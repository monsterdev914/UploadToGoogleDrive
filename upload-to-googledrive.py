import os
from pathlib import Path
import asyncio
import json
from bs4 import BeautifulSoup
import time
# import requests
from playwright.async_api import async_playwright
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
UPLOAD_JOB_FILE = Path("upload_job.json")
ROOT_SHARED_FOLDER_ID = "1h6RHOs6FYVMAX4l-4kUwszQ3tsLFBfPZ"
# OAuth scopes
SCOPES = ["https://www.googleapis.com/auth/drive"]
start_year = 2025
end_year = 2025
# ---------- Google Drive auth ----------
def get_drive_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

def get_or_create_folder(service, folder_path: str):
    """
    Get folder ID by path like 'app/aa'. Creates missing folders.
    """
    parent_id = ROOT_SHARED_FOLDER_ID
    for folder_name in folder_path.strip("/").split("/"):
        # Check if folder exists
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get("files", [])

        if items:
            # Folder exists
            folder_id = items[0]["id"]
        else:
            # Create folder
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]

            folder = service.files().create(body=file_metadata, fields="id").execute()
            folder_id = folder["id"]
            print(f"Created folder '{folder_name}' with ID {folder_id}")

        parent_id = folder_id

    return parent_id  # final folder ID

def upload_to_drive(service, file_path, folder_id):
    file_metadata = {"name": os.path.basename(file_path), "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=True, chunksize=10*1024*1024)
    request = service.files().create(body=file_metadata, media_body=media, fields="id")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")
    print(f"Uploaded to Drive: {file_path}, File ID: {response['id']}")
async def download_file_async(dest_folder: str, service):
    base_url = "https://www.sec.gov/Archives/edgar/Feed/"
    dest_folder = Path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        for year in range(start_year, end_year + 1):
                    url = f"{base_url}{year}/"
                    await page.goto(url, wait_until="domcontentloaded")
                    soup = BeautifulSoup(await page.content(), 'html.parser')
                    table_for_qrts = soup.find('table')
                    trs_for_qrts = table_for_qrts.find_all('tr')[1:]
                    for tr in trs_for_qrts:
                        href = tr.find('a')['href']
                        qrt = tr.find('a').text
                        await page.goto(f"{base_url}{year}/{href}")
                        soup_qrt = BeautifulSoup(await page.content(), 'html.parser')
                        table_for_file = soup_qrt.find('table')
                        trs_for_file = table_for_file.find_all('tr')[1:]

                        for tr_file in trs_for_file:
                            file_href = tr_file.find('a')['href']
                            if check_upload_jobs_to_download(file_href):
                                continue
                            async with page.expect_download() as download_info:
                                await page.evaluate(f'''
                                    () => {{
                                        const a = document.querySelector('a[href="{file_href}"]');
                                        if (a) a.click();
                                    }}
                                ''')
                            download = await download_info.value
                            file_path = dest_folder / download.suggested_filename
                            await download.save_as(file_path)
                            # read upload job file and append new job
                            append_upload_job(str(file_path), download.suggested_filename, get_or_create_folder(service, f"{year}/{qrt}"))
                            print(f"Saved: {file_path}")
        await browser.close()

def check_upload_jobs_to_download(file_name: str):
    jobs = []
    if UPLOAD_JOB_FILE.exists():
        with open(UPLOAD_JOB_FILE, "r") as f:
            try:
                jobs = json.load(f)
            except json.JSONDecodeError:
                jobs = []
    # check if the file is already in jobs
    for job in jobs:
        if job["file_name"] == file_name:
            return True
    return False

def append_upload_job(file_path: str, file_name: str, folder_id: str):
    # Load existing jobs if file exists
    if UPLOAD_JOB_FILE.exists():
        with open(UPLOAD_JOB_FILE, "r") as f:
            try:
                jobs = json.load(f)
            except json.JSONDecodeError:
                jobs = []
    else:
        jobs = []

    # Append new job
    jobs.append({"file_path": file_path, "file_name": file_name, "folder_id": folder_id, "status": "pending"})

    # Save back
    with open(UPLOAD_JOB_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

    print(f"Added upload job: {file_path} -> {folder_id}")

async def upload_pending_jobs_async(service, poll_interval=5):
    """
    Continuously checks upload jobs and uploads pending files to Drive.
    """
    while True:
        if not UPLOAD_JOB_FILE.exists():
            await asyncio.sleep(poll_interval)
            continue

        with open(UPLOAD_JOB_FILE, "r") as f:
            try:
                jobs = json.load(f)
            except json.JSONDecodeError:
                print("Upload job file is corrupted.")
                await asyncio.sleep(poll_interval)
                continue

        updated = False
        for job in jobs:
            if job["status"] == "pending":
                try:
                    upload_to_drive(service, job["file_path"], job["folder_id"])
                    if os.path.exists(job["file_path"]):
                        os.remove(job["file_path"])
                        print(f"Deleted local file: {job['file_path']}")
                    job["status"] = "completed"
                    updated = True
                except Exception as e:
                    print(f"Failed to upload {job['file_path']}: {e}")

        if updated:
            with open(UPLOAD_JOB_FILE, "w") as f:
                json.dump(jobs, f, indent=2)

        await asyncio.sleep(poll_interval)  # non-blocking wait
async def main():    
    service = get_drive_service()
    download_task = asyncio.create_task(download_file_async('downloads', service))
    upload_task = asyncio.create_task(upload_pending_jobs_async(service))
    await download_task

    # After downloads finish, keep running uploads for remaining jobs
    while True:
        with open(UPLOAD_JOB_FILE, "r") as f:
            jobs = json.load(f)
        if all(job["status"] == "completed" for job in jobs):
            print("All uploads completed.")
            break
        await asyncio.sleep(5)

    # Cancel upload task since everything is done
    upload_task.cancel()
    try:
        await upload_task
    except asyncio.CancelledError:
        pass
if __name__ == "__main__":
    print("This script is being run directly.")
    asyncio.run(main())
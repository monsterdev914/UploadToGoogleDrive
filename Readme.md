# SEC EDGAR Downloader & Google Drive Uploader

This project automates downloading SEC EDGAR filings and uploading them to a shared Google Drive folder using Playwright and Google Drive API.

---

## Features

- Asynchronously downloads SEC EDGAR feed files for a given year range.
- Automatically creates folders in Google Drive if they do not exist.
- Tracks upload jobs in a JSON file (`upload_job.json`) to prevent duplicate uploads.
- Deletes local files after successful upload.
- Fully asynchronous: downloads and uploads run concurrently.

---

## Requirements

- Python 3.10+
- Google credentials (`credentials.json`) for Google Drive API
- Virtual environment (recommended)

Python packages:

- `playwright`
- `beautifulsoup4`
- `google-api-python-client`
- `google-auth`
- `google-auth-oauthlib`
- `google-auth-httplib2`

---

## Installation

1. Clone the repository:

    ```bash
    git clone <your-repo-url>
    cd <your-repo-folder>
    ```

2. Create and activate a virtual environment:
    ```bash
    python -m venv venv
    source venv/Scripts/activate   # Git Bash / Linux / macOS
    # Or on Windows PowerShell:
    # venv\Scripts\Activate
    ```

3. Install required packages:
    ```bash
    pip install -r requirements.txt
    ```

4. Install Playwright browsers:
    ```bash
    playwright install chromium
    ```


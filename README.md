# BookLeaf Cover Checker

Automated validation system for book cover files submitted to BookLeaf Publishing. Authors upload covers to a Google Drive folder; the system analyses each one for badge zone violations, margin issues, and resolution problems, logs results to Airtable, emails the author automatically, and shows everything in a local web dashboard.

---

## System Architecture

```
Author uploads cover to Google Drive folder
         │
         ▼
  drive_watcher.py (background thread, polls every 30s)
         │  downloads file → extracts ISBN from filename
         ▼
     checker.py (OpenCV + pytesseract)
         │  OCR → badge zone detection → margin checks → resolution check
         │  draws annotated image → saves to static/annotations/
         ▼
  ┌──────┴──────┐
  ▼             ▼
airtable_client  email_sender
(logs result)    (notifies author)
         │
         ▼
  Flask dashboard (http://localhost:5000)
  • Upload manually via drag & drop
  • Live results table (polls /api/results every 15s)
  • Drive watcher status bar (polls /api/status every 10s)
```

---

## Prerequisites

- Python 3.9 or higher
- **Tesseract OCR** (for text detection)
- **Poppler** (for PDF → image conversion)

---

## Setup

### 1 — Run the setup script

**Linux / macOS:**
```bash
bash setup.sh
```

This installs Tesseract, Poppler, all Python packages, creates required directories, and copies `.env.example` to `.env`.

**Windows:**

Install Tesseract and Poppler manually first (see below), then:
```cmd
pip install -r requirements.txt
mkdir static\annotations test_covers uploads_tmp
copy .env.example .env
```

---

### 2 — Fill in your `.env` file

Open `.env` in a text editor and fill in every value. See **How to get API keys** below.

---

### 3 — Add `credentials.json`

Place your Google Drive service account key file at `credentials.json` in the project root (same folder as `app.py`).

---

### 4 — Run

```bash
python app.py
```

Open your browser at **http://localhost:5000**.

---

## How to Get Each API Key

### Google Drive Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable **Google Drive API**: APIs & Services → Enable APIs → search "Drive API"
4. Create a service account: IAM & Admin → Service Accounts → Create
5. Give it a name, click Done
6. Click the service account → Keys tab → Add Key → Create New Key → JSON
7. Download the JSON file and rename it to `credentials.json`
8. Place it in the project root
9. **Share your Google Drive folder** with the service account email address (looks like `name@project.iam.gserviceaccount.com`) with **Viewer** access
10. Copy the folder ID from the Drive URL into `GOOGLE_DRIVE_FOLDER_ID` in `.env`

### Airtable

1. Go to [airtable.com](https://airtable.com) and create an account
2. Create a new **Base** called "BookLeaf Publishing"
3. Create a table called **"Cover Tracker"** with these exact fields (see table setup section below)
4. Get your **Base ID**: open the base in your browser — the URL contains `appXXXXXXXXXXXXXX` — that is your `AIRTABLE_BASE_ID`
5. Create a **Personal Access Token**: [airtable.com/create/tokens](https://airtable.com/create/tokens)
   - Scope: `data.records:read`, `data.records:write`
   - Access: select your base
6. Copy the token to `AIRTABLE_TOKEN` in `.env`

### Gmail App Password

1. Enable 2-Factor Authentication on your Google Account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Select app: **Mail** — device: **Other** → name it "BookLeaf"
4. Copy the 16-character password to `GMAIL_APP_PASSWORD` in `.env`
5. Set `GMAIL_ADDRESS` to your Gmail address

---

## Airtable Table Setup

Create a table named **Cover Tracker** with these fields **in this order**:

| Field Name              | Field Type          | Notes                           |
|-------------------------|---------------------|---------------------------------|
| Book ID                 | Single line text    |                                 |
| ISBN                    | Single line text    |                                 |
| Book Title              | Single line text    |                                 |
| Author Name             | Single line text    |                                 |
| Author Email            | Email               |                                 |
| Status                  | Single select       | Options: `PASS`, `REVIEW NEEDED`|
| Confidence Score        | Number              | Integer                         |
| Issues Found            | Long text           |                                 |
| Correction Instructions | Long text           |                                 |
| Timestamp               | Date                | Enable "Include time"           |
| Annotation URL          | URL                 |                                 |
| Revision Count          | Number              | Default: 0                      |

---

## Running the System

```bash
python app.py
```

- Dashboard: http://localhost:5000
- Drive watcher starts automatically in the background
- Upload covers via the web UI or by placing them in your Drive folder

---

## How to Test

### Via the web UI:
1. Name a test image: `9781234567890_text.png` (any ISBN from `isbn_db.py`)
2. Drag it into the upload zone on the dashboard
3. The result card will appear with the annotated image, status, and confidence score

### Via Google Drive:
1. Upload a file named `9781234567890_text.pdf` to your configured Drive folder
2. Within 30 seconds, the Drive watcher will process it automatically
3. Check the Recent Submissions table in the dashboard

### Test filenames using mock ISBN database:
```
9781234567890_text.pdf   → Ojal Jain — Whispers of the Soul
9789876543210_text.pdf   → Arjun Mehta — The Quiet Hours
9781122334455_text.pdf   → Priya Sharma — Between the Monsoons
```

---

## Cover Specifications (BookLeaf Publishing)

| Spec                | Value                     |
|---------------------|---------------------------|
| Cover size          | 5 inches × 8 inches       |
| Safe margins        | 3mm on left, right, top   |
| Badge zone          | Bottom 9mm (PROTECTED)    |
| Minimum resolution  | 300 DPI                   |
| Badge               | 21st Century Emily Dickinson Award emblem |

The **badge zone** (bottom 9mm) is always flagged as protected. Any text detected in this zone causes the cover to be classified as **REVIEW NEEDED** regardless of the confidence score.

---

## Troubleshooting

**`tesseract is not installed or it's not in your PATH`**
- Linux: `sudo apt-get install tesseract-ocr`
- macOS: `brew install tesseract`
- Windows: Install from https://github.com/UB-Mannheim/tesseract/wiki — ensure it's at `C:\Program Files\Tesseract-OCR\tesseract.exe`

**`Unable to open poppler...` or PDF conversion fails**
- Linux: `sudo apt-get install poppler-utils`
- macOS: `brew install poppler`
- Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases — extract and add the `bin/` folder to your system PATH

**`AIRTABLE_TOKEN or AIRTABLE_BASE_ID not set`**
- Fill in both values in `.env`. The app will still run and show results locally, but won't log to Airtable.

**`Gmail authentication failed`**
- Ensure you are using an **App Password** (16 chars, no spaces), not your real Gmail password
- 2FA must be enabled on the Google Account

**`Google credentials not found at 'credentials.json'`**
- Place your service account key JSON file at `credentials.json` in the project root
- The Drive watcher will be disabled until this is in place — manual uploads still work

**Annotated image not showing in dashboard**
- Check that `static/annotations/` directory exists and is writable
- The cover file must be a valid image or PDF

**`cv2 module not found`**
- Run: `pip install opencv-python==4.9.0.80`
- On some systems: `pip install opencv-python-headless==4.9.0.80`

---

## Windows-Specific Notes

- Tesseract must be installed at `C:\Program Files\Tesseract-OCR\tesseract.exe` (the path is hardcoded in `checker.py` for Windows)
- Poppler must be on your system PATH for pdf2image to work
- Use `python app.py` in a standard Command Prompt or PowerShell window

---

## Project Structure

```
bookleaf-cover-checker/
├── app.py               Flask app + API routes
├── checker.py           CV analysis (OpenCV + pytesseract)
├── drive_watcher.py     Google Drive polling loop
├── airtable_client.py   Airtable read / write
├── email_sender.py      Gmail notifications
├── isbn_db.py           Mock ISBN → author mapping
├── templates/
│   └── index.html       Dashboard (HTML + CSS + JS, no build step)
├── static/
│   └── annotations/     Annotated cover images (auto-generated)
├── test_covers/         Put sample covers here for manual testing
├── credentials.json     Google service account key (not committed)
├── .env                 All secrets (not committed)
├── .env.example         Template for .env
├── .gitignore
├── requirements.txt
├── setup.sh             One-command setup
└── README.md
```

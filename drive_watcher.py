"""
drive_watcher.py — Google Drive folder polling loop
Runs as a daemon background thread inside Flask.
Polls the target folder every 30 seconds for new cover files.
"""

import os
import io
import time
import logging
import tempfile
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# ── State shared with Flask /api/status endpoint ──────────────────────────────
watcher_state = {
    "running":       False,
    "last_checked":  None,
    "files_seen":    0,
    "error":         None,
}

_processed_ids: set = set()
_state_lock          = threading.Lock()


# ── Google Drive auth ─────────────────────────────────────────────────────────

def _build_drive_service():
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Google credentials not found at '{creds_path}'. "
            "See README.md for how to create a service account."
        )

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds)
    return service


# ── File helpers ───────────────────────────────────────────────────────────────

def _extract_isbn(filename: str) -> str:
    """
    Extract ISBN from filename. Expects format: 1234567890123_text.pdf
    Returns the part before the first underscore.
    """
    base = os.path.splitext(filename)[0]  # strip extension
    parts = base.split("_", 1)
    return parts[0].strip()


def _download_file(service, file_id: str, dest_path: str) -> bool:
    """Download a Drive file by ID to a local path."""
    try:
        from googleapiclient.http import MediaIoBaseDownload

        request   = service.files().get_media(fileId=file_id)
        fh        = io.FileIO(dest_path, "wb")
        downloader = MediaIoBaseDownload(fh, request, chunksize=4 * 1024 * 1024)

        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.close()
        return True
    except Exception as e:
        logger.error(f"[drive] Download failed for file_id={file_id}: {e}")
        return False


# ── Poll loop ─────────────────────────────────────────────────────────────────

def _poll_once(service, folder_id: str):
    """
    List files in the Drive folder.
    Process any that haven't been seen before.
    """
    # Import here to avoid circular import at module level
    from checker        import analyse_cover
    from airtable_client import create_record
    from email_sender   import send_email
    from isbn_db        import get_author_info

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false "
        "and (mimeType = 'application/pdf' "
        "     or mimeType = 'image/png' "
        "     or mimeType = 'image/jpeg')"
    )

    try:
        resp = service.files().list(
            q=query,
            fields="files(id, name, createdTime, mimeType)",
            orderBy="createdTime desc",
            pageSize=50,
        ).execute()
    except Exception as e:
        logger.error(f"[drive] list() failed: {e}")
        with _state_lock:
            watcher_state["error"] = str(e)
        return

    files = resp.get("files", [])

    for f in files:
        fid  = f["id"]
        name = f["name"]

        if fid in _processed_ids:
            continue

        logger.info(f"[drive] New file detected: {name} (id={fid})")
        _processed_ids.add(fid)

        isbn = _extract_isbn(name)
        ext  = os.path.splitext(name)[1].lower() or ".pdf"

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name

        try:
            ok = _download_file(service, fid, tmp_path)
            if not ok:
                continue

            result      = analyse_cover(tmp_path, isbn=isbn)
            author_info = get_author_info(isbn)

            # Log to Airtable
            record_id = create_record(result, author_info)
            if record_id:
                logger.info(f"[drive] Airtable record created: {record_id}")

            # Send author email
            sent = send_email(result, author_info)
            logger.info(f"[drive] Email sent={sent} for ISBN={isbn}")

            with _state_lock:
                watcher_state["files_seen"] += 1

        except Exception as e:
            logger.error(f"[drive] Processing error for {name}: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def watch_drive():
    """
    Main loop — called in a daemon thread.
    Polls GOOGLE_DRIVE_FOLDER_ID every 30 seconds.
    """
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    if not folder_id:
        logger.warning(
            "[drive] GOOGLE_DRIVE_FOLDER_ID not set in .env — Drive watcher disabled"
        )
        with _state_lock:
            watcher_state["running"] = False
            watcher_state["error"]   = "GOOGLE_DRIVE_FOLDER_ID not configured"
        return

    try:
        service = _build_drive_service()
        logger.info(f"[drive] Watcher started. Watching folder: {folder_id}")
    except Exception as e:
        logger.error(f"[drive] Could not build Drive service: {e}")
        with _state_lock:
            watcher_state["running"] = False
            watcher_state["error"]   = str(e)
        return

    with _state_lock:
        watcher_state["running"] = True
        watcher_state["error"]   = None

    while True:
        try:
            _poll_once(service, folder_id)
        except Exception as e:
            logger.error(f"[drive] Unexpected poll error: {e}")
            with _state_lock:
                watcher_state["error"] = str(e)

        with _state_lock:
            watcher_state["last_checked"] = datetime.now().isoformat()

        time.sleep(30)


def start_watcher():
    """Spawn the Drive watcher as a daemon thread."""
    t = threading.Thread(target=watch_drive, daemon=True, name="DriveWatcher")
    t.start()
    logger.info("[drive] Watcher thread started")
    return t

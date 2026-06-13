"""
airtable_client.py — Airtable read / write for Cover Tracker table
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy import so app starts even if pyairtable isn't installed yet
_table = None


def _get_table():
    global _table
    if _table is not None:
        return _table

    token    = os.getenv("AIRTABLE_TOKEN", "")
    base_id  = os.getenv("AIRTABLE_BASE_ID", "")
    tbl_name = os.getenv("AIRTABLE_TABLE_NAME", "Cover Tracker")

    if not token or not base_id:
        logger.warning("[airtable] AIRTABLE_TOKEN or AIRTABLE_BASE_ID not set — skipping")
        return None

    try:
        from pyairtable import Table
        _table = Table(token, base_id, tbl_name)
        return _table
    except Exception as e:
        logger.error(f"[airtable] Failed to initialise table: {e}")
        return None


# ── Correction instructions auto-generator ────────────────────────────────────

def _build_correction_instructions(issues: list) -> str:
    instructions = []
    for issue in issues:
        il = issue.lower()
        if "badge zone" in il or "overlap" in il:
            instructions.append(
                "Move your author name and all text elements above the bottom 9mm zone "
                "of the cover. The 21st Century Emily Dickinson Award emblem is placed in "
                "the bottom 9mm and absolutely no text may enter this area."
            )
        elif "margin" in il:
            instructions.append(
                "Ensure all text elements are at least 3mm away from every cover edge "
                "(left, right, and top). Review your layout in your design software and "
                "add or verify safe-margin guides at 3mm."
            )
        elif "resolution" in il or "dpi" in il:
            instructions.append(
                "Please resubmit the cover file at 300 DPI or higher. Export from your "
                "design application at print resolution. JPEG, PNG, or PDF formats are "
                "accepted. Low-resolution files cannot be used for print production."
            )
        else:
            instructions.append(
                f"Issue detected: {issue}. Please review your cover file and correct "
                "before resubmission."
            )
    return "\n".join(f"{i+1}. {instr}" for i, instr in enumerate(instructions))


# ── Public API ─────────────────────────────────────────────────────────────────

def create_record(result: dict, author_info: dict) -> str | None:
    """
    Insert a new row into Airtable Cover Tracker.
    Returns the new record ID, or None on failure.
    """
    table = _get_table()
    if table is None:
        logger.warning("[airtable] Skipping create_record — table unavailable")
        return None

    issues_str      = "\n".join(result.get("issues", [])) or "None"
    correction_str  = _build_correction_instructions(result.get("issues", []))
    ts              = result.get("timestamp", datetime.now().isoformat())

    # Airtable Date field needs ISO format; trim to date+time without microseconds
    try:
        dt_obj  = datetime.fromisoformat(ts)
        airtable_ts = dt_obj.strftime("%Y-%m-%d")
    except Exception:
        airtable_ts = ts

    fields = {
        "Book ID":               f"BL-{result.get('isbn', 'UNKNOWN')}",
        "ISBN":                  result.get("isbn", ""),
        "Book Title":            author_info.get("book_title", "Unknown Title"),
        "Author Name":           author_info.get("author_name", "Unknown Author"),
        "Author Email":          author_info.get("author_email", ""),
        "Status":                result.get("status", "REVIEW NEEDED"),
        "Confidence Score":      result.get("confidence", 0),
        "Issues Found":          issues_str,
        "Correction Instructions": correction_str,
        "Timestamp":             airtable_ts,
        "Revision Count":        0,
    }

    # Annotation URL — only add if we have a path
    ann = result.get("annotation_path")
    if ann:
        flask_base = os.getenv("FLASK_BASE_URL", "http://localhost:5000")
        fields["Annotation URL"] = f"{flask_base}/static/{ann}"

    try:
        record = table.create(fields)
        record_id = record.get("id") or record["id"]
        logger.info(f"[airtable] Created record {record_id} for ISBN {result.get('isbn')}")
        return record_id
    except Exception as e:
        logger.error(f"[airtable] create_record failed: {e}")
        return None


def update_record(record_id: str, fields: dict) -> bool:
    """
    Update an existing Airtable record by ID.
    Returns True on success.
    """
    table = _get_table()
    if table is None:
        return False

    try:
        table.update(record_id, fields)
        logger.info(f"[airtable] Updated record {record_id}")
        return True
    except Exception as e:
        logger.error(f"[airtable] update_record failed: {e}")
        return False


def get_all_records() -> list:
    """
    Fetch all records from Cover Tracker, newest first.
    Returns a list of dicts with flattened fields.
    """
    table = _get_table()
    if table is None:
        return []

    try:
        raw = table.all(sort=["-Timestamp"])
    except Exception:
        try:
            raw = table.all()
        except Exception as e:
            logger.error(f"[airtable] get_all_records failed: {e}")
            return []

    records = []
    for r in raw:
        f = r.get("fields", {})
        records.append({
            "id":            r.get("id", ""),
            "isbn":          f.get("ISBN", ""),
            "book_title":    f.get("Book Title", ""),
            "author_name":   f.get("Author Name", ""),
            "author_email":  f.get("Author Email", ""),
            "status":        f.get("Status", ""),
            "confidence":    f.get("Confidence Score", 0),
            "issues":        f.get("Issues Found", ""),
            "corrections":   f.get("Correction Instructions", ""),
            "timestamp":     f.get("Timestamp", ""),
            "annotation_url":f.get("Annotation URL", ""),
            "revision_count":f.get("Revision Count", 0),
        })
    return records

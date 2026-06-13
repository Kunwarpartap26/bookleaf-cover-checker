"""
app.py — BookLeaf Cover Checker — Flask application
Serves the dashboard, handles uploads, exposes API endpoints.
"""

import os
import uuid
import logging
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory

from dotenv import load_dotenv
load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Flask app ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
UPLOAD_FOLDER      = "uploads_tmp"
os.makedirs(UPLOAD_FOLDER,        exist_ok=True)
os.makedirs("static/annotations", exist_ok=True)

# In-memory log for results (supplements Airtable; used when Airtable is not configured)
_local_results: list = []


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _extract_isbn(filename: str) -> str:
    base   = os.path.splitext(filename)[0]
    parts  = base.split("_", 1)
    return parts[0].strip()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/annotations/<path:filename>")
def serve_annotation(filename):
    return send_from_directory("static/annotations", filename)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Accept a cover file upload, run CV analysis, log to Airtable + email author.
    Returns JSON result.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type. Use PDF, PNG, or JPG."}), 400

    # Save to temp file
    ext      = file.filename.rsplit(".", 1)[1].lower()
    tmp_name = f"{uuid.uuid4().hex}.{ext}"
    tmp_path = os.path.join(UPLOAD_FOLDER, tmp_name)

    try:
        file.save(tmp_path)
    except Exception as e:
        logger.error(f"[upload] Could not save file: {e}")
        return jsonify({"error": "Failed to save uploaded file"}), 500

    isbn = _extract_isbn(file.filename)

    try:
        from checker         import analyse_cover
        from airtable_client import create_record
        from email_sender    import send_email
        from isbn_db         import get_author_info

        result      = analyse_cover(tmp_path, isbn=isbn)
        author_info = get_author_info(isbn)

        # Airtable
        record_id = None
        try:
            record_id = create_record(result, author_info)
        except Exception as e:
            logger.error(f"[upload] Airtable create_record failed: {e}")

        # Email
        email_sent = False
        try:
            email_sent = send_email(result, author_info)
        except Exception as e:
            logger.error(f"[upload] send_email failed: {e}")

        # Cache locally for dashboard when Airtable isn't configured
        _local_results.insert(0, {
            "id":            record_id or f"local-{uuid.uuid4().hex[:8]}",
            "isbn":          result["isbn"],
            "book_title":    author_info.get("book_title", "Unknown"),
            "author_name":   author_info.get("author_name", "Unknown"),
            "author_email":  author_info.get("author_email", ""),
            "status":        result["status"],
            "confidence":    result["confidence"],
            "issues":        "\n".join(result.get("issues", [])),
            "timestamp":     result["timestamp"],
            "annotation_url": (
                f"/static/{result['annotation_path']}"
                if result.get("annotation_path") else ""
            ),
            "revision_count": 0,
        })

        response = {
            "isbn":           result["isbn"],
            "status":         result["status"],
            "confidence":     result["confidence"],
            "issues":         result["issues"],
            "badge_overlaps": [b["word"] for b in result.get("badge_overlaps", [])],
            "resolution_ok":  result["resolution_ok"],
            "timestamp":      result["timestamp"],
            "author_name":    author_info.get("author_name", "Unknown"),
            "book_title":     author_info.get("book_title", "Unknown"),
            "annotation_url": (
                f"/static/{result['annotation_path']}"
                if result.get("annotation_path") else None
            ),
            "airtable_id":    record_id,
            "email_sent":     email_sent,
        }

        logger.info(
            f"[upload] ISBN={isbn} → {result['status']} "
            f"(confidence={result['confidence']}%, airtable={bool(record_id)}, email={email_sent})"
        )
        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"[upload] Unexpected error: {e}")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.route("/api/results")
def api_results():
    """
    Return all cover analysis records.
    Prefers Airtable; falls back to local in-memory cache.
    """
    try:
        from airtable_client import get_all_records
        records = get_all_records()
        if records:
            return jsonify(records), 200
    except Exception as e:
        logger.warning(f"[results] Airtable fetch failed, using local cache: {e}")

    return jsonify(_local_results), 200


@app.route("/api/status")
def api_status():
    """Return Drive watcher status."""
    from drive_watcher import watcher_state, _state_lock
    with _state_lock:
        state = dict(watcher_state)

    last = state.get("last_checked")
    seconds_ago = None
    if last:
        try:
            delta = datetime.now() - datetime.fromisoformat(last)
            seconds_ago = int(delta.total_seconds())
        except Exception:
            pass

    return jsonify({
        "running":      state.get("running", False),
        "last_checked": last,
        "seconds_ago":  seconds_ago,
        "files_seen":   state.get("files_seen", 0),
        "error":        state.get("error"),
    }), 200


# ── Startup ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from drive_watcher import start_watcher
    start_watcher()

    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    logger.info(f"✅ BookLeaf Cover Checker running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)

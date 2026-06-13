"""
email_sender.py — BookLeaf automated author email notifications
Uses smtplib with Gmail App Password (no OAuth required).
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Template helpers ───────────────────────────────────────────────────────────

def _format_issues_list(issues: list) -> str:
    if not issues:
        return "   • None"
    return "\n".join(f"   • {issue}" for issue in issues)


def _build_correction_instructions(issues: list) -> str:
    instructions = []
    for issue in issues:
        il = issue.lower()
        if "badge zone" in il or "overlap" in il:
            instructions.append(
                "Move your author name and all text above the bottom 9mm zone of the cover.\n"
                "   The award badge is placed in the bottom 9mm — no text may enter this area."
            )
        elif "margin" in il:
            instructions.append(
                "Ensure all text is at least 3mm away from the cover edges on all sides.\n"
                "   Add 3mm safe-margin guides in your design software and push all text inside them."
            )
        elif "resolution" in il or "dpi" in il:
            instructions.append(
                "Please resubmit the cover at 300 DPI or higher for print quality.\n"
                "   Export from your design app at print resolution (not screen resolution)."
            )
        else:
            instructions.append(f"Please review and correct: {issue}")

    return "\n\n".join(f"   {i+1}. {instr}" for i, instr in enumerate(instructions))


def _format_timestamp(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%d %B %Y at %H:%M UTC")
    except Exception:
        return ts


# ── Email templates ────────────────────────────────────────────────────────────

def _pass_email_body(author_name, isbn, confidence, timestamp) -> str:
    ts_fmt = _format_timestamp(timestamp)
    return f"""Dear {author_name},

Great news! Your book cover has been reviewed and approved.

📋 Review Summary:
   • ISBN:             {isbn}
   • Status:           ✅ PASS
   • Confidence Score: {confidence}%
   • Reviewed:         {ts_fmt}

Your cover meets all BookLeaf Publishing standards:
   ✅ Award badge zone is clear
   ✅ Text within safe margins
   ✅ Resolution acceptable

Your book is now cleared to proceed to the next stage of publishing.
Our team will be in touch with further instructions shortly.

If you have any questions, please contact us at info@bookleafpub.in

Warm regards,
BookLeaf Publishing Team
bookleafpub.in | India | USA | UK
"""


def _review_email_body(author_name, isbn, book_title, confidence, timestamp, issues, corrections) -> str:
    ts_fmt     = _format_timestamp(timestamp)
    issues_str = _format_issues_list(issues)
    return f"""Dear {author_name},

Thank you for submitting your book cover for "{book_title}". Our automated 
validation system has detected some issues that need to be corrected before 
we can proceed to print production.

📋 Review Summary:
   • ISBN:             {isbn}
   • Status:           ⚠️ REVIEW NEEDED
   • Confidence Score: {confidence}%
   • Reviewed:         {ts_fmt}

❌ Issues Detected:
{issues_str}

📝 Correction Instructions:
{corrections}

⏱️ Please resubmit your corrected cover within 48 hours.

Upload your revised cover to the same Google Drive folder using 
the same filename format:

   {isbn}_text.pdf

Your revision will be analysed automatically when uploaded.

For support or questions: info@bookleafpub.in

Warm regards,
BookLeaf Publishing Team
bookleafpub.in | India | USA | UK
"""


# ── Core send function ─────────────────────────────────────────────────────────

def send_email(result: dict, author_info: dict) -> bool:
    """
    Send PASS or REVIEW NEEDED email to the author.
    Returns True on success, False on failure.
    """
    gmail_address  = os.getenv("GMAIL_ADDRESS", "")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")

    if not gmail_address or not gmail_password:
        logger.warning("[email] GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set — skipping email")
        return False

    author_name  = author_info.get("author_name",  "Author")
    author_email = author_info.get("author_email",  "")
    book_title   = author_info.get("book_title",    "Your Book")

    if not author_email:
        logger.warning("[email] No author email address — skipping")
        return False

    isbn       = result.get("isbn",       "N/A")
    status     = result.get("status",     "REVIEW NEEDED")
    confidence = result.get("confidence", 0)
    timestamp  = result.get("timestamp",  datetime.now().isoformat())
    issues     = result.get("issues",     [])

    corrections = _build_correction_instructions(issues)

    if status == "PASS":
        subject = f"✅ Your Book Cover Has Been Approved — {book_title}"
        body    = _pass_email_body(author_name, isbn, confidence, timestamp)
    else:
        subject = f"⚠️ Action Required — Book Cover Review Needed — {book_title}"
        body    = _review_email_body(
            author_name, isbn, book_title, confidence,
            timestamp, issues, corrections
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"BookLeaf Publishing <{gmail_address}>"
    msg["To"]      = author_email

    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, [author_email], msg.as_string())
        logger.info(f"[email] Sent '{status}' email to {author_email} for ISBN {isbn}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("[email] Gmail authentication failed. Check GMAIL_APP_PASSWORD in .env")
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"[email] Recipient refused: {author_email}")
    except Exception as e:
        logger.error(f"[email] Failed to send email: {e}")

    return False

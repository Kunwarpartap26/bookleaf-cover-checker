"""
checker.py — BookLeaf Cover Validation Engine
Computer Vision analysis using OpenCV + pytesseract
"""

import os
import platform
import cv2
import numpy as np
import pytesseract
from PIL import Image as PILImage
from datetime import datetime

# Windows Tesseract path fix
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ─── Constants ────────────────────────────────────────────────────────────────
# BookLeaf Publishing specs at 300 DPI, 5×8 inch cover
BASE_HEIGHT_PX   = 2400   # 8 inches × 300 DPI
BASE_BADGE_PX    = 106    # 9mm × (300/25.4) ≈ 106px
BASE_MARGIN_PX   = 35     # 3mm × (300/25.4) ≈ 35px
MIN_DPI          = 295
OCR_CONF_THRESH  = 60     # skip OCR words below this confidence


def _mm_to_px(mm: float, scale: float = 1.0) -> int:
    """Convert millimetres to pixels at 300 DPI, with optional scale."""
    return int((mm * 300 / 25.4) * scale)


def _rect_overlap(r1: dict, r2: dict) -> bool:
    """Return True if two rectangles overlap (each has x1,y1,x2,y2)."""
    return not (
        r1['x2'] <= r2['x1'] or
        r1['x1'] >= r2['x2'] or
        r1['y2'] <= r2['y1'] or
        r1['y1'] >= r2['y2']
    )


def _load_image(image_path: str):
    """
    Load image from path, handling PDFs via pdf2image.
    Returns (cv2_bgr_array, pil_image).
    """
    ext = os.path.splitext(image_path)[1].lower()

    if ext == '.pdf':
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(image_path, dpi=300, first_page=1, last_page=1)
            if not pages:
                raise ValueError("PDF has no pages")
            pil_img = pages[0].convert('RGB')
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF: {e}")
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    else:
        cv_img = cv2.imread(image_path)
        if cv_img is None:
            raise RuntimeError(f"OpenCV could not load image: {image_path}")
        pil_img = PILImage.open(image_path).convert('RGB')

    return cv_img, pil_img


def _get_dpi(pil_img: PILImage.Image, image_path: str) -> tuple:
    """Extract DPI from PIL image metadata; fall back to (72, 72)."""
    try:
        dpi = pil_img.info.get('dpi', None)
        if dpi and dpi[0] > 0:
            return dpi
    except Exception:
        pass
    # Try re-opening original (pdf2image gives no dpi info on the PIL object)
    try:
        raw = PILImage.open(image_path)
        dpi = raw.info.get('dpi', (72, 72))
        return dpi
    except Exception:
        return (72, 72)


def analyse_cover(image_path: str, isbn: str = "unknown") -> dict:
    """
    Full cover analysis pipeline.

    Returns a result dict with:
      isbn, status, confidence, issues, badge_overlaps,
      margin_violations, resolution_ok, annotation_path, timestamp
    """
    issues            = []
    badge_overlaps    = []
    margin_violations = []
    resolution_ok     = True
    annotation_path   = None

    # ── Step 1: Load image ────────────────────────────────────────────────────
    try:
        cv_img, pil_img = _load_image(image_path)
    except Exception as e:
        return {
            "isbn": isbn,
            "status": "REVIEW NEEDED",
            "confidence": 0,
            "issues": [f"Image load error: {e}"],
            "badge_overlaps": [],
            "margin_violations": [],
            "resolution_ok": False,
            "annotation_path": None,
            "timestamp": datetime.now().isoformat(),
        }

    img_h, img_w = cv_img.shape[:2]

    # ── Step 2: Calculate zones ───────────────────────────────────────────────
    scale          = img_h / BASE_HEIGHT_PX
    badge_zone_h   = int(BASE_BADGE_PX  * scale)
    side_margin    = int(BASE_MARGIN_PX * scale)
    top_margin_px  = int(BASE_MARGIN_PX * scale)

    badge_y_start = img_h - badge_zone_h
    badge_rect    = {"x1": 0, "y1": badge_y_start, "x2": img_w, "y2": img_h}

    # ── Step 3: Resolution check ──────────────────────────────────────────────
    dpi = _get_dpi(pil_img, image_path)
    # if dpi[0] < MIN_DPI:
    #     resolution_ok = False
    #     issues.append(
    #         f"Low resolution: {int(dpi[0])} DPI detected, {MIN_DPI} DPI required"
    #     )

    # ── Step 4: OCR ──────────────────────────────────────────────────────────
    try:
        # Use a slightly enhanced image for OCR (grayscale, CLAHE)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        ocr_data = pytesseract.image_to_data(
            enhanced,
            output_type=pytesseract.Output.DICT,
            config='--psm 11 --oem 3'
        )
    except Exception as e:
        issues.append(f"OCR failed: {e}")
        ocr_data = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}

    n_words = len(ocr_data['text'])

    # ── Step 5 & 6: Badge overlap + margin violation detection ───────────────
    for i in range(n_words):
        word = str(ocr_data['text'][i]).strip()
        if not word:
            continue

        try:
            conf = int(ocr_data['conf'][i])
        except (ValueError, TypeError):
            conf = -1

        if conf < OCR_CONF_THRESH:
            continue

        left   = int(ocr_data['left'][i])
        top    = int(ocr_data['top'][i])
        width  = int(ocr_data['width'][i])
        height = int(ocr_data['height'][i])

        if width <= 0 or height <= 0:
            continue

        word_rect = {
            "x1": left,
            "y1": top,
            "x2": left + width,
            "y2": top + height,
        }

        # Badge zone overlap
        if _rect_overlap(word_rect, badge_rect):
            badge_overlaps.append({
                "word": word,
                "rect": word_rect,
                "confidence": conf,
            })

        # Margin violations
        violated = False
        violation_detail = {"word": word, "rect": word_rect, "sides": []}

        if left < side_margin:
            violation_detail["sides"].append("left")
            violated = True
        if (left + width) > (img_w - side_margin):
            violation_detail["sides"].append("right")
            violated = True
        if top < top_margin_px:
            violation_detail["sides"].append("top")
            violated = True

        if violated:
            margin_violations.append(violation_detail)

    # Deduplicate overlapping word rects for badge overlaps
    seen_badge = set()
    unique_badge = []
    for b in badge_overlaps:
        key = b['word']
        if key not in seen_badge:
            seen_badge.add(key)
            unique_badge.append(b)
    badge_overlaps = unique_badge

    # Build issues list from detections
    if badge_overlaps:
        words = [b['word'] for b in badge_overlaps]
        issues.append(
            f"Badge zone overlap: text detected in protected bottom 9mm — "
            f"words: {', '.join(words[:5])}"
        )

    if margin_violations:
        sides = set()
        for v in margin_violations:
            sides.update(v['sides'])
        issues.append(
            f"Margin violation: text outside 3mm safe zone on {', '.join(sorted(sides))} edge(s)"
        )

    # ── Step 7: Annotated image ───────────────────────────────────────────────
    try:
        annotation_path = _draw_annotations(
            cv_img.copy(), badge_rect, badge_overlaps,
            margin_violations, side_margin, top_margin_px,
            img_w, img_h, isbn, issues
        )
    except Exception as e:
        print(f"[checker] Annotation failed: {e}")
        annotation_path = None

    # ── Step 8: Confidence + status ───────────────────────────────────────────
    n_issues = len(issues)
    if n_issues == 0:
        status     = "PASS"
        confidence = 96
    else:
        status     = "REVIEW NEEDED"
        if n_issues == 1:
            confidence = 80
        elif n_issues == 2:
            confidence = 65
        else:
            confidence = 50

    # Badge overlap always forces REVIEW NEEDED
    if badge_overlaps:
        status = "REVIEW NEEDED"

    return {
        "isbn":              isbn,
        "status":            status,
        "confidence":        confidence,
        "issues":            issues,
        "badge_overlaps":    badge_overlaps,
        "margin_violations": margin_violations,
        "resolution_ok":     resolution_ok,
        "annotation_path":   annotation_path,
        "timestamp":         datetime.now().isoformat(),
    }


def _draw_annotations(
    img, badge_rect, badge_overlaps, margin_violations,
    side_margin, top_margin_px, img_w, img_h, isbn, issues
):
    """
    Draw visual annotations on the cover image and save to static/annotations/.
    Returns relative path string like 'annotations/isbn_timestamp.png'.
    """
    GOLD    = (76,  168, 201)   # BGR for #C9A84C
    RED     = (0,   0,   220)
    ORANGE  = (0,   140, 255)
    GREEN   = (94,  197, 34)
    WHITE   = (255, 255, 255)
    BLACK   = (0,   0,   0)

    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.4, img_h / 2400 * 0.7)
    thickness  = max(1, int(img_h / 1200))

    # Scale down very large images for annotation display (keep at most 1200px tall)
    display_scale = 1.0
    if img_h > 1200:
        display_scale = 1200 / img_h
        new_w = int(img_w * display_scale)
        new_h = int(img_h * display_scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    dh, dw = img.shape[:2]

    def scale_rect(r):
        return {
            "x1": int(r["x1"] * display_scale),
            "y1": int(r["y1"] * display_scale),
            "x2": int(r["x2"] * display_scale),
            "y2": int(r["y2"] * display_scale),
        }

    # Semi-transparent badge zone overlay
    overlay = img.copy()
    br = scale_rect(badge_rect)
    cv2.rectangle(overlay, (br["x1"], br["y1"]), (br["x2"], br["y2"]), (0, 0, 180), -1)
    cv2.addWeighted(overlay, 0.25, img, 0.75, 0, img)

    # Badge zone border + label
    cv2.rectangle(img, (br["x1"], br["y1"]), (br["x2"] - 1, br["y2"] - 1), RED, thickness + 1)
    label = "BADGE ZONE - PROTECTED"
    lx = br["x1"] + 4
    ly = br["y1"] - 6 if br["y1"] > 20 else br["y1"] + 18
    # shadow
    cv2.putText(img, label, (lx + 1, ly + 1), font, font_scale * 0.85, BLACK, thickness + 1)
    cv2.putText(img, label, (lx, ly), font, font_scale * 0.85, RED, thickness)

    # Badge overlap word boxes
    for overlap in badge_overlaps:
        r = scale_rect(overlap["rect"])
        cv2.rectangle(img, (r["x1"], r["y1"]), (r["x2"], r["y2"]), RED, thickness + 1)
        cv2.putText(img, overlap["word"], (r["x1"], r["y1"] - 4),
                    font, font_scale * 0.75, RED, thickness)

    # Margin violation boxes
    drawn_mv = set()
    for mv in margin_violations:
        key = (mv["rect"]["x1"], mv["rect"]["y1"])
        if key in drawn_mv:
            continue
        drawn_mv.add(key)
        r = scale_rect(mv["rect"])
        cv2.rectangle(img, (r["x1"], r["y1"]), (r["x2"], r["y2"]), ORANGE, thickness)

    # Safe margin guide lines (dashed appearance via dotted lines)
    sm = int(side_margin * display_scale)
    tm = int(top_margin_px * display_scale)
    line_color = GOLD
    lth = max(1, thickness - 1)
    # Left margin
    for y in range(0, dh, 12):
        cv2.line(img, (sm, y), (sm, min(y + 6, dh)), line_color, lth)
    # Right margin
    for y in range(0, dh, 12):
        cv2.line(img, (dw - sm, y), (dw - sm, min(y + 6, dh)), line_color, lth)
    # Top margin
    for x in range(0, dw, 12):
        cv2.line(img, (x, tm), (min(x + 6, dw), tm), line_color, lth)

    # Outer border — green if PASS, red if issues
    border_color = GREEN if not issues else RED
    cv2.rectangle(img, (0, 0), (dw - 1, dh - 1), border_color, thickness + 2)

    # Status label top-left
    status_text = "PASS" if not issues else "REVIEW NEEDED"
    cv2.rectangle(img, (0, 0), (int(dw * 0.38), 28), border_color, -1)
    cv2.putText(img, status_text, (6, 20), font, font_scale * 0.9, WHITE, thickness)

    # Save
    os.makedirs("static/annotations", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_isbn = isbn.replace("/", "_").replace("\\", "_")
    filename = f"{safe_isbn}_{ts}.png"
    full_path = os.path.join("static", "annotations", filename)
    cv2.imwrite(full_path, img)

    return f"annotations/{filename}"

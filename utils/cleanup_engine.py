"""
Cleanup Engine: Orchestrates the visual cleanup pipeline.

CRITICAL SAFETY:
1. Foreground protection mask is ALWAYS applied.
2. Content integrity check runs after cleanup.
3. If cleanup damages content (>5% foreground lost), original page is restored.
4. Blank pages are never output.
5. All pages are processed — no page is ever skipped.
"""
import os
import uuid
import tempfile
import shutil
import cv2
import numpy as np

from utils.watermark_detector import detect_watermarks, detect_foreground_mask
from utils.inpaint_engine import apply_safe_cleanup, apply_manual_rects


def process_all_pages(file_path, settings, file_id, preview_dir):
    """
    Master function: processes ALL pages of a PDF/image.
    
    1. Renders every page as an image.
    2. Runs visual cleanup on each page.
    3. Saves each cleaned page as JPEG in preview_dir.
    4. Returns a cleanup report for every page.
    
    Returns: list of dicts [{page, path, watermark_removed, ad_removed, content_safe}]
    """
    from utils.renderer import render_pdf_to_images, load_image_as_page
    
    os.makedirs(preview_dir, exist_ok=True)
    
    is_pdf = file_path.lower().endswith(".pdf")
    
    # Render all pages at 150 DPI for cleanup
    dpi = 150
    if is_pdf:
        pages = render_pdf_to_images(file_path, dpi=dpi)
    else:
        pages = load_image_as_page(file_path)
    
    if not pages:
        return []
    
    # Process each page
    cleanup_report = []
    
    for page in pages:
        page_num = page["page_num"]
        src_path = page["path"]
        
        # Output path in preview dir
        out_filename = f"gen_{file_id}_p{page_num}.jpg"
        out_path = os.path.join(preview_dir, out_filename)
        
        # Run cleanup
        result = _cleanup_single_page(src_path, out_path, settings, page)
        result["page"] = page_num
        result["path"] = out_path
        
        cleanup_report.append(result)
    
    return cleanup_report


def _cleanup_single_page(src_path, out_path, settings, page_info):
    """
    Cleans a single page image. Returns a report dict.
    """
    from PIL import Image
    
    mode = settings.get("mode", "visual-cleanup")
    auto_watermark = settings.get("auto_watermark", True)
    auto_teacher = settings.get("auto_teacher", True)
    auto_footer = settings.get("auto_footer", True)
    auto_ad = settings.get("auto_ad", True)
    fill_method = settings.get("fill_method", "white")
    strength = settings.get("cleanup_strength", "medium")
    preserve_fg = settings.get("preserve_foreground", True)

    # Strength → threshold mapping
    strength_map = {
        "low":    {"thresh_lo": 210, "thresh_hi": 245, "inpaint_radius": 3},
        "medium": {"thresh_lo": 190, "thresh_hi": 242, "inpaint_radius": 5},
        "high":   {"thresh_lo": 170, "thresh_hi": 240, "inpaint_radius": 7},
        "ultra":  {"thresh_lo": 150, "thresh_hi": 245, "inpaint_radius": 10},
    }
    params = strength_map.get(strength, strength_map["medium"])

    report = {
        "watermark_removed": False,
        "ad_removed": False,
        "content_safe": True,
        "status": "original"
    }

    did_cleanup = False
    temp_out = os.path.join(tempfile.gettempdir(), f"tmp_clean_{uuid.uuid4()}.png")

    # ===== AUTO CLEANUP =====
    if mode in ("visual-cleanup", "auto-background"):
        if auto_watermark or auto_teacher or auto_footer or auto_ad:
            safe_mask, fg_count = detect_watermarks(
                src_path,
                thresh_lo=params["thresh_lo"],
                thresh_hi=params["thresh_hi"],
                protect_dark=True,
                detect_ad=auto_ad,
                detect_footer=auto_footer,
                detect_teacher=auto_teacher,
                preserve_colored=preserve_fg
            )

            if safe_mask is not None and cv2.countNonZero(safe_mask) > 0:
                apply_safe_cleanup(
                    src_path, temp_out, safe_mask,
                    fill_method=fill_method,
                    inpaint_radius=params["inpaint_radius"]
                )

                # === CONTENT INTEGRITY CHECK ===
                if not verify_content_integrity(src_path, temp_out, fg_count):
                    # Cleanup damaged content — restore original
                    shutil.copy2(src_path, temp_out)
                    report["content_safe"] = False
                    report["status"] = "cleanup_rejected_to_protect_content"
                else:
                    report["watermark_removed"] = True
                    report["ad_removed"] = auto_ad
                    report["status"] = "cleaned"

                did_cleanup = True

    # Save final result as JPEG
    if did_cleanup and os.path.exists(temp_out):
        # Final blank-page safety check
        if _is_page_blank(temp_out):
            # Restore original — never output blank page
            Image.open(src_path).convert("RGB").save(out_path, "JPEG", quality=82)
            report["status"] = "blank_rejected_restored_original"
            report["content_safe"] = True
        else:
            Image.open(temp_out).convert("RGB").save(out_path, "JPEG", quality=82)
    else:
        # No cleanup needed — save original as JPEG
        Image.open(src_path).convert("RGB").save(out_path, "JPEG", quality=82)
        report["status"] = "no_cleanup_needed"

    # Cleanup temp file
    try:
        if os.path.exists(temp_out):
            os.remove(temp_out)
    except Exception:
        pass

    return report


def process_cleanup(pages, settings):
    """
    Legacy interface: Takes page dicts and settings. Returns cleaned page dicts.
    Used by manual brush/rect operations.
    """
    out_dir = os.path.join(tempfile.gettempdir(), "outputs")
    os.makedirs(out_dir, exist_ok=True)

    mode = settings.get("mode", "visual-cleanup")
    auto_watermark = settings.get("auto_watermark", True)
    auto_teacher = settings.get("auto_teacher", True)
    auto_footer = settings.get("auto_footer", True)
    auto_ad = settings.get("auto_ad", True)
    fill_method = settings.get("fill_method", "white")
    strength = settings.get("cleanup_strength", "medium")
    preserve_fg = settings.get("preserve_foreground", True)
    manual_rects = settings.get("manual_rects", [])
    apply_scope = settings.get("apply_scope", "current")
    page_range_str = settings.get("page_range", "")

    strength_map = {
        "low":    {"thresh_lo": 210, "thresh_hi": 245, "inpaint_radius": 3},
        "medium": {"thresh_lo": 190, "thresh_hi": 242, "inpaint_radius": 5},
        "high":   {"thresh_lo": 170, "thresh_hi": 240, "inpaint_radius": 7},
        "ultra":  {"thresh_lo": 150, "thresh_hi": 245, "inpaint_radius": 10},
    }
    params = strength_map.get(strength, strength_map["medium"])

    cleaned_pages = []

    for page in pages:
        src_path = page["path"]
        out_path = os.path.join(out_dir, f"cleaned_{uuid.uuid4()}.png")
        did_cleanup = False

        # ===== AUTO CLEANUP =====
        if mode in ("visual-cleanup", "auto-background"):
            if auto_watermark or auto_teacher or auto_footer or auto_ad:
                safe_mask, fg_count = detect_watermarks(
                    src_path,
                    thresh_lo=params["thresh_lo"],
                    thresh_hi=params["thresh_hi"],
                    protect_dark=True,
                    detect_ad=auto_ad,
                    detect_footer=auto_footer,
                    detect_teacher=auto_teacher,
                    preserve_colored=preserve_fg
                )

                if safe_mask is not None and cv2.countNonZero(safe_mask) > 0:
                    apply_safe_cleanup(
                        src_path, out_path, safe_mask,
                        fill_method=fill_method,
                        inpaint_radius=params["inpaint_radius"]
                    )

                    if not verify_content_integrity(src_path, out_path, fg_count):
                        shutil.copy2(src_path, out_path)

                    did_cleanup = True

        # ===== MANUAL ERASE =====
        if manual_rects:
            should_apply = False
            if apply_scope == "all":
                should_apply = True
            elif apply_scope == "current" and page["page_num"] == 1:
                should_apply = True
            elif apply_scope == "range":
                should_apply = _is_page_in_range(page["page_num"], page_range_str)

            if should_apply:
                source = out_path if did_cleanup else src_path
                manual_out = os.path.join(out_dir, f"manual_{uuid.uuid4()}.png")
                apply_manual_rects(
                    source, manual_out, manual_rects,
                    fill_method=fill_method,
                    inpaint_radius=params["inpaint_radius"],
                    preserve_foreground=preserve_fg
                )

                if not verify_content_integrity(src_path, manual_out, None):
                    shutil.copy2(src_path, manual_out)

                out_path = manual_out
                did_cleanup = True

        # If no cleanup was needed, use original page as-is
        if not did_cleanup:
            cleaned_pages.append(page)
        else:
            if _is_page_blank(out_path):
                cleaned_pages.append(page)  # Restore original
            else:
                cleaned_pages.append({
                    "page_num": page["page_num"],
                    "width": page["width"],
                    "height": page["height"],
                    "path": out_path
                })

    return cleaned_pages


def verify_content_integrity(original_path, cleaned_path, original_fg_count=None):
    """
    Checks that the cleaned page hasn't lost more than 5% of foreground content.
    Returns True if content is safe, False if cleanup damaged it.
    """
    try:
        orig_img = cv2.imread(original_path)
        clean_img = cv2.imread(cleaned_path)
        if orig_img is None or clean_img is None:
            return False

        if original_fg_count is None:
            orig_fg = detect_foreground_mask(orig_img)
            original_fg_count = int(cv2.countNonZero(orig_fg))

        if original_fg_count == 0:
            return True  # Nothing to protect

        clean_fg = detect_foreground_mask(clean_img)
        clean_fg_count = int(cv2.countNonZero(clean_fg))

        # STRICT RULE: Reject if more than 5% of foreground was removed
        if clean_fg_count < original_fg_count * 0.95:
            return False

        return True
    except Exception:
        return False


def _is_page_blank(image_path):
    """Check if a page image is essentially blank (>95% white)."""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return True
        total_pixels = img.shape[0] * img.shape[1]
        white_pixels = np.sum(img > 240)
        return (white_pixels / total_pixels) > 0.95
    except Exception:
        return True


def _is_page_in_range(page_num, range_str):
    """Parse '1-5, 8, 10-12' and check if page_num is included."""
    if not range_str:
        return False
    try:
        for part in range_str.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                if int(lo) <= page_num <= int(hi):
                    return True
            else:
                if int(part) == page_num:
                    return True
    except (ValueError, TypeError):
        pass
    return False

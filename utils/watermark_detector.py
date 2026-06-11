"""
Watermark Detector with Foreground Protection Mask and Targeted Cleanup.

ARCHITECTURE:
1. Build a robust foreground protection mask (text, lines, tables, colors).
2. Use TARGETED detectors for watermarks — never blanket-erase.
3. safe_cleanup_mask = watermark_mask - foreground_mask.

CRITICAL RULE: Never erase protected foreground pixels.
"""
import cv2
import numpy as np


def detect_foreground_mask(img, preserve_colored=True):
    """
    Builds a comprehensive foreground protection mask that covers:
    - Black/dark text (using adaptive thresholding for robustness)
    - Red answer text / Blue section headings / Yellow bars (if preserve_colored=True)
    - Table borders / grid lines / vertical rules
    - Diagrams and math symbols
    """
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # 1. Dark text — Adaptive Thresholding ignores large blurry watermarks
    dark_mask = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 21, 10
    )
    mask = cv2.bitwise_or(mask, dark_mask)

    # 2. Saturated colored text (red answers, blue headings, yellow bars, green text)
    if preserve_colored:
        sat_channel = hsv[:, :, 1]
        val_channel = hsv[:, :, 2]
        colored_mask = np.zeros((h, w), dtype=np.uint8)
        # Saturation > 50 and Value < 240 is likely intentional colored content
        colored_mask[(sat_channel > 50) & (val_channel < 240)] = 255

        # Top-Hat transform: extract ONLY thin/sharp features (text)
        # and ignore massive colored blobs (watermarks)
        kernel_th = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        colored_text_only = cv2.morphologyEx(colored_mask, cv2.MORPH_TOPHAT, kernel_th)

        mask = cv2.bitwise_or(mask, colored_text_only)

    # 3. Lines and borders
    # Horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    h_lines = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, h_kernel)
    mask = cv2.bitwise_or(mask, h_lines)

    # Vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    v_lines = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, v_kernel)
    mask = cv2.bitwise_or(mask, v_lines)

    # 4. Dilate the foreground mask by 7px to create a strict safety buffer
    dilate_kernel = np.ones((7, 7), np.uint8)
    mask = cv2.dilate(mask, dilate_kernel, iterations=1)

    return mask


def _detect_faint_watermark(gray, thresh_lo, thresh_hi, min_blob_area=3000):
    """
    Detector 1: Faint pixel range detector.
    Watermarks are typically semi-transparent — they sit in a narrow gray range
    between pure white background (~250-255) and dark text (~0-150).
    
    This targets ONLY the faint pixel range, NOT all non-white pixels.
    Then filters for large connected blobs (watermarks are large, noise is small).
    """
    # Target the faint watermark range
    faint_mask = cv2.inRange(gray, thresh_lo, thresh_hi)

    # Use a LARGE morphological closing to connect nearby faint pixels into blobs
    # This specifically targets large, sparse watermarks
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    faint_mask = cv2.morphologyEx(faint_mask, cv2.MORPH_CLOSE, close_kernel, iterations=3)

    # Filter out small noise — keep only large connected blobs
    contours, _ = cv2.findContours(faint_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered_mask = np.zeros_like(faint_mask)
    for cnt in contours:
        if cv2.contourArea(cnt) >= min_blob_area:
            cv2.drawContours(filtered_mask, [cnt], -1, 255, -1)

    return filtered_mask

def _detect_background_logo(gray, img_h, img_w):
    """
    Detector 2: Large centered background logo/image.
    Looks for a large faint shape in the center region of the page.
    """
    # Define center region (middle 60% of page)
    cx1 = int(img_w * 0.2)
    cx2 = int(img_w * 0.8)
    cy1 = int(img_h * 0.2)
    cy2 = int(img_h * 0.8)

    center_region = gray[cy1:cy2, cx1:cx2]

    # Look for pixels in the faint range within center
    faint_center = cv2.inRange(center_region, 180, 245)

    # Morphological close to form blobs
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    faint_center = cv2.morphologyEx(faint_center, cv2.MORPH_CLOSE, kernel, iterations=3)

    # Only keep very large blobs (background logos are huge)
    contours, _ = cv2.findContours(faint_center, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    logo_mask = np.zeros((img_h, img_w), dtype=np.uint8)
    min_area = (img_h * img_w) * 0.01  # Must be at least 1% of page area

    for cnt in contours:
        if cv2.contourArea(cnt) >= min_area:
            # Offset contour back to full image coordinates
            cnt_offset = cnt.copy()
            cnt_offset[:, :, 0] += cx1
            cnt_offset[:, :, 1] += cy1
            cv2.drawContours(logo_mask, [cnt_offset], -1, 255, -1)

    return logo_mask


def _detect_ad_blocks(img, min_area_ratio=0.02):
    """
    Detector 3: Advertisement/promotional blocks.
    Ads are large, highly saturated rectangular regions with banner-like aspect ratios.
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]

    # Threshold high saturation areas
    _, sat_thresh = cv2.threshold(sat, 80, 255, cv2.THRESH_BINARY)

    # Close gaps to form solid blocks
    sat_kernel = np.ones((15, 15), np.uint8)
    ad_mask_raw = cv2.morphologyEx(sat_thresh, cv2.MORPH_CLOSE, sat_kernel, iterations=3)

    # Find contours and filter by size/shape
    contours, _ = cv2.findContours(ad_mask_raw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ad_mask = np.zeros((h, w), dtype=np.uint8)
    min_area = h * w * min_area_ratio

    for cnt in contours:
        area = cv2.contourArea(cnt)
        x, y, cw, ch = cv2.boundingRect(cnt)

        # Must be reasonably large
        if area < min_area:
            continue

        # Must be wide (banner-like) or large block
        if cw < w * 0.3:
            continue

        # Must have a reasonable height
        if ch < 30:
            continue

        cv2.rectangle(ad_mask, (x, y), (x + cw, y + ch), 255, -1)

    return ad_mask


def _detect_footer_banner(gray, img, img_h, img_w):
    """
    Detector 4: Footer/banner strip.
    Instead of blindly masking the bottom 8%, analyze the bottom region
    for dense content that looks like a banner (dark strip, promotional text).
    """
    footer_mask = np.zeros((img_h, img_w), dtype=np.uint8)

    # Analyze bottom 12% of the page
    footer_y_start = int(img_h * 0.88)
    footer_region = gray[footer_y_start:, :]

    if footer_region.size == 0:
        return footer_mask

    # Check if the footer region has significantly different characteristics
    # than the rest of the page (dark strip, colored band, etc.)
    mean_footer = np.mean(footer_region)
    mean_page = np.mean(gray[:footer_y_start, :])

    # If footer region is notably darker than the page body, it's likely a banner
    if mean_footer < mean_page - 30:
        cv2.rectangle(footer_mask, (0, footer_y_start), (img_w, img_h), 255, -1)
        return footer_mask

    # Also check for a thin dark strip at the very bottom (common footer line)
    bottom_strip = gray[int(img_h * 0.95):, :]
    if bottom_strip.size > 0:
        dark_ratio = np.sum(bottom_strip < 180) / bottom_strip.size
        if dark_ratio > 0.3:
            cv2.rectangle(footer_mask, (0, int(img_h * 0.95)), (img_w, img_h), 255, -1)

    return footer_mask


def _detect_teacher_name_regions(gray, img_h, img_w):
    """
    Detector 5: Teacher name / phone number in corners.
    Instead of blindly masking top-right, detect small isolated text blocks
    in any corner region. These are typically small, isolated from main content.
    """
    corner_mask = np.zeros((img_h, img_w), dtype=np.uint8)

    # Define corner regions (each corner: 30% width, 10% height)
    corners = [
        (int(img_w * 0.70), 0, img_w, int(img_h * 0.10)),          # top-right
        (0, 0, int(img_w * 0.30), int(img_h * 0.10)),              # top-left
        (int(img_w * 0.70), int(img_h * 0.90), img_w, img_h),      # bottom-right
        (0, int(img_h * 0.90), int(img_w * 0.30), img_h),          # bottom-left
    ]

    for (x1, y1, x2, y2) in corners:
        region = gray[y1:y2, x1:x2]
        if region.size == 0:
            continue

        # Check if there's a small amount of dark content (text)
        dark_pixels = np.sum(region < 150)
        total_pixels = region.size
        dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0

        # Teacher name: small amount of text (1-15% dark pixels)
        # Too much dark = probably real content
        # Too little = empty corner
        if 0.01 < dark_ratio < 0.15:
            cv2.rectangle(corner_mask, (x1, y1), (x2, y2), 255, -1)

    return corner_mask


def detect_watermarks(image_path, thresh_lo=190, thresh_hi=242, protect_dark=True,
                      detect_ad=True, detect_footer=True, detect_teacher=True,
                      preserve_colored=True):
    """
    Detects watermark regions using TARGETED detectors, then subtracts
    the foreground protection mask to create a safe_cleanup_mask.

    Returns: (safe_mask, foreground_pixel_count)
    """
    img = cv2.imread(image_path)
    if img is None:
        return None, 0

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Step 1: Build robust foreground protection mask
    fg_mask = detect_foreground_mask(img, preserve_colored=preserve_colored)
    fg_count = int(cv2.countNonZero(fg_mask))

    # Step 2: Initialize total cleanup mask
    total_cleanup_mask = np.zeros((h, w), dtype=np.uint8)

    # --- Detector 1: Faint watermark pixels ---
    # Map strength thresholds to minimum blob area
    blob_area_map = {
        (210, 245): 5000,   # low
        (190, 242): 3000,   # medium
        (170, 240): 1500,   # high
        (150, 245): 800,    # ultra
    }
    min_blob = blob_area_map.get((thresh_lo, thresh_hi), 3000)

    faint_mask = _detect_faint_watermark(gray, thresh_lo, thresh_hi, min_blob_area=min_blob)
    total_cleanup_mask = cv2.bitwise_or(total_cleanup_mask, faint_mask)

    # --- Detector 2: Background logo ---
    logo_mask = _detect_background_logo(gray, h, w)
    total_cleanup_mask = cv2.bitwise_or(total_cleanup_mask, logo_mask)

    # --- Detector 3: Advertisement blocks ---
    if detect_ad:
        ad_mask = _detect_ad_blocks(img)
        total_cleanup_mask = cv2.bitwise_or(total_cleanup_mask, ad_mask)

    # --- Detector 4: Footer banner ---
    if detect_footer:
        footer_mask = _detect_footer_banner(gray, img, h, w)
        total_cleanup_mask = cv2.bitwise_or(total_cleanup_mask, footer_mask)

    # --- Detector 5: Teacher name / phone in corners ---
    if detect_teacher:
        teacher_mask = _detect_teacher_name_regions(gray, h, w)
        total_cleanup_mask = cv2.bitwise_or(total_cleanup_mask, teacher_mask)

    # Step 3: CRITICAL — strictly subtract foreground from total cleanup mask
    safe_mask = cv2.bitwise_and(total_cleanup_mask, cv2.bitwise_not(fg_mask))

    # Step 4: Remove tiny isolated noise regions (< 100 pixels)
    contours, _ = cv2.findContours(safe_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) < 100:
            cv2.drawContours(safe_mask, [cnt], -1, 0, -1)

    return safe_mask, fg_count


def detect_watermark_rects(image_path, thresh_lo=180, thresh_hi=240, protect_dark=True):
    """
    Legacy interface — returns bounding rects of watermark regions.
    """
    safe_mask, _ = detect_watermarks(image_path, thresh_lo, thresh_hi, protect_dark)
    if safe_mask is None:
        return []

    contours, _ = cv2.findContours(safe_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > 15 and h > 15:
            rects.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    return rects

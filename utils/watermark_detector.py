"""
Watermark Detector with Foreground Protection Mask and Advanced Ad/Footer Detection.

CRITICAL RULE: Never erase protected foreground pixels.
Creates a safe_cleanup_mask = watermark_mask - foreground_mask.
"""
import cv2
import numpy as np


def detect_foreground_mask(img, preserve_colored=True):
    """
    Builds a comprehensive foreground protection mask that covers:
    - Black/dark text (using adaptive thresholding for robustness)
    - Red answer text / Blue section headings (if preserve_colored=True)
    - Table borders / grid lines
    """
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 1. Dark text (Adaptive Thresholding ignores large blurry watermarks and shadows)
    # Block size 21, C=10 gives a good balance of finding sharp text edges.
    dark_mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                      cv2.THRESH_BINARY_INV, 21, 10)
    mask = cv2.bitwise_or(mask, dark_mask)
    
    # 2. Saturated colored text (red answers, blue headings, yellow bars)
    if preserve_colored:
        sat_channel = hsv[:, :, 1]
        val_channel = hsv[:, :, 2]
        colored_mask = np.zeros((h, w), dtype=np.uint8)
        # Saturation > 50 and Value < 240 is likely intentional colored content
        colored_mask[(sat_channel > 50) & (val_channel < 240)] = 255
        
        # CRITICAL FIX: The above mask protects ALL saturated colors, including massive faint watermarks!
        # We apply a Morphological Top-Hat transform to extract ONLY thin/sharp features (text) 
        # and ignore massive colored blobs (watermarks).
        kernel_th = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        colored_text_only = cv2.morphologyEx(colored_mask, cv2.MORPH_TOPHAT, kernel_th)
        
        mask = cv2.bitwise_or(mask, colored_text_only)
    
    # 3. Lines and borders (use morphological operations)
    # Horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    h_lines = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, h_kernel)
    mask = cv2.bitwise_or(mask, h_lines)
    
    # Vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    v_lines = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, v_kernel)
    mask = cv2.bitwise_or(mask, v_lines)
    
    # 4. Dilate the foreground mask by 3-5px to create a strict safety buffer
    dilate_kernel = np.ones((5, 5), np.uint8)
    mask = cv2.dilate(mask, dilate_kernel, iterations=1)
    
    return mask


def detect_watermarks(image_path, thresh_lo=180, thresh_hi=240, protect_dark=True, 
                      detect_ad=True, detect_footer=True, detect_teacher=True,
                      preserve_colored=True):
    """
    Detects faint watermark regions, ad blocks, footers, and teacher names,
    and returns a safe_cleanup_mask that has foreground content strictly subtracted out.
    
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

    # --- Detector 1: Universal Background & Watermark Removal (Pixel-to-Pixel) ---
    # The user requested to remove ALL background images and ANY color of watermark.
    # Instead of guessing specific colors, we target ALL pixels that are not pure white.
    # This aggressively targets all backgrounds, watermarks, and images for removal.
    
    # Target anything that isn't already near-white
    universal_bg_mask = cv2.inRange(gray, 0, 250)
    
    # Add it to the total cleanup mask
    total_cleanup_mask = cv2.bitwise_or(total_cleanup_mask, universal_bg_mask)

    # --- Detector 2: Advertisement / Promotional Block ---
    # Look for highly saturated blocks (typically bottom half or center)
    if detect_ad:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        # Ads usually have large solid colored areas
        _, sat_thresh = cv2.threshold(sat, 80, 255, cv2.THRESH_BINARY)
        sat_kernel = np.ones((15, 15), np.uint8)
        ad_mask = cv2.morphologyEx(sat_thresh, cv2.MORPH_CLOSE, sat_kernel, iterations=3)
        # Limit to larger blocks
        contours, _ = cv2.findContours(ad_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            # Ad heuristic: wide block, reasonably tall, often in bottom half
            if cw > w * 0.4 and ch > 50 and y > h * 0.3:
                cv2.rectangle(total_cleanup_mask, (x, y), (x+cw, y+ch), 255, -1)

    # --- Detector 3: Repeated Footer / Banner ---
    # Look for dense text or dark blocks at the very bottom
    if detect_footer:
        footer_y = int(h * 0.92) # Bottom 8%
        cv2.rectangle(total_cleanup_mask, (0, footer_y), (w, h), 255, -1)

    # --- Detector 4: Top-Right Teacher Name ---
    # Look for text blocks in top right corner
    if detect_teacher:
        tr_x = int(w * 0.75)
        tr_y_end = int(h * 0.08) # Top right 25% w, 8% h
        cv2.rectangle(total_cleanup_mask, (tr_x, 0), (w, tr_y_end), 255, -1)

    # Step 3: CRITICAL — strictly subtract foreground from the total cleanup mask
    # This ensures that even if an ad or footer overlaps with real content, the content is safe.
    safe_mask = cv2.bitwise_and(total_cleanup_mask, cv2.bitwise_not(fg_mask))
    
    # Step 4: Remove tiny isolated noise regions (< 100 pixels)
    contours, _ = cv2.findContours(safe_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) < 100:
            cv2.drawContours(safe_mask, [cnt], -1, 0, -1)
    
    return safe_mask, fg_count


def detect_watermark_rects(image_path, thresh_lo=180, thresh_hi=240, protect_dark=True):
    """
    Legacy interface.
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

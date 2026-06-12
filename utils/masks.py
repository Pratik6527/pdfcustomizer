import cv2
import numpy as np

def create_color_channel_mask(img: np.ndarray, watermark_color: str) -> np.ndarray:
    """Creates a mask for the specified watermark color."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    color_ranges = {
        "blue":    [(90, 50, 50),   (130, 255, 255)],
        "red":     [(0, 100, 100),  (10, 255, 255)],   
        "green":   [(40, 50, 50),   (80, 255, 255)],
        "cyan":    [(80, 50, 50),   (100, 255, 255)],
        "magenta": [(140, 50, 50),  (165, 255, 255)],
        "yellow":  [(20, 100, 100), (35, 255, 255)],
        "gray":    [(0, 0, 120),    (180, 30, 220)],
    }
    
    lo_color, hi_color = color_ranges.get(watermark_color, color_ranges["blue"])
    lo = np.array(lo_color, dtype=np.uint8)
    hi = np.array(hi_color, dtype=np.uint8)
    
    color_mask = cv2.inRange(hsv, lo, hi)
    kernel = np.ones((3, 3), np.uint8)
    color_mask = cv2.dilate(color_mask, kernel, iterations=1)
    
    return color_mask

def apply_fft_filter(img: np.ndarray, region_box=None) -> np.ndarray:
    """Applies FFT to suppress periodic watermarks like diagonal repeating text."""
    result = img.copy()
    
    if region_box:
        x, y, w, h = region_box
        roi = img[y:y+h, x:x+w]
    else:
        roi = img
        x, y = 0, 0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float64)
    f_transform = np.fft.fft2(gray)
    f_shifted   = np.fft.fftshift(f_transform)
    magnitude   = np.abs(f_shifted)
    
    rows, cols = gray.shape
    cx, cy     = cols // 2, rows // 2
    
    notch_filter = np.ones((rows, cols), dtype=np.float64)
    log_magnitude = np.log1p(magnitude)
    
    mean_mag = np.mean(log_magnitude)
    std_mag  = np.std(log_magnitude)
    spike_threshold = mean_mag + 5.0 * std_mag
    
    spike_mask = log_magnitude > spike_threshold
    
    dc_radius = min(rows, cols) // 10
    Y, X = np.ogrid[:rows, :cols]
    dc_zone = (X - cx) ** 2 + (Y - cy) ** 2 <= dc_radius ** 2
    spike_mask[dc_zone] = False
    
    for r, c in zip(*np.where(spike_mask)):
        notch_radius = 8
        y_start = max(0, r - notch_radius)
        y_end   = min(rows, r + notch_radius + 1)
        x_start = max(0, c - notch_radius)
        x_end   = min(cols, c + notch_radius + 1)
        
        yy, xx = np.mgrid[y_start:y_end, x_start:x_end]
        gauss  = 1 - np.exp(-((xx - c)**2 + (yy - r)**2) / (2 * (notch_radius/2)**2))
        notch_filter[y_start:y_end, x_start:x_end] *= gauss
    
    f_filtered  = f_shifted * notch_filter
    f_unshifted = np.fft.ifftshift(f_filtered)
    cleaned     = np.real(np.fft.ifft2(f_unshifted))
    cleaned     = np.clip(cleaned, 0, 255).astype(np.uint8)
    
    if len(roi.shape) == 3:
        roi_yuv     = cv2.cvtColor(roi, cv2.COLOR_BGR2YUV)
        roi_yuv[:, :, 0] = cleaned
        cleaned_bgr = cv2.cvtColor(roi_yuv, cv2.COLOR_YUV2BGR)
    else:
        cleaned_bgr = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)
    
    if region_box:
        result[y:y+h, x:x+w] = cleaned_bgr
    else:
        result = cleaned_bgr
    
    return result

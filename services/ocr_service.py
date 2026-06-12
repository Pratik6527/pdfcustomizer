import cv2
import numpy as np
from utils.logging_config import logger

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

def create_protected_content_mask(image_path: str) -> np.ndarray:
    """
    Uses OCR (Tesseract) to detect actual text (questions, options, headings).
    Returns a binary mask where text regions are 255, meaning DO NOT erase.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None
        
    h, w = img.shape[:2]
    protected_mask = np.zeros((h, w), dtype=np.uint8)
    
    if not TESSERACT_AVAILABLE:
        logger.warning("pytesseract not installed. Content protection will rely solely on adaptive thresholding.")
        # Fallback to simple adaptive thresholding if no OCR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        return mask
        
    try:
        # Get bounding boxes for text
        # PSM 11: Sparse text. Find as much text as possible in no particular order.
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config='--psm 11')
        
        n_boxes = len(data['level'])
        for i in range(n_boxes):
            text = data['text'][i].strip()
            # Only protect boxes that actually contain alphanumeric characters
            if len(text) > 0 and any(c.isalnum() for c in text):
                (x, y, w_box, h_box) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                
                # Expand bounding box slightly to ensure descenders/ascenders are safe
                pad = 4
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(w, x + w_box + pad)
                y2 = min(h, y + h_box + pad)
                
                cv2.rectangle(protected_mask, (x1, y1), (x2, y2), 255, -1)
                
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        # Return empty mask if OCR fails, so we don't block everything, but cleanup will use CV masks
        
    return protected_mask

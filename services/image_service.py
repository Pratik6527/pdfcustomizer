import base64
import cv2
import numpy as np
import shutil
from utils.file_store import get_preview_dir

def image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def is_page_blank(image_path: str, threshold: float = 0.99) -> bool:
    """Checks if a page is entirely blank (white)."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return True
    white_pixels = np.sum(img > 250)
    total_pixels = img.size
    return (white_pixels / total_pixels) > threshold

def load_image_as_page(image_path: str, file_id: str):
    """Copies an uploaded image into the preview directory as page 1."""
    preview_dir = get_preview_dir(file_id)
    out_path = preview_dir / f"gen_{file_id}_p1.jpg"
    
    img = cv2.imread(image_path)
    if img is not None:
        cv2.imwrite(str(out_path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        h, w = img.shape[:2]
        return [{"page_num": 1, "path": str(out_path), "width": w, "height": h}]
    else:
        # Fallback to direct copy if cv2 fails to read
        shutil.copy2(image_path, out_path)
        return [{"page_num": 1, "path": str(out_path), "width": 800, "height": 1000}]

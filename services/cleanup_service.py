import os
import cv2
import numpy as np
from PIL import Image
from utils.file_store import get_temp_path
from utils.masks import apply_fft_filter, create_color_channel_mask
from services.ai_detection_service import detect_watermarks_ai
from services.ocr_service import create_protected_content_mask
from services.image_service import is_page_blank

def apply_safe_cleanup(src_path, out_path, remove_mask, protected_mask, fill_method="white", inpaint_radius=5):
    """
    Applies cleanup using a removal mask, but strictly prevents altering the protected_mask.
    """
    img = cv2.imread(src_path)
    if img is None:
        return
        
    # Remove protected pixels from the removal mask
    if protected_mask is not None:
        safe_mask = cv2.bitwise_and(remove_mask, cv2.bitwise_not(protected_mask))
    else:
        safe_mask = remove_mask

    if cv2.countNonZero(safe_mask) == 0:
        cv2.imwrite(out_path, img)
        return

    if fill_method == "white":
        img[safe_mask > 0] = [255, 255, 255]
    elif fill_method == "inpaint":
        img = cv2.inpaint(img, safe_mask, inpaint_radius, cv2.INPAINT_TELEA)

    cv2.imwrite(out_path, img)

def process_single_page(src_path: str, out_path: str, settings: dict, page_num: int):
    """
    Core cleanup pipeline combining AI, OCR, and CV.
    """
    use_ai = settings.get("use_ai_detection", True)
    provider = settings.get("ai_provider", "hybrid")
    protect_ocr = settings.get("protect_content_ocr", True)
    fill_method = settings.get("fill_method", "white")
    
    img = cv2.imread(src_path)
    if img is None:
        return {"status": "error"}
        
    img_h, img_w = img.shape[:2]
    working_img = img.copy()
    did_cleanup = False
    
    # 1. AI Detection
    ai_result = {"remove_regions": []}
    if use_ai:
        ai_result = detect_watermarks_ai(src_path, provider, settings.get("openai_api_key", ""), settings.get("gemini_api_key", ""))
    
    
    # 2. OCR Content Protection
    protected_mask = None
    if protect_ocr:
        protected_mask = create_protected_content_mask(src_path)
    
    # 3. Process AI Regions
    direct_fill_mask = np.zeros((img_h, img_w), dtype=np.uint8)
    inpaint_mask = np.zeros((img_h, img_w), dtype=np.uint8)
    
    for region in ai_result.get("remove_regions", []):
        bbox = region.get("bbox", {})
        x = int(bbox.get("x", 0) * img_w)
        y = int(bbox.get("y", 0) * img_h)
        w = int(bbox.get("w", 0) * img_w)
        h = int(bbox.get("h", 0) * img_h)
        
        # Clamp to bounds
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = max(1, min(w, img_w - x))
        h = max(1, min(h, img_h - y))
        
        strategy = region.get("removal_method", "white_fill")
        
        if strategy in ["white_fill", "background_reconstruct"]:
            cv2.rectangle(direct_fill_mask, (x, y), (x + w, y + h), 255, -1)
        elif strategy == "inpaint":
            cv2.rectangle(inpaint_mask, (x, y), (x + w, y + h), 255, -1)
        elif strategy == "frequency_filter":
            working_img = apply_fft_filter(working_img, (x, y, w, h))
            did_cleanup = True
        elif strategy == "color_channel_remove":
            color_mask = create_color_channel_mask(working_img[y:y+h, x:x+w], "blue") # default to blue
            if protected_mask is not None:
                safe_color_mask = cv2.bitwise_and(color_mask, cv2.bitwise_not(protected_mask[y:y+h, x:x+w]))
            else:
                safe_color_mask = color_mask
            working_img[y:y+h, x:x+w][safe_color_mask > 0] = [255, 255, 255]
            did_cleanup = True

    # 4. Apply Spatial Masks
    temp_img_path = get_temp_path()
    cv2.imwrite(temp_img_path, working_img)
    
    if cv2.countNonZero(direct_fill_mask) > 0 or cv2.countNonZero(inpaint_mask) > 0:
        combined = cv2.bitwise_or(direct_fill_mask, inpaint_mask)
        apply_safe_cleanup(temp_img_path, temp_img_path, combined, protected_mask, fill_method)
        did_cleanup = True

    # 5. Final guard against blank page
    if is_page_blank(temp_img_path):
        Image.open(src_path).convert("RGB").save(out_path, "JPEG", quality=90)
        status = "blank_rejected"
    elif did_cleanup:
        Image.open(temp_img_path).convert("RGB").save(out_path, "JPEG", quality=90)
        status = "cleaned"
    else:
        Image.open(src_path).convert("RGB").save(out_path, "JPEG", quality=90)
        status = "no_cleanup_needed"

    if os.path.exists(temp_img_path):
        os.remove(temp_img_path)

    return {
        "status": status,
        "page_num": page_num,
        "path": out_path,
        "ai_regions": ai_result.get("remove_regions", [])
    }

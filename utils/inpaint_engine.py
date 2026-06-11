"""
Inpaint Engine: Applies cleanup ONLY to the safe_cleanup_mask.
Never touches foreground content.

Supports fill methods: white, inpaint, blur, background.
"""
import cv2
import numpy as np


def apply_safe_cleanup(image_path, out_path, safe_mask, fill_method="white", inpaint_radius=5, preserve_foreground=False):
    """
    Applies the selected fill method ONLY to pixels marked 255 in safe_mask.
    Foreground content (where safe_mask is 0) is never touched unless preserve_foreground is False.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image at {image_path}")

    if safe_mask is None or cv2.countNonZero(safe_mask) == 0:
        # Nothing to clean — save original
        cv2.imwrite(out_path, img)
        return

    if preserve_foreground:
        from utils.watermark_detector import detect_foreground_mask
        fg_mask = detect_foreground_mask(img)
        safe_mask = cv2.bitwise_and(safe_mask, cv2.bitwise_not(fg_mask))

    if fill_method == "white":
        # Only whiten pixels in the safe mask
        img[safe_mask == 255] = [255, 255, 255]

    elif fill_method == "inpaint":
        img = cv2.inpaint(img, safe_mask, inpaint_radius, cv2.INPAINT_TELEA)

    elif fill_method == "blur":
        # Create a blurred version and blend only in safe areas
        blurred = cv2.GaussianBlur(img, (31, 31), 0)
        img[safe_mask == 255] = blurred[safe_mask == 255]

    elif fill_method == "background":
        # Sample the median background color from light areas and fill
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bg_pixels = img[gray > 240]
        if len(bg_pixels) > 0:
            bg_color = np.median(bg_pixels, axis=0).astype(np.uint8)
        else:
            bg_color = np.array([255, 255, 255], dtype=np.uint8)
        img[safe_mask == 255] = bg_color

    cv2.imwrite(out_path, img)


def apply_manual_rects(image_path, out_path, rects, fill_method="white", inpaint_radius=5, preserve_foreground=False):
    """
    Applies manual rectangular erasures to the image.
    rects is a list of dicts: [{"box": {"x": 100, "y": 200, "width": 50, "height": 50}}]
    """
    try:
        img = cv2.imread(image_path)
        if img is None: return False
        mask = np.zeros(img.shape[:2], dtype=np.uint8)

        for item in rects:
            box = item.get("box", {})
            x = int(box.get("x", 0))
            y = int(box.get("y", 0))
            w = int(box.get("width", 0))
            h = int(box.get("height", 0))
            if w > 0 and h > 0:
                cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)

        apply_safe_cleanup(image_path, out_path, mask, fill_method, inpaint_radius, preserve_foreground)
        return True
    except Exception as e:
        print(f"Manual rect error: {e}")
        return False


def apply_brush_strokes(image_path, out_path, points, brush_size=20, fill_method="white", preserve_foreground=False):
    """
    Applies a manual brush stroke (polyline) to the image.
    points is a list of dicts: [{"x": 100, "y": 200}, ...]
    """
    try:
        img = cv2.imread(image_path)
        if img is None: return False
        mask = np.zeros(img.shape[:2], dtype=np.uint8)

        # Convert points to numpy array for polylines
        if points:
            pts = np.array([[int(p["x"]), int(p["y"])] for p in points], np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=int(brush_size), lineType=cv2.LINE_AA)

        apply_safe_cleanup(image_path, out_path, mask, fill_method, 5, preserve_foreground)
        return True
    except Exception as e:
        print(f"Brush stroke error: {e}")
        return False

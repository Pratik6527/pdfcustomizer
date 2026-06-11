import io
import os
import zipfile
from PIL import Image

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


def export_pages_as_images(pdf_bytes, page_selection="all", dpi=200, fmt="png"):
    """
    Convert generated PDF pages into images and return:
      - If single page: (image_bytes, None)  — raw image bytes
      - If multiple pages: (None, zip_bytes)  — ZIP archive bytes
    
    Args:
        pdf_bytes (bytes): Raw PDF bytes.
        page_selection (str|int|list): "all", a page number (1-indexed int), or list of page numbers.
        dpi (int): Render DPI.
        fmt (str): "png" or "jpg"/"jpeg".
    
    Returns:
        tuple: (single_image_bytes_or_None, zip_bytes_or_None)
    """
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) is required for image export.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # Resolve page selection to a list of 0-indexed page indices
    if page_selection == "all":
        indices = list(range(total_pages))
    elif isinstance(page_selection, int):
        idx = max(0, min(page_selection - 1, total_pages - 1))
        indices = [idx]
    elif isinstance(page_selection, list):
        indices = [max(0, min(p - 1, total_pages - 1)) for p in page_selection]
    else:
        indices = [0]

    pil_fmt = "JPEG" if fmt.lower() in ["jpg", "jpeg"] else "PNG"
    ext = "jpg" if pil_fmt == "JPEG" else "png"

    rendered_images = []
    for idx in indices:
        page = doc[idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        if pil_fmt == "JPEG":
            img_pil.save(buf, format="JPEG", quality=92)
        else:
            img_pil.save(buf, format="PNG")
        buf.seek(0)
        rendered_images.append((f"page_{idx + 1}.{ext}", buf.read()))

    doc.close()

    if len(rendered_images) == 1:
        # Return single image bytes directly
        return rendered_images[0][1], None
    else:
        # Pack into ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in rendered_images:
                zf.writestr(name, data)
        zip_buf.seek(0)
        return None, zip_buf.read()

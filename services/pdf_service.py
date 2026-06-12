import fitz
from PIL import Image
import os
from pathlib import Path
from utils.file_store import get_preview_dir

def render_pdf_to_images(pdf_path: str, file_id: str, dpi=200):
    """
    Renders each page of a PDF to a high-quality JPEG in the preview directory.
    Returns a list of dicts: [{"page_num": int, "path": str, "width": int, "height": int}]
    """
    preview_dir = get_preview_dir(file_id)
    doc = fitz.open(pdf_path)
    pages_info = []
    
    # 200 DPI is a good balance between OCR quality and speed
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Convert to PIL Image
        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        
        out_path = preview_dir / f"gen_{file_id}_p{page_num + 1}.jpg"
        img.save(str(out_path), "JPEG", quality=90)
        
        pages_info.append({
            "page_num": page_num + 1,
            "path": str(out_path),
            "width": pix.width,
            "height": pix.height
        })
        
    doc.close()
    return pages_info

import os
import fitz
import tempfile
import uuid
from PIL import Image

def render_pdf_to_images(pdf_path, dpi=200, specific_page=None):
    """
    Renders each page of a PDF to a high-quality image.
    Returns a list of dicts containing image paths and metadata.
    """
    out_dir = os.path.join(tempfile.gettempdir(), "pages")
    os.makedirs(out_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    pages = []
    
    # 200 DPI gives a zoom factor of ~2.77
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    
    for page_num in range(len(doc)):
        if specific_page is not None and (page_num + 1) != specific_page:
            continue
        
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Save as PNG
        img_id = str(uuid.uuid4())
        img_path = os.path.join(out_dir, f"{img_id}.png")
        pix.save(img_path)
        
        pages.append({
            "page_num": page_num + 1,
            "width": pix.width,
            "height": pix.height,
            "path": img_path
        })
    
    doc.close()
    return pages

def load_image_as_page(img_path):
    """
    Wrapper for when the user uploads an image instead of a PDF.
    """
    out_dir = os.path.join(tempfile.gettempdir(), "pages")
    os.makedirs(out_dir, exist_ok=True)
    
    img = Image.open(img_path)
    # Ensure RGB
    if img.mode != "RGB":
        img = img.convert("RGB")
        
    img_id = str(uuid.uuid4())
    out_path = os.path.join(out_dir, f"{img_id}.png")
    img.save(out_path)
    
    return [{
        "page_num": 1,
        "width": img.width,
        "height": img.height,
        "path": out_path
    }]

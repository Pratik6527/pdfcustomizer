from utils.renderer import render_pdf_to_images, load_image_as_page
from utils.cleanup_engine import process_cleanup
from utils.pdf_exporter import generate_pdf_from_images
import os
import uuid
import tempfile

def run_cleanup_pipeline(file_path, file_type, config):
    """
    Main orchestrator for Visual Cleanup Mode.
    1. Extracts pages to images
    2. Runs cleanup_engine to inpaint
    3. Exports to PDF
    """
    # 1. Render to images
    if file_type == "application/pdf":
        pages = render_pdf_to_images(file_path, dpi=200)
    else:
        pages = load_image_as_page(file_path)
        
    # 2. Process Cleanup (Inpainting)
    cleaned_pages = process_cleanup(pages, config)
    
    # 3. Export to PDF
    out_dir = os.path.join(tempfile.gettempdir(), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_pdf = os.path.join(out_dir, f"final_{uuid.uuid4()}.pdf")
    
    cleaned_paths = [p["path"] for p in cleaned_pages]
    
    final_pdf_path = generate_pdf_from_images(cleaned_paths, out_pdf, dpi=200)
    
    return final_pdf_path

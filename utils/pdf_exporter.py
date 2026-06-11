"""
PDF Exporter with Smart Hybrid Output

Architecture:
- generate_final_pdf(): Builds a new PDF from cleaned page images.
  Uses the original PDF for page dimensions. Never modifies the original in-place.
- smart_hybrid_export(): Legacy interface that combines render+cleanup+export.
- File size optimization: JPEG compression, DPI control, post-export compression check.
"""
import fitz
import os
import uuid
import tempfile
import cv2
from PIL import Image

from utils.renderer import render_pdf_to_images, load_image_as_page
from utils.cleanup_engine import process_cleanup


def generate_final_pdf(file_path, cleaned_page_paths, out_path, quality_mode="smart"):
    """
    Builds a new PDF from cleaned page images.
    
    Uses the original PDF to determine correct page dimensions.
    Each cleaned page image is compressed to JPEG and placed onto a
    correctly-sized blank page.
    
    Args:
        file_path: Path to the original uploaded file (PDF or image)
        cleaned_page_paths: List of image paths, one per page, in order
        out_path: Where to save the final PDF
        quality_mode: 'smart', 'small', 'balanced', 'high', 'ultra'
    
    Returns: True on success, False on failure
    """
    try:
        # Determine JPEG quality based on mode
        jpeg_quality_map = {
            "small": 65,
            "smart": 78,
            "balanced": 78,
            "high": 85,
            "ultra": 95,
        }
        jpeg_quality = jpeg_quality_map.get(quality_mode, 78)

        is_pdf = file_path.lower().endswith(".pdf")
        
        # Get original page dimensions
        page_dimensions = []
        if is_pdf:
            try:
                orig_doc = fitz.open(file_path)
                for i in range(len(orig_doc)):
                    rect = orig_doc[i].rect
                    page_dimensions.append((rect.width, rect.height))
                orig_doc.close()
            except Exception:
                page_dimensions = []
        
        # If we couldn't get dimensions, fall back to image dimensions
        if not page_dimensions:
            for img_path in cleaned_page_paths:
                try:
                    img = Image.open(img_path)
                    # Convert pixel dimensions to points (72 DPI)
                    # Assuming pages were rendered at 150 DPI
                    w_pts = img.width * 72 / 150
                    h_pts = img.height * 72 / 150
                    page_dimensions.append((w_pts, h_pts))
                except Exception:
                    page_dimensions.append((595, 842))  # A4 fallback
        
        # Ensure we have dimensions for every page
        while len(page_dimensions) < len(cleaned_page_paths):
            page_dimensions.append(page_dimensions[-1] if page_dimensions else (595, 842))
        
        # Build new PDF from scratch
        doc = fitz.open()
        
        for i, img_path in enumerate(cleaned_page_paths):
            if not os.path.exists(img_path):
                # Page image missing — skip would violate "never skip a page"
                # Use a white placeholder page instead
                pw, ph = page_dimensions[i]
                doc.new_page(width=pw, height=ph)
                continue
            
            pw, ph = page_dimensions[i]
            
            # Compress to JPEG for file size optimization
            temp_jpg = os.path.join(tempfile.gettempdir(), f"exp_{uuid.uuid4()}.jpg")
            try:
                Image.open(img_path).convert("RGB").save(
                    temp_jpg, "JPEG", quality=jpeg_quality, optimize=True
                )
            except Exception:
                # If JPEG conversion fails, use original image
                temp_jpg = img_path
            
            # Create page with original dimensions
            page = doc.new_page(width=pw, height=ph)
            rect = fitz.Rect(0, 0, pw, ph)
            
            try:
                page.insert_image(rect, filename=temp_jpg)
            except Exception:
                # Fallback: try with original image
                try:
                    page.insert_image(rect, filename=img_path)
                except Exception:
                    pass  # Page will be blank but present
            
            # Cleanup temp jpg
            if temp_jpg != img_path:
                try:
                    os.remove(temp_jpg)
                except Exception:
                    pass
        
        # Save with optimization
        doc.save(out_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
        # File size check: if output > input * 1.5, run compression pass
        if is_pdf and os.path.exists(file_path) and os.path.exists(out_path):
            orig_size = os.path.getsize(file_path)
            gen_size = os.path.getsize(out_path)
            
            if orig_size > 0 and gen_size > orig_size * 1.5:
                _compress_pdf(out_path, jpeg_quality=max(55, jpeg_quality - 15))
        
        return True
        
    except Exception as e:
        print(f"generate_final_pdf error: {e}")
        import traceback
        traceback.print_exc()
        return False


def _compress_pdf(pdf_path, jpeg_quality=65):
    """
    Additional compression pass on an existing PDF.
    Re-saves with aggressive garbage collection.
    """
    try:
        doc = fitz.open(pdf_path)
        temp_path = pdf_path + ".tmp"
        doc.save(temp_path, garbage=4, deflate=True, clean=True,
                 linear=True)
        doc.close()
        
        # Replace original with compressed version
        os.replace(temp_path, pdf_path)
    except Exception:
        # If compression fails, keep the original
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def smart_hybrid_export(file_path, out_path, settings, quality_mode="smart",
                        file_id=None, preview_dir=None):
    """
    Legacy export interface.
    
    If preview images exist in preview_dir (from process_all_pages), uses those.
    Otherwise renders and cleans all pages fresh.
    """
    try:
        is_pdf = file_path.lower().endswith(".pdf")
        
        # Determine DPI based on quality mode
        dpi_map = {
            "small": 120,
            "smart": 150,
            "balanced": 150,
            "high": 200,
            "ultra": 300,
        }
        dpi = dpi_map.get(quality_mode, 150)
        
        # If it's just an image, simple workflow
        if not is_pdf:
            pages = load_image_as_page(file_path)
            cleaned_pages = process_cleanup(pages, settings)
            cleaned_paths = [p["path"] for p in cleaned_pages]
            return generate_final_pdf(file_path, cleaned_paths, out_path, quality_mode)

        # For PDFs: check if pre-generated pages exist
        page_count = 0
        try:
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
        except Exception:
            page_count = 1

        # Collect cleaned page paths
        cleaned_paths = []
        
        for p_num in range(1, page_count + 1):
            # Check for pre-generated preview
            gen_file = None
            if preview_dir and file_id:
                gen_file = os.path.join(preview_dir, f"gen_{file_id}_p{p_num}.jpg")
                if not os.path.exists(gen_file):
                    gen_file = None
            
            if gen_file:
                cleaned_paths.append(gen_file)
            else:
                # Page hasn't been processed — render and clean it now
                pages = render_pdf_to_images(file_path, dpi=dpi, specific_page=p_num)
                if pages:
                    cleaned_p = process_cleanup(pages, settings)
                    cleaned_paths.append(cleaned_p[0]["path"])
                else:
                    # Render failed — use a blank page (will be caught by generate_final_pdf)
                    cleaned_paths.append("")
        
        return generate_final_pdf(file_path, cleaned_paths, out_path, quality_mode)
        
    except Exception as e:
        print(f"Hybrid export error: {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_pdf_from_images(image_paths, output_path, dpi=200):
    """
    Legacy method: Simply stitches images into a PDF. 
    Only used as a fallback if the file uploaded was an image, not a PDF.
    """
    if not image_paths:
        return False
    
    doc = fitz.open()
    for img_path in image_paths:
        img = fitz.open(img_path)
        rect = img[0].rect
        pdfbytes = img.convert_to_pdf()
        img.close()
        
        imgPDF = fitz.open("pdf", pdfbytes)
        page = doc.new_page(width=rect.width, height=rect.height)
        page.show_pdf_page(rect, imgPDF, 0)
        imgPDF.close()
        
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return True

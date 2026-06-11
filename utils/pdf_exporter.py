"""
PDF Exporter with Smart Hybrid Output

Optimizes export by keeping vector pages unchanged and only replacing/patching
raster images where necessary. Uses JPEG compression for massive space savings.
"""
import fitz
import os
import uuid
import tempfile
import cv2
from PIL import Image

from utils.renderer import render_pdf_to_images, load_image_as_page
from utils.cleanup_engine import process_cleanup

def smart_hybrid_export(file_path, out_path, settings, quality_mode="smart", file_id=None, preview_dir=None):
    """
    Exports the PDF using the Hybrid strategy.
    Instead of rendering every page to PNG, it renders the pages, runs cleanup,
    and if a page was cleaned, it replaces that page in the original PDF with 
    a compressed JPEG. If the page was untouched, it retains the original vector page.
    """
    try:
        is_pdf = file_path.lower().endswith(".pdf")
        
        # If it's just an image, fallback to simple raster workflow
        if not is_pdf:
            pages = load_image_as_page(file_path)
            cleaned_pages = process_cleanup(pages, settings)
            cleaned_paths = [p["path"] for p in cleaned_pages]
            return generate_pdf_from_images(cleaned_paths, out_path, dpi=200)

        doc = fitz.open(file_path)
        
        # Determine DPI and JPEG Quality based on mode
        dpi = 150
        jpeg_quality = 80
        
        if quality_mode == "small":
            dpi = 120
            jpeg_quality = 65
        elif quality_mode == "balanced":
            dpi = 150
            jpeg_quality = 78
        elif quality_mode == "high":
            dpi = 200
            jpeg_quality = 85
        elif quality_mode == "ultra":
            dpi = 300
            jpeg_quality = 95

        # We will iterate through the PDF pages.
        # If a corresponding generated page exists in preview_dir, it means it was cleaned or edited.
        # If it doesn't exist, it means the user never even scrolled to it OR it didn't need cleanup.
        # Wait, if they never scrolled to it, it hasn't been generated yet!
        # So we MUST run process_cleanup on the untouched pages now just to be safe if auto-settings are on!
        
        # Actually, for an accurate export of "all pages", we should process ALL pages here,
        # but if a page is already in `preview_dir`, we use that one (because it might have manual brush strokes!).
        pages = render_pdf_to_images(file_path, dpi=dpi)
        
        cleaned_pages = []
        for p in pages:
            p_num = p["page_num"]
            prev_file = os.path.join(preview_dir, f"prev_{file_id}_p{p_num}.jpg") if (preview_dir and file_id) else None
            
            if prev_file and os.path.exists(prev_file):
                # Use the already generated (and potentially brush-edited) preview image!
                cleaned_pages.append({
                    "page_num": p_num,
                    "width": p["width"],
                    "height": p["height"],
                    "path": prev_file
                })
            else:
                # Page hasn't been generated/previewed yet. Run it through the auto-cleanup now.
                cleaned_p = process_cleanup([p], settings)[0]
                cleaned_pages.append(cleaned_p)
        
        # Iterate and replace pages in the PDF ONLY if they were modified
        for i, (orig, clean) in enumerate(zip(pages, cleaned_pages)):
            if orig["path"] != clean["path"]:
                # The page was cleaned/modified!
                # We need to replace it in the PDF document.
                
                # Compress the cleaned PNG to a high-quality JPEG
                temp_jpg = os.path.join(tempfile.gettempdir(), f"opt_{uuid.uuid4()}.jpg")
                Image.open(clean["path"]).convert("RGB").save(temp_jpg, "JPEG", quality=jpeg_quality, optimize=True)
                
                # Get dimensions of original page to maintain exact sizing
                page = doc[i]
                rect = page.rect
                
                # Create a new blank page with same dimensions immediately after
                doc.insert_page(i + 1, width=rect.width, height=rect.height)
                new_page = doc[i + 1]
                
                # Insert the compressed JPEG onto the new page
                new_page.insert_image(rect, filename=temp_jpg)
                
                # Delete the original heavy/dirty page
                doc.delete_page(i)
                
                # Cleanup temp jpg
                try:
                    os.remove(temp_jpg)
                except Exception:
                    pass

        # Save and optimize the final document
        # garbage=4 (Remove unused objects)
        # deflate=True (Compress streams)
        # clean=True (Clean and sanitize contents)
        doc.save(out_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
        return True
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

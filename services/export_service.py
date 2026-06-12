import fitz
import os

def export_to_pdf(original_pdf_path: str, image_paths: list, output_pdf_path: str):
    """
    Rebuilds the PDF using the cleaned images.
    Tries to match original dimensions if original_pdf_path is valid.
    """
    out_doc = fitz.open()
    
    orig_doc = None
    if original_pdf_path and os.path.exists(original_pdf_path) and original_pdf_path.endswith('.pdf'):
        try:
            orig_doc = fitz.open(original_pdf_path)
        except Exception:
            pass
            
    for i, img_path in enumerate(image_paths):
        if not os.path.exists(img_path):
            continue
            
        img_doc = fitz.open(img_path)
        pdf_bytes = img_doc.convert_to_pdf()
        img_pdf = fitz.open("pdf", pdf_bytes)
        img_page = img_pdf[0]
        
        # Match dimensions if possible
        if orig_doc and i < len(orig_doc):
            orig_page = orig_doc[i]
            out_page = out_doc.new_page(width=orig_page.rect.width, height=orig_page.rect.height)
            out_page.show_pdf_page(out_page.rect, img_pdf, 0)
        else:
            out_page = out_doc.new_page(width=img_page.rect.width, height=img_page.rect.height)
            out_page.show_pdf_page(out_page.rect, img_pdf, 0)
            
        img_doc.close()
        img_pdf.close()
        
    if orig_doc:
        orig_doc.close()
        
    if len(out_doc) > 0:
        out_doc.save(output_pdf_path, garbage=3, deflate=True)
        out_doc.close()
        return True
    return False

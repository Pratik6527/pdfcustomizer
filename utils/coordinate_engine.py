import os
import fitz
import difflib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import uuid

# Register fonts
FONT_DIR = os.path.join("static", "fonts")
try:
    pdfmetrics.registerFont(TTFont('NotoSans', os.path.join(FONT_DIR, 'NotoSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('NotoSansBengali', os.path.join(FONT_DIR, 'NotoSansBengali-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', os.path.join(FONT_DIR, 'NotoSansDevanagari-Regular.ttf')))
except Exception as e:
    print(f"Warning: Failed to load custom fonts: {e}")

def similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

def extract_and_rebuild_pdf(input_path, output_path, config):
    """
    Extracts foreground blocks with PyMuPDF, applies spatial deduplication
    and cross-page frequency filtering, then rebuilds with ReportLab.
    """
    doc = fitz.open(input_path)
    
    # Pass 1: Extract all blocks and their coordinates
    all_pages_blocks = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        # get_text("dict") returns blocks, lines, spans
        page_dict = page.get_text("dict")
        blocks = []
        
        for block in page_dict.get("blocks", []):
            if block.get("type") == 0:  # Text block
                block_text = ""
                min_x, min_y, max_x, max_y = 9999, 9999, -1, -1
                font_size = 11
                
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            block_text += text + " "
                            bbox = span["bbox"]
                            min_x = min(min_x, bbox[0])
                            min_y = min(min_y, bbox[1])
                            max_x = max(max_x, bbox[2])
                            max_y = max(max_y, bbox[3])
                            font_size = span.get("size", font_size)
                            
                block_text = block_text.strip()
                if block_text:
                    blocks.append({
                        "text": block_text,
                        "x": min_x,
                        "y": min_y,
                        "w": max_x - min_x,
                        "h": max_y - min_y,
                        "size": font_size
                    })
        
        all_pages_blocks.append(blocks)

    # Pass 2: Cross-Page Frequency Filtering (AI Token Filtering alternative)
    # Tally block texts across pages
    frequency_map = {}
    for blocks in all_pages_blocks:
        for b in blocks:
            text_key = b["text"]
            # Disregard very short strings like page numbers
            if len(text_key) > 4:
                frequency_map[text_key] = frequency_map.get(text_key, 0) + 1

    # Pass 3: Rebuild with ReportLab
    c = canvas.Canvas(output_path, pagesize=A4)
    # We will assume standard A4 size, but ideally we'd match the source doc size
    # Actually, let's use the source doc size for the first page
    if len(doc) > 0:
        src_rect = doc[0].rect
        c.setPageSize((src_rect.width, src_rect.height))

    for page_num, blocks in enumerate(all_pages_blocks):
        src_rect = doc[page_num].rect
        page_height = src_rect.height
        
        # Sort blocks top-to-bottom
        blocks.sort(key=lambda b: b["y"])
        
        # Spatial Deduplication
        cleaned_blocks = []
        for i, b in enumerate(blocks):
            # Check frequency map
            if frequency_map.get(b["text"], 0) > 2:
                continue # Skip repetitive background headers/watermarks
                
            is_duplicate = False
            for prev_b in cleaned_blocks:
                # Check Y-axis overlap (within 12 pixels)
                if abs(b["y"] - prev_b["y"]) < 12:
                    # Check string similarity
                    if similar(b["text"], prev_b["text"]) > 0.85:
                        is_duplicate = True
                        break
            if not is_duplicate:
                cleaned_blocks.append(b)

        # Draw blocks
        for b in cleaned_blocks:
            # Detect script to select font
            font_name = "NotoSans"
            # Simple heuristic for Bengali/Hindi
            if any("\u0980" <= char <= "\u09FF" for char in b["text"]):
                font_name = "NotoSansBengali"
            elif any("\u0900" <= char <= "\u097F" for char in b["text"]):
                font_name = "NotoSansDevanagari"
                
            try:
                c.setFont(font_name, b["size"])
                # ReportLab Y is from bottom, fitz Y is from top
                draw_y = page_height - b["y"] - b["size"]
                c.drawString(b["x"], draw_y, b["text"])
            except Exception as e:
                # Fallback to standard font if unicode fails or font missing
                c.setFont("Helvetica", b["size"])
                c.drawString(b["x"], page_height - b["y"] - b["size"], b["text"].encode('ascii', 'ignore').decode())
                
        c.showPage()
        
    c.save()
    doc.close()
    return output_path

import os
import google.generativeai as genai
from PIL import Image

def extract_html_with_vision(image_path):
    """
    Takes an image path, sends it to Gemini 1.5 Pro Vision API,
    and returns a clean, structural HTML representation of the document.
    """
    # Requires GEMINI_API_KEY to be set in environment
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please add it to your .env file.")
        
    genai.configure(api_key=api_key)
    
    # We use gemini-1.5-flash as it is fast and supports vision, 
    # but gemini-1.5-pro is better for complex documents.
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    img = Image.open(image_path)
    
    prompt = """
    You are an expert document parser. Look closely at the provided document page image. 
    Analyze, read, and extract all questions, multiple-choice options (A, B, C, D), headings, 
    list items, tables, and math equations accurately. 
    
    CRITICAL: Ignore and completely strip out background watermarks, light grey text logos, 
    advertisement text, or specific instructor names. 
    
    Reconstruct the document as well-structured, semantic HTML using clean CSS styling 
    (e.g., tables as <table>, math expressions properly spaced, lists as <ul>/<li>). 
    Ensure Bengali scripts retain correct spelling and word structure.
    
    Output ONLY the valid HTML content inside a <body> tag. Do not include markdown codeblocks (```html).
    Just return the raw HTML string.
    """
    
    response = model.generate_content([prompt, img])
    
    html_content = response.text
    
    # Clean up any potential markdown formatting
    if html_content.startswith("```html"):
        html_content = html_content[7:]
    if html_content.endswith("```"):
        html_content = html_content[:-3]
        
    return html_content.strip()

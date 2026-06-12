import json
import base64
import re
from pathlib import Path
from utils.logging_config import logger
from utils.security import get_openai_api_key, get_gemini_api_key

SYSTEM_PROMPT = """You are a forensic document cleanup analyst. Identify only unwanted overlay content that is not part of the real educational document. Remove-region examples include teacher names, coaching center names, phone numbers, watermarks, diagonal repeated branding, business details, footer ads, promotional banners, logos, social links, and unrelated images. Preserve all questions, options, subject headings, chapter/topic names, tables, diagrams, formulas, answer choices, page numbers if part of the document, and exam text. Return only strict JSON. Do not explain."""

USER_PROMPT = """Analyze this document page carefully.

Identify every watermark, promotional content, or non-original overlay that should be removed.

Respond with ONLY this JSON structure (no other text):
{
  "page_number": 1,
  "document_content": {
    "heading": "",
    "subject": "",
    "topic": "",
    "question_regions": [],
    "option_regions": [],
    "table_regions": [],
    "diagram_regions": [],
    "formula_regions": [],
    "must_preserve_regions": []
  },
  "remove_regions": [
    {
      "type": "watermark | teacher_name | coaching_name | phone_number | diagonal_text | footer_ad | corner_branding | logo_overlay | stamp | unrelated_image",
      "text": "Text content here",
      "reason": "Why it should be removed",
      "bbox": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
      "confidence": 0.9,
      "removal_method": "inpaint | white_fill | background_reconstruct | frequency_filter | color_channel_remove"
    }
  ],
  "safe_to_remove": true
}

NOTE: Bbox values should be percentages from 0.0 to 1.0. For example, x:0.1 means 10% from the left.
"""

def extract_json(text: str) -> dict:
    try:
        text = re.sub(r'^```json\s*', '', text.strip(), flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text.strip(), flags=re.MULTILINE)
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}. Raw text: {text}")
        return None

def detect_with_openai(image_path: str, api_key: str) -> dict:
    import openai
    try:
        client = openai.OpenAI(api_key=api_key)
        
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        ext = Path(image_path).suffix.lower()
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}}
                ]}
            ],
            max_tokens=2000,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        return extract_json(result_text)
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return None

def detect_with_gemini(image_path: str, api_key: str) -> dict:
    import google.generativeai as genai
    import PIL.Image
    try:
        genai.configure(api_key=api_key)
        # Using gemini-1.5-pro or gemini-1.5-flash for vision
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        img = PIL.Image.open(image_path)
        
        prompt = SYSTEM_PROMPT + "\n\n" + USER_PROMPT
        
        response = model.generate_content([prompt, img])
        return extract_json(response.text)
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None

def detect_watermarks_ai(image_path: str, provider: str = "hybrid") -> dict:
    """
    Main entry point for AI detection.
    Provider can be: "openai", "gemini", or "hybrid".
    Hybrid will try OpenAI first, fallback to Gemini.
    """
    openai_key = get_openai_api_key()
    gemini_key = get_gemini_api_key()
    
    result = None
    
    if provider in ["openai", "hybrid"] and openai_key:
        logger.info(f"Trying OpenAI for {Path(image_path).name}")
        result = detect_with_openai(image_path, openai_key)
        
    if not result and provider in ["gemini", "hybrid"] and gemini_key:
        logger.info(f"Trying Gemini for {Path(image_path).name}")
        result = detect_with_gemini(image_path, gemini_key)
        
    if not result:
        logger.warning(f"AI detection failed or no keys for {Path(image_path).name}")
        return {"safe_to_remove": False, "remove_regions": []}
        
    return result

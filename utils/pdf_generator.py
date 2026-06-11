import os
from playwright.sync_api import sync_playwright

def generate_pdf_from_html(html_body, output_path, config):
    """
    Takes a raw HTML body string, wraps it in a standard document template 
    (with Google Fonts embedded), and compiles it to a precise PDF using Playwright.
    """
    
    font_family = config.get("font_family", "'Noto Sans', sans-serif")
    font_size = config.get("font_size", "11pt")
    line_height = config.get("line_height", "1.5")
    margin_style = config.get("margin_style", "normal")
    
    # Map margin styles to CSS
    margin_css = "1in"
    if margin_style == "narrow":
        margin_css = "0.5in"
    elif margin_style == "wide":
        margin_css = "1.5in"
        
    header_text = config.get("header_text", "")
    footer_text = config.get("footer_text", "")
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Poppins:wght@400;600&family=Noto+Sans:wght@400;600&family=Noto+Sans+Bengali:wght@400;600&family=Noto+Sans+Devanagari:wght@400;600&display=swap" rel="stylesheet">
        <style>
            @page {{
                margin: {margin_css};
            }}
            body {{
                font-family: {font_family};
                font-size: {font_size};
                line-height: {line_height};
                color: #000;
                background: #fff;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 1rem;
            }}
            table, th, td {{
                border: 1px solid #000;
            }}
            th, td {{
                padding: 8px;
                text-align: left;
            }}
            .page-header {{
                text-align: center;
                font-size: 0.9em;
                color: #555;
                margin-bottom: 2rem;
                border-bottom: 1px solid #ccc;
                padding-bottom: 10px;
            }}
            .page-footer {{
                text-align: center;
                font-size: 0.9em;
                color: #555;
                margin-top: 2rem;
                border-top: 1px solid #ccc;
                padding-top: 10px;
            }}
        </style>
    </head>
    <body>
        {"<div class='page-header'>" + header_text + "</div>" if header_text else ""}
        
        {html_body}
        
        {"<div class='page-footer'>" + footer_text + "</div>" if footer_text else ""}
    </body>
    </html>
    """
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_template, wait_until="networkidle")
        
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={"top": margin_css, "bottom": margin_css, "left": margin_css, "right": margin_css}
        )
        
        browser.close()
        
    return output_path

# Document Cleanup Tool

Premium PDF/Image watermark cleanup tool with AI-powered page-by-page visual processing.

## Features

- **Visual Watermark Cleanup** — Detects and removes watermarks, background logos, teacher names, phone numbers, ad banners, footer strips
- **Foreground Protection** — Never erases questions, options, tables, borders, headings, or colored text
- **Manual Tools** — Rectangle select and brush erase for manual cleanup
- **Scroll Preview** — Side-by-side original and cleaned preview with scroll-based page navigation
- **Smart Export** — Optimized PDF output with configurable DPI and compression

## Tech Stack

- **Backend**: Python/Flask + PyMuPDF + OpenCV + Pillow
- **Frontend**: Vanilla HTML/CSS/JS + PDF.js
- **Deploy**: Vercel-ready (serverless Python)

## Project Structure

```
├── api/
│   └── index.py          # Flask app with all API routes
├── utils/
│   ├── watermark_detector.py  # Targeted watermark detection
│   ├── cleanup_engine.py      # Page-by-page cleanup pipeline
│   ├── pdf_exporter.py        # PDF generation & optimization
│   ├── inpaint_engine.py      # Pixel-level cleanup (fill/inpaint)
│   └── renderer.py            # PDF-to-image rendering
├── static/
│   ├── css/style.css     # All styles (dark mode, responsive)
│   ├── js/app.js         # Frontend logic
│   ├── assets/           # Developer avatar
│   └── fonts/            # Noto Sans / Bengali fonts
├── templates/
│   └── index.html        # Main HTML template
├── requirements.txt
├── vercel.json
└── runtime.txt
```

## Local Development

```bash
pip install -r requirements.txt
python api/index.py
# Open http://localhost:8000
```

## Deploy to Vercel

```bash
vercel deploy
```

Max upload: 4.4MB (Vercel serverless limit).

## Usage

1. Click "Upload Document"
2. Confirm document ownership
3. Configure cleanup settings (watermark, teacher name, footer, ads)
4. Click "Process Document"
5. Review cleaned preview (scroll to navigate pages)
6. Download the clean PDF

## License

For authorized document cleanup only.

---

Developed by **Mr. Pratik Mondal**

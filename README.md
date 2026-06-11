# Document Cleanup Tool

A premium web application for authorized PDF/Image watermark cleanup, manual erasing, and document rebuilding. 

## Key Features
- **Visual Cleanup Mode**: Safely removes faint backgrounds, watermarks, and banners while preserving original content layout, Bengali/Hindi fonts, tables, and spacing.
- **Manual Erase Mode**: Brush and Rectangle selection tools to easily erase unwanted sections. Changes can be applied to the current page, a specific range, or all pages (e.g. repeated footers).
- **Foreground Protection**: Automatically protects dark text, colored answers, borders, and lines so that real content is never accidentally erased.
- **Vercel & Mobile Ready**: 100% stateless backend using `/tmp` storage. Fully responsive UI featuring Glassmorphism, Google Fonts, and a Dual-Pane Preview.
- **Local PDF Rendering**: Uses PyMuPDF and PDF.js to render your documents cleanly.

## Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Run Locally**
   ```bash
   python api/index.py
   ```
   The app will run at `http://localhost:8000/`.

## Deployment to Vercel
This project is configured out-of-the-box for serverless deployment on Vercel.
1. Install the Vercel CLI or link via GitHub.
2. Ensure you deploy the root directory. Vercel will use `vercel.json` to route `/api/*` to the Python backend and serve `/static/*` via edge CDN.

## Important Note
This tool is intended for authorized document editing only. Please verify you own or have permission to modify any uploaded file.

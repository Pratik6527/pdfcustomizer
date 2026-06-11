"""
Flask Application: Premium Document Cleanup & Rebuilder
All temp files go to /tmp for Vercel compatibility.
"""
import os, sys, uuid, tempfile, traceback, time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, 
            template_folder=os.path.join(base_dir, "templates"), 
            static_folder=os.path.join(base_dir, "static"))
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64MB hard limit locally

# Temp directories (Vercel-safe)
_TMP = tempfile.gettempdir()
_UPL = os.path.join(_TMP, "uploads")
_PRV = os.path.join(_TMP, "previews")
_OUT = os.path.join(_TMP, "outputs")
_PGS = os.path.join(_TMP, "pages")
for d in [_UPL, _PRV, _OUT, _PGS]:
    os.makedirs(d, exist_ok=True)

ALLOWED = {'.pdf', '.png', '.jpg', '.jpeg', '.webp'}

@app.before_request
def auto_cleanup_old_files():
    """Clean files older than 10 mins to prevent No space left on device."""
    try:
        now = time.time()
        for d in [_UPL, _PRV, _OUT, _PGS]:
            if not os.path.exists(d): continue
            for filename in os.listdir(d):
                fp = os.path.join(d, filename)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 600:
                    try: os.remove(fp)
                    except Exception: pass
    except Exception:
        pass

def ensure_dict(value):
    if isinstance(value, dict): return value
    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
        return value[0]
    return {}

# ===== GLOBAL ERROR HANDLERS =====
@app.errorhandler(413)
@app.errorhandler(RequestEntityTooLarge)
def request_entity_too_large(error):
    return jsonify({
        "status": "error",
        "code": "FILE_TOO_LARGE",
        "message": "File is too large for Vercel serverless upload. Please compress your PDF or use a file under 4.4 MB."
    }), 413

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "code": "INTERNAL_ERROR",
        "message": "Something went wrong while processing the file on the server."
    }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "code": "NOT_FOUND",
        "message": "The requested API endpoint or file was not found."
    }), 404

# ===== ROUTES =====
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Only validates and saves the file. No heavy PDF rendering here."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files["file"]
        if not file or not file.filename:
            return jsonify({"error": "No file selected"}), 400

        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED:
            return jsonify({"error": f"Unsupported file type: {ext}"}), 400

        file_id = str(uuid.uuid4())
        saved_name = f"{file_id}_{filename}"
        file_path = os.path.join(_UPL, saved_name)
        file.save(file_path)

        fmt = "application/pdf" if ext == ".pdf" else "image"
        page_count = 1
        
        # Fast page count check for PDFs
        if fmt == "application/pdf":
            try:
                import fitz
                doc = fitz.open(file_path)
                page_count = doc.page_count
                doc.close()
            except ImportError:
                return jsonify({
                    "status": "error",
                    "code": "PDF_ENGINE_ERROR",
                    "message": "PDF engine failed to load on server. Please redeploy after fixing PyMuPDF dependency."
                }), 500
            except Exception:
                page_count = 1

        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)

        return jsonify({
            "status": "success",
            "message": "Upload successful",
            "file_id": file_id,
            "filename": filename,
            "format": fmt,
            "page_count": page_count,
            "original_size_mb": size_mb,
            "original_url": f"/api/download_raw/{saved_name}"
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/preview-page/<file_id>/<int:page_num>", methods=["GET"])
def preview_page(file_id, page_num):
    """Generates a cleanup preview for a single page (Lazy loading)."""
    try:
        settings_str = request.args.get("settings", "{}")
        import json
        settings = json.loads(settings_str)

        # Look for the original uploaded file
        # We don't know the exact filename extension, so we must find it
        upload_files = [f for f in os.listdir(_UPL) if f.startswith(f"{file_id}_")]
        if not upload_files:
            return jsonify({"status": "expired", "message": "Preview expired. Please upload again."}), 410
            
        file_path = os.path.join(_UPL, upload_files[0])
        preview_name = f"prev_{file_id}_p{page_num}.jpg"
        final_prev_path = os.path.join(_PRV, preview_name)
        
        # If the generated image already exists and we aren't explicitly forcing a refresh with new settings, 
        # we can just return it. However, the user prompt implies: "If page image does not exist: render it".
        # Actually, if settings changed, we should probably re-render. Let's just re-render.
        # But wait, if they draw a brush stroke, it modifies the generated image, and we want to return THAT.
        # So we only generate it if it DOES NOT exist!
        if not os.path.exists(final_prev_path):
            from utils.renderer import render_pdf_to_images, load_image_as_page
            from utils.cleanup_engine import process_cleanup

            # Render only the requested page at 120 DPI for fast preview
            is_pdf = file_path.lower().endswith(".pdf")
            if is_pdf:
                pages = render_pdf_to_images(file_path, dpi=120, specific_page=page_num)
            else:
                pages = load_image_as_page(file_path)

            if not pages:
                return jsonify({"error": "Failed to render page."}), 500

            cleaned_pages = process_cleanup(pages, settings)
            preview_img_path = cleaned_pages[0]["path"]

            # Save as fast JPEG
            from PIL import Image
            Image.open(preview_img_path).convert("RGB").save(final_prev_path, "JPEG", quality=80)

        return send_file(final_prev_path, mimetype="image/jpeg")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/apply-brush", methods=["POST"])
def apply_brush():
    """Applies a brush stroke to the generated page."""
    try:
        payload = ensure_dict(request.get_json(silent=True) or {})
        file_id = payload.get("file_id")
        page = payload.get("page", 1)
        brush_size = payload.get("brush_size", 20)
        points = payload.get("points", [])
        
        if not file_id or not points:
            return jsonify({"error": "Missing file_id or points"}), 400

        preview_name = f"prev_{file_id}_p{page}.jpg"
        final_prev_path = os.path.join(_PRV, preview_name)
        
        if not os.path.exists(final_prev_path):
            return jsonify({"error": "Page not generated yet"}), 400

        from utils.inpaint_engine import apply_brush_strokes
        apply_brush_strokes(final_prev_path, final_prev_path, points, brush_size)
        
        return jsonify({"status": "success", "affected_pages": [page]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/apply-rectangle", methods=["POST"])
def apply_rectangle():
    """Applies a manual rectangle erase to the generated page(s)."""
    try:
        payload = ensure_dict(request.get_json(silent=True) or {})
        file_id = payload.get("file_id")
        page = payload.get("page", 1)
        rect = payload.get("rect", {})
        
        if not file_id or not rect:
            return jsonify({"error": "Missing file_id or rect"}), 400

        from utils.inpaint_engine import apply_manual_rects
        
        # Determine which pages to apply to
        apply_mode = payload.get("apply_mode", "current")
        page_range_str = payload.get("page_range", "")
        
        affected_pages = []
        
        if apply_mode == "current":
            affected_pages = [page]
        else:
            # We must apply to all available previews in the folder
            for filename in os.listdir(_PRV):
                if filename.startswith(f"prev_{file_id}_p"):
                    try:
                        p_num = int(filename.split("_p")[1].split(".jpg")[0])
                        
                        if apply_mode == "all":
                            affected_pages.append(p_num)
                        elif apply_mode == "range":
                            from utils.cleanup_engine import _is_page_in_range
                            if _is_page_in_range(p_num, page_range_str):
                                affected_pages.append(p_num)
                    except Exception: pass

        for p_num in affected_pages:
            final_prev_path = os.path.join(_PRV, f"prev_{file_id}_p{p_num}.jpg")
            if os.path.exists(final_prev_path):
                # Manual rect format expects list of rects: [{"box": {"x":..., "y":..., "width":..., "height":...}}]
                rect_obj = {"box": rect}
                apply_manual_rects(final_prev_path, final_prev_path, [rect_obj], fill_method=payload.get("fill_method", "white"), inpaint_radius=5)

        return jsonify({"status": "success", "affected_pages": affected_pages})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/export', methods=['POST'])
def export_pdf():
    try:
        payload = ensure_dict(request.get_json(silent=True) or {})
        file_id = payload.get("file_id")

        if not file_id:
            return jsonify({
                "status": "error",
                "code": "MISSING_FILE_ID",
                "message": "Missing file_id. Please upload the document again."
            }), 400

        settings = ensure_dict(payload.get("settings", {}))
        
        upload_files = [f for f in os.listdir(_UPL) if f.startswith(f"{file_id}_")]
        if not upload_files:
            return jsonify({"status": "error", "message": "File expired. Please re-upload."}), 410
            
        file_path = os.path.join(_UPL, upload_files[0])

        from utils.pdf_exporter import smart_hybrid_export
        out_name = f"final_{uuid.uuid4()}.pdf"
        out_path = os.path.join(_OUT, out_name)

        quality_mode = settings.get("export_quality", "smart")
        
        success = smart_hybrid_export(file_path, out_path, settings, quality_mode, file_id=file_id, preview_dir=_PRV)

        if not success:
            return jsonify({
                "status": "error",
                "message": "Export failed during PDF generation."
            }), 500

        orig_size = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        gen_size = round(os.path.getsize(out_path) / (1024 * 1024), 2)

        return jsonify({
            "status": "success",
            "download_url": f"/api/download/{out_name}",
            "original_size_mb": orig_size,
            "generated_size_mb": gen_size
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "code": "EXPORT_FAILED",
            "message": "Export failed. Please try again."
        }), 500


@app.route("/api/download_raw/<path:filename>")
def download_raw(filename):
    fp = os.path.join(_UPL, secure_filename(filename))
    if os.path.exists(fp): return send_file(fp)
    return jsonify({"error": "Not found"}), 404

@app.route("/api/download_preview/<path:filename>")
def download_preview(filename):
    fp = os.path.join(_PRV, secure_filename(filename))
    if os.path.exists(fp): return send_file(fp, mimetype="image/jpeg")
    return jsonify({"error": "Not found"}), 404

@app.route("/api/download/<path:filename>")
def download(filename):
    fp = os.path.join(_OUT, secure_filename(filename))
    if os.path.exists(fp): return send_file(fp, as_attachment=False)
    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

"""
Flask Application: Premium Document Cleanup & Rebuilder
All temp files go to /tmp for Vercel compatibility.
"""
import os, sys, uuid, tempfile, traceback, time, json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, 
            template_folder=os.path.join(base_dir, "templates"), 
            static_folder=os.path.join(base_dir, "static"))
app.config["MAX_CONTENT_LENGTH"] = int(4.4 * 1024 * 1024)  # 4.4MB for Vercel

# Temp directories (Vercel-safe)
_TMP = tempfile.gettempdir()
_UPL = os.path.join(_TMP, "uploads")
_PRV = os.path.join(_TMP, "previews")
_OUT = os.path.join(_TMP, "outputs")
_PGS = os.path.join(_TMP, "pages")
_GEN = os.path.join(_TMP, "generated")
for d in [_UPL, _PRV, _OUT, _PGS, _GEN]:
    os.makedirs(d, exist_ok=True)

ALLOWED = {'.pdf', '.png', '.jpg', '.jpeg', '.webp'}

@app.before_request
def auto_cleanup_old_files():
    """Clean files older than 10 mins to prevent No space left on device."""
    try:
        now = time.time()
        for d in [_UPL, _PRV, _OUT, _PGS, _GEN]:
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


@app.route("/api/process", methods=["POST"])
def process_document():
    """
    Processes ALL pages of the uploaded document:
    1. Renders each page as an image.
    2. Runs visual cleanup on every page.
    3. Saves each cleaned page as JPEG preview.
    4. Generates the final optimized PDF.
    5. Returns download URL + cleanup report.
    
    This is the main processing endpoint. 
    Download button should only be enabled after this returns.
    """
    try:
        payload = ensure_dict(request.get_json(silent=True) or {})
        file_id = payload.get("file_id")
        settings = ensure_dict(payload.get("settings", {}))

        if not file_id:
            return jsonify({
                "status": "error",
                "code": "MISSING_FILE_ID",
                "message": "Missing file_id. Please upload the document again."
            }), 400

        # Find uploaded file
        upload_files = [f for f in os.listdir(_UPL) if f.startswith(f"{file_id}_")]
        if not upload_files:
            return jsonify({
                "status": "error",
                "code": "FILE_EXPIRED",
                "message": "File expired. Please re-upload."
            }), 410

        file_path = os.path.join(_UPL, upload_files[0])

        # Process all pages
        from utils.cleanup_engine import process_all_pages
        cleanup_report = process_all_pages(file_path, settings, file_id, _GEN)

        if not cleanup_report:
            return jsonify({
                "status": "error",
                "message": "Failed to process any pages."
            }), 500

        page_count = len(cleanup_report)

        # Generate final PDF
        from utils.pdf_exporter import generate_final_pdf
        quality_mode = settings.get("export_quality", "smart")
        out_name = f"final_{file_id}.pdf"
        out_path = os.path.join(_OUT, out_name)

        cleaned_paths = [r["path"] for r in cleanup_report]
        success = generate_final_pdf(file_path, cleaned_paths, out_path, quality_mode)

        if not success:
            return jsonify({
                "status": "error",
                "message": "PDF generation failed."
            }), 500

        orig_size = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        gen_size = round(os.path.getsize(out_path) / (1024 * 1024), 2)

        return jsonify({
            "status": "success",
            "file_id": file_id,
            "page_count": page_count,
            "download_url": f"/api/download/{out_name}",
            "original_size_mb": orig_size,
            "generated_size_mb": gen_size,
            "cleanup_report": [
                {
                    "page": r["page"],
                    "watermark_removed": r.get("watermark_removed", False),
                    "ad_removed": r.get("ad_removed", False),
                    "content_safe": r.get("content_safe", True),
                    "status": r.get("status", "unknown")
                }
                for r in cleanup_report
            ]
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "code": "PROCESS_FAILED",
            "message": f"Server processing error: {str(e)} \n(If it says 'cv2', the server wasn't fully restarted)"
        }), 500


@app.route("/api/preview-page/<file_id>/<int:page_num>", methods=["GET"])
def preview_page(file_id, page_num):
    """
    Serves a pre-generated cleaned page image.
    Images are created by the /api/process endpoint.
    Returns the actual JPEG image data — never HTML or JSON for success.
    """
    try:
        # Look for the generated page image
        gen_file = os.path.join(_GEN, f"gen_{file_id}_p{page_num}.jpg")

        if os.path.exists(gen_file):
            return send_file(gen_file, mimetype="image/jpeg")

        # Also check legacy preview dir
        prev_file = os.path.join(_PRV, f"prev_{file_id}_p{page_num}.jpg")
        if os.path.exists(prev_file):
            return send_file(prev_file, mimetype="image/jpeg")

        return jsonify({
            "status": "error",
            "message": "Preview page not found. Please process the document first."
        }), 404

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": "Failed to serve preview page."
        }), 500


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

        # Check generated dir first, then preview dir
        gen_path = os.path.join(_GEN, f"gen_{file_id}_p{page}.jpg")
        prev_path = os.path.join(_PRV, f"prev_{file_id}_p{page}.jpg")
        
        target_path = gen_path if os.path.exists(gen_path) else prev_path
        
        if not os.path.exists(target_path):
            return jsonify({"error": "Page not generated yet. Please process the document first."}), 400

        from utils.inpaint_engine import apply_brush_strokes
        apply_brush_strokes(target_path, target_path, points, brush_size)
        
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
            # Check all generated pages
            for dirname in [_GEN, _PRV]:
                if not os.path.exists(dirname):
                    continue
                for filename in os.listdir(dirname):
                    if filename.startswith(f"gen_{file_id}_p") or filename.startswith(f"prev_{file_id}_p"):
                        try:
                            p_num = int(filename.split("_p")[1].split(".jpg")[0])
                            
                            if apply_mode == "all":
                                if p_num not in affected_pages:
                                    affected_pages.append(p_num)
                            elif apply_mode == "range":
                                from utils.cleanup_engine import _is_page_in_range
                                if _is_page_in_range(p_num, page_range_str):
                                    if p_num not in affected_pages:
                                        affected_pages.append(p_num)
                        except Exception: pass

        for p_num in affected_pages:
            gen_path = os.path.join(_GEN, f"gen_{file_id}_p{p_num}.jpg")
            prev_path = os.path.join(_PRV, f"prev_{file_id}_p{p_num}.jpg")
            target_path = gen_path if os.path.exists(gen_path) else prev_path
            
            if os.path.exists(target_path):
                rect_obj = {"box": rect}
                apply_manual_rects(
                    target_path, target_path, [rect_obj],
                    fill_method=payload.get("fill_method", "white"),
                    inpaint_radius=5
                )

        return jsonify({"status": "success", "affected_pages": affected_pages})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/export', methods=['POST'])
def export_pdf():
    """
    Legacy export endpoint — kept for backward compatibility.
    The new flow uses /api/process which generates the PDF inline.
    """
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
        
        success = smart_hybrid_export(
            file_path, out_path, settings, quality_mode,
            file_id=file_id, preview_dir=_GEN
        )

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

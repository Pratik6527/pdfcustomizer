from flask import Blueprint, request, jsonify, send_file, render_template, abort
from werkzeug.utils import secure_filename
import os
import re
import cv2
import numpy as np

from utils.file_store import (
    allowed_file, save_upload, get_upload_path, get_preview_dir, delete_session_files, OUTPUT_DIR, PREVIEW_DIR
)
from utils.security import get_max_upload_mb
from utils.logging_config import logger
from services.pdf_service import render_pdf_to_images
from services.image_service import load_image_as_page, image_to_base64
from services.cleanup_service import process_single_page, apply_safe_cleanup
from services.export_service import export_to_pdf

api_bp = Blueprint('api', __name__)

@api_bp.route("/")
def index():
    return render_template("index.html")

@api_bp.route("/api/upload", methods=["POST"])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file provided."}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({"status": "error", "message": "Empty filename."}), 400

    mime = f.mimetype or ""
    if not allowed_file(f.filename, mime):
        return jsonify({"status": "error", "message": "Only PDF, PNG, JPG, WebP allowed."}), 400

    file_data = f.read()
    size_mb = len(file_data) / (1024 * 1024)
    if size_mb > get_max_upload_mb():
        return jsonify({"status": "error", "message": f"File too large. Max is {get_max_upload_mb()}MB."}), 413

    # Reset file pointer and save
    f.seek(0)
    file_id, save_path = save_upload(f)

    try:
        if save_path.endswith('.pdf'):
            import fitz
            doc = fitz.open(save_path)
            page_count = len(doc)
            doc.close()
        else:
            page_count = 1
    except Exception:
        page_count = 1

    return jsonify({
        "status": "success",
        "file_id": file_id,
        "page_count": page_count,
        "filename": secure_filename(f.filename),
        "original_size_mb": round(size_mb, 2)
    })

@api_bp.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    settings = data.get("settings", {})

    if not file_id:
        return jsonify({"status": "error", "message": "file_id required"}), 400

    upload_path = get_upload_path(file_id)
    if not upload_path:
        return jsonify({"status": "error", "message": "File not found. Please re-upload."}), 404

    try:
        # Generate initial page images
        if upload_path.endswith('.pdf'):
            pages_info = render_pdf_to_images(upload_path, file_id)
        else:
            pages_info = load_image_as_page(upload_path, file_id)

        cleanup_report = []
        # Process each page
        for page in pages_info:
            report = process_single_page(page["path"], page["path"], settings, page["page_num"])
            cleanup_report.append(report)

        # Build final PDF
        out_pdf = OUTPUT_DIR / f"{file_id}_final.pdf"
        cleaned_paths = [p["path"] for p in pages_info]
        export_to_pdf(upload_path, cleaned_paths, str(out_pdf))

        # Build response
        for r in cleanup_report:
            if os.path.exists(r["path"]):
                r["image_base64"] = image_to_base64(r["path"])

        pdf_b64 = image_to_base64(str(out_pdf))
        orig_size = os.path.getsize(upload_path) / (1024 * 1024)
        gen_size = os.path.getsize(str(out_pdf)) / (1024 * 1024)

        return jsonify({
            "status": "success",
            "file_id": file_id,
            "page_count": len(cleanup_report),
            "original_size_mb": round(orig_size, 2),
            "generated_size_mb": round(gen_size, 2),
            "cleanup_report": cleanup_report,
            "pdf_base64": pdf_b64,
            "download_url": f"/api/download/{file_id}"
        })

    except Exception as e:
        logger.error(f"Process error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route("/api/preview-page/<file_id>/<int:page_num>")
def api_preview_page(file_id, page_num):
    img_path = PREVIEW_DIR / file_id / f"gen_{file_id}_p{page_num}.jpg"
    if not img_path.exists():
        return jsonify({"error": "Page not found"}), 404
    return send_file(str(img_path), mimetype="image/jpeg", max_age=0, cache_timeout=0)

@api_bp.route("/api/apply-brush", methods=["POST"])
def api_apply_brush():
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    page_num = int(data.get("page", 1))
    points = data.get("points", [])
    brush_sz = int(data.get("brush_size", 20))

    img_path = PREVIEW_DIR / file_id / f"gen_{file_id}_p{page_num}.jpg"
    if not img_path.exists():
        return jsonify({"status": "error", "message": "Page not found."}), 404

    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    for i in range(1, len(points)):
        p1 = (int(points[i-1]['x'] * w), int(points[i-1]['y'] * h))
        p2 = (int(points[i]['x'] * w), int(points[i]['y'] * h))
        cv2.line(mask, p1, p2, 255, brush_sz)

    apply_safe_cleanup(str(img_path), str(img_path), mask, None, "white", 5)

    return jsonify({"status": "success", "affected_pages": [page_num]})

@api_bp.route("/api/apply-rectangle", methods=["POST"])
def api_apply_rectangle():
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    page_num = int(data.get("page", 1))
    rect = data.get("rect", {})

    img_path = PREVIEW_DIR / file_id / f"gen_{file_id}_p{page_num}.jpg"
    if not img_path.exists():
        return jsonify({"status": "error", "message": "Page not found."}), 404

    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    rx = int(rect.get('x', 0) * w)
    ry = int(rect.get('y', 0) * h)
    rw = int(rect.get('width', 0) * w)
    rh = int(rect.get('height', 0) * h)
    cv2.rectangle(mask, (rx, ry), (rx + rw, ry + rh), 255, -1)

    apply_safe_cleanup(str(img_path), str(img_path), mask, None, "white", 5)

    return jsonify({"status": "success", "affected_pages": [page_num]})

@api_bp.route("/api/export", methods=["POST"])
def api_export():
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    
    if not re.match(r'^[0-9a-f\-]{36}$', file_id):
        return jsonify({"status": "error", "message": "Invalid file ID"}), 400

    preview_dir = PREVIEW_DIR / file_id
    if not preview_dir.exists():
        return jsonify({"status": "error", "message": "No pages found."}), 404

    page_files = sorted(
        preview_dir.glob(f"gen_{file_id}_p*.jpg"),
        key=lambda p: int(p.stem.split("_p")[-1])
    )

    upload_path = get_upload_path(file_id)
    out_pdf = OUTPUT_DIR / f"{file_id}_final.pdf"
    cleaned_paths = [str(p) for p in page_files]

    success = export_to_pdf(upload_path, cleaned_paths, str(out_pdf))

    if not success:
        return jsonify({"status": "error", "message": "PDF build failed."}), 500

    size_mb = os.path.getsize(str(out_pdf)) / (1024 * 1024)

    if size_mb > 8:
        return jsonify({
            "status": "success",
            "download_url": f"/api/download/{file_id}",
            "generated_size_mb": round(size_mb, 2)
        })

    pdf_b64 = image_to_base64(str(out_pdf))
    return jsonify({
        "status": "success",
        "pdf_base64": pdf_b64,
        "generated_size_mb": round(size_mb, 2)
    })

@api_bp.route("/api/download/<file_id>")
def api_download(file_id):
    if not re.match(r'^[0-9a-f\-]{36}$', file_id):
        abort(400)
    pdf_path = OUTPUT_DIR / f"{file_id}_final.pdf"
    if not pdf_path.exists():
        abort(404)
    return send_file(
        str(pdf_path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"cleaned_{file_id[:8]}.pdf"
    )

@api_bp.route("/api/delete-session", methods=["POST"])
def api_delete_session():
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    if file_id:
        delete_session_files(file_id)
    return jsonify({"status": "success"})

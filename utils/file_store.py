import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename

import tempfile

BASE_DIR = Path(tempfile.gettempdir())
UPLOAD_DIR = BASE_DIR / "uploads"
PREVIEW_DIR = BASE_DIR / "previews"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR = BASE_DIR / "temp"

# Ensure directories exist
for d in [UPLOAD_DIR, PREVIEW_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp'}
ALLOWED_MIMES = {'application/pdf', 'image/png', 'image/jpeg', 'image/webp'}

def allowed_file(filename, mimetype):
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS and mimetype in ALLOWED_MIMES

def save_upload(file_obj) -> tuple[str, str]:
    """Saves uploaded file and returns (file_id, save_path)."""
    ext = Path(secure_filename(file_obj.filename)).suffix.lower()
    file_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_id}{ext}"
    file_obj.save(str(save_path))
    return file_id, str(save_path)

def get_upload_path(file_id: str) -> str:
    for ext in ALLOWED_EXTENSIONS:
        candidate = UPLOAD_DIR / f"{file_id}{ext}"
        if candidate.exists():
            return str(candidate)
    return None

def get_preview_dir(file_id: str) -> Path:
    preview_dir = PREVIEW_DIR / file_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    return preview_dir

def get_temp_path(ext=".png") -> str:
    return str(TEMP_DIR / f"tmp_{uuid.uuid4()}{ext}")

def delete_session_files(file_id: str):
    import shutil
    upload = get_upload_path(file_id)
    if upload and os.path.exists(upload):
        os.remove(upload)
    
    preview_dir = PREVIEW_DIR / file_id
    if preview_dir.exists():
        shutil.rmtree(str(preview_dir))
        
    out_pdf = OUTPUT_DIR / f"{file_id}_cleaned.pdf"
    if out_pdf.exists():
        os.remove(out_pdf)
    
    out_final = OUTPUT_DIR / f"{file_id}_final.pdf"
    if out_final.exists():
        os.remove(out_final)

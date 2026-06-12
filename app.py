import os
from flask import Flask
from utils.security import get_secret_key
from api.routes import api_bp

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config['SECRET_KEY'] = get_secret_key()
    
    # Register blueprints
    app.register_blueprint(api_bp)
    
    @app.before_request
    def auto_cleanup_old_files():
        import time
        from utils.file_store import UPLOAD_DIR, PREVIEW_DIR, OUTPUT_DIR, TEMP_DIR
        try:
            now = time.time()
            for d in [UPLOAD_DIR, PREVIEW_DIR, OUTPUT_DIR, TEMP_DIR]:
                if not d.exists(): continue
                for file_path in d.rglob('*'):
                    if file_path.is_file() and now - file_path.stat().st_mtime > 600:
                        try:
                            file_path.unlink()
                        except Exception:
                            pass
        except Exception:
            pass
            
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

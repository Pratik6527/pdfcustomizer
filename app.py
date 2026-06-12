import os
from flask import Flask
from utils.security import get_secret_key
from api.routes import api_bp

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config['SECRET_KEY'] = get_secret_key()
    
    # Register blueprints
    app.register_blueprint(api_bp)
    
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

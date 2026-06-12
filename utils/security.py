import os
from dotenv import load_dotenv

# Load env variables from .env file if present
load_dotenv()

def get_openai_api_key():
    return os.environ.get("OPENAI_API_KEY", "")

def get_gemini_api_key():
    return os.environ.get("GEMINI_API_KEY", "")

def get_ai_provider():
    return os.environ.get("AI_PROVIDER", "hybrid")

def get_max_upload_mb():
    try:
        return int(os.environ.get("MAX_UPLOAD_MB", 25))
    except ValueError:
        return 25

def get_secret_key():
    return os.environ.get("SECRET_KEY", "default-dev-key")

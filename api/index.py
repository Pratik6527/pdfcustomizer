import os
import sys

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# This allows Vercel serverless functions to pick up the `app` instance

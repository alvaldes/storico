"""
Vercel serverless entry point for Storico API.

Wraps the FastAPI application using Mangum for ASGI → HTTP adapter
compatible with Vercel Python serverless functions.
"""

import sys
from pathlib import Path

# Add src/ to Python path so `import storico` works in serverless env
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mangum import Mangum
from storico.api.app import create_app

app = create_app()
handler = Mangum(app)

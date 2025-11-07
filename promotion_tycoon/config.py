import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

def _bool(s, default=False):
    return str(s).strip().lower() in {"1","true","yes","on"} if s is not None else default

DEMO_MODE = _bool(os.getenv("DEMO_MODE"), False)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Atlas-only (no localhost default)
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "promotion_advisor")

if not DEMO_MODE:
    if not MONGODB_URI:
        raise RuntimeError(
            "MONGODB_URI is required. Set it in .env. "
            "To run without MongoDB, set DEMO_MODE=true."
        )
    if not MONGODB_URI.startswith("mongodb+srv://"):
        raise RuntimeError(
            "Atlas-only policy: MONGODB_URI must start with 'mongodb+srv://'."
        )

GRADIO_SERVER_NAME = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
GRADIO_SERVER_PORT = int(os.getenv("GRADIO_SERVER_PORT", "7860"))

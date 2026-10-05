"""Shared paths/settings so the app works from any folder (portable)."""
import os
from pathlib import Path

from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backend" / "data"
load_dotenv(ROOT / ".env")

# PDF folder: PDF_DIR in .env (absolute, or relative to the app folder), default ./Coastal_Noakhali
PDF_DIR = ROOT / (os.getenv("PDF_DIR") or "Coastal_Noakhali")

# Use the embedding model bundled in ./models (no download on first run)
_bundled = ROOT / "models" / "all-MiniLM-L6-v2"
if (_bundled / "onnx" / "model.onnx").exists():
    ONNXMiniLM_L6_V2.DOWNLOAD_PATH = _bundled

# Embeddings on CPU: small model, and avoids GPU-library warnings when onnxruntime-gpu is installed
EMBED = ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])

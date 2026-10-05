"""FastAPI backend: Q&A over the Coastal Noakhali plantation journals.

The answering logic is the RAG graph in backend/graph.py
(router -> SQL table or hybrid retrieval -> grade -> rewrite -> generate -> grounding check).

Run from the project root:
  .venv\\Scripts\\uvicorn backend.main:app --port 8000
"""
import base64
import json
import os
import secrets
from pathlib import Path

import pymupdf
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.graph import ask
from backend.llm import ANSWER_MODELS
from backend.settings import DATA, PDF_DIR, ROOT

stats = json.loads((DATA / "stats.json").read_text(encoding="utf-8"))
questions = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))

app = FastAPI(title="Coastal Noakhali Q&A")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Optional password (set APP_PASSWORD on the host). The browser shows its own login box; any user name works.
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


@app.middleware("http")
async def password_gate(request: Request, call_next):
    if not APP_PASSWORD or request.url.path == "/api/stats":  # health check stays open
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            _user, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
            if secrets.compare_digest(pw, APP_PASSWORD):
                return await call_next(request)
        except Exception:
            pass
    return Response("Password required", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Noakhali Q&A"'})


class Ask(BaseModel):
    question: str


@app.get("/")
def home():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/api/stats")
def get_stats():
    return {**stats, "model": ANSWER_MODELS[0][1]}


@app.get("/api/questions")
def get_questions():
    return questions


@app.post("/api/chat")
def chat(req: Ask):
    try:
        return ask(req.question)  # {answer, sources, model, route, trace, sql}
    except Exception as e:  # all models busy, etc.
        raise HTTPException(502, str(e)[:500])


@app.get("/api/page/{file}/{page}")
def page_image(file: str, page: int):
    path = PDF_DIR / Path(file).name  # .name blocks path traversal
    if not path.exists():
        raise HTTPException(404, "file not found")
    doc = pymupdf.open(path)
    if not 1 <= page <= doc.page_count:
        raise HTTPException(404, "page not found")
    return Response(doc[page - 1].get_pixmap(dpi=110).tobytes("png"), media_type="image/png")

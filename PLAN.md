# Coastal Noakhali Plantation Journal Chatbot — Plan (Simple MVP, 1 day)

Goal: a working chatbot by tomorrow. Ask a question, get an answer from the PDFs with page citations.
Keep it simple first. Extras come later (section 7).

## 1. The data

- 80 PDFs in `Coastal_Noakhali/` (~280 MB, ~10–20 pages each, ~1,000 pages total).
- SUFAL Project Plantation Journals, Coastal Forest Division, Noakhali. Mostly English, many tables.
- **Most PDFs are scanned images.** Some have no text at all. The rest have poor embedded OCR.
- So every page must be OCR'd. This is the slowest step. Run it once and cache the result.

## 2. Simple architecture

```
PDFs ─► ocr.py ─► data/pages.jsonl ─► index.py ─► ChromaDB
                                                      │
React chat ◄──► FastAPI /chat ◄── retrieve top-6 pages/chunks ─► Groq LLM ─► answer + [file p.N]
```

No agent, no SQL, no reranker in the MVP. Just retrieve → answer.

## 3. Tech stack (all free)

| Part | Choice |
|---|---|
| OCR | **RapidOCR** (pip install, no system install needed), pages rendered with PyMuPDF at 200 DPI |
| Vector DB | **ChromaDB**, local folder, its built-in default embedding (no torch needed) |
| LLM | **OpenRouter `qwen/qwen3.8-27b:free`** (free, 262K context, vision+text), called via the `openai` client with `base_url=https://openrouter.ai/api/v1`. Backup: Groq `llama-3.3-70b-versatile`. Switch by changing `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) |
| Backend | FastAPI + Uvicorn |
| Frontend | React + Vite, one page |

## 4. Environment status (already done)

- Project venv created: `.venv/` (Python 3.11). Installed: `numpy<2`, rapidocr-onnxruntime, pymupdf,
  chromadb, fastapi, uvicorn, openai, python-dotenv. Import check passed.
- A separate venv was needed. The global Python has a NumPy 2 vs OpenCV conflict.
- Node 22 is available for React.
- **You need:** a free OpenRouter API key from https://openrouter.ai/keys, put in `.env` as `LLM_API_KEY=...`
  (optionally a Groq key as backup).

## 5. Files to build

```
Coastal_Noakhali-.../
├── Coastal_Noakhali/        # raw PDFs (unchanged)
├── .venv/                   # done
├── .env                     # GROQ_API_KEY=...
├── backend/
│   ├── ocr.py               # PDF pages -> text, saved to data/pages.jsonl (resumable)
│   ├── index.py             # chunk (~800 chars, 150 overlap) + store in Chroma with {file, page}
│   ├── main.py              # FastAPI: POST /chat, GET /page/{file}/{n} (page PNG)
│   └── data/
└── frontend/                # Vite React: chat box, answer, source links
```

## 6. Steps and time (1 day)

| # | Step | Time |
|---|---|---|
| 1 | Write `ocr.py`, test on 2 PDFs, check text quality by eye | 1 h |
| 2 | Run OCR on all 80 PDFs in the background (resumable, skips done files) | 1–2 h run time |
| 3 | Write `index.py`, build the Chroma index | 30 min |
| 4 | Write `main.py`: retrieve top 6 chunks, prompt "answer only from context, cite [file p.N], else say not found" | 1 h |
| 5 | React UI: input, message list, source links that open the page image | 1.5 h |
| 6 | Test with 10 real questions and fix issues | 1 h |

**Total: about 6–7 hours of work.** Steps 3–5 can be written while OCR runs.

Run commands (final):
```
.venv\Scripts\python backend\ocr.py
.venv\Scripts\python backend\index.py
.venv\Scripts\uvicorn backend.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## 7. Later improvements (after the MVP works)

1. **Plantation table + Text-to-SQL.** Pull one row per journal (range, beat, year, area, seedlings, species, cost)
   into SQLite. Answers totals like "hectares planted in Hatiya 2020-21". This is the biggest upgrade.
2. **Hybrid search + reranker** (BM25 + `bge-reranker`) for exact names like "Char Kalam".
3. **Vision LLM** (Gemini Flash) for handwritten or badly OCR'd pages.
4. **Bangla questions** with a multilingual embedding (`bge-m3`).
5. **Map view** of plantation sites with Leaflet.
6. Summary card per journal, and Excel/PDF export.

## 8. Risks

- OCR quality on tables and handwriting. Accept "good enough" for the MVP.
- Free-model limits. OpenRouter `:free` models are rate-limited per minute and per day, and this model has
  only one provider (~95% uptime). Fine for a demo. Keep Groq as a fallback in `.env`.
- Do not use the free model to OCR all ~1,000 pages. Daily limits would block it. Use it for vision only on a few bad pages.

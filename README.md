# Coastal Noakhali Plantation Journal Q&A

Ask questions in plain English about the 81 SUFAL plantation journals (Coastal Forest Division, Noakhali).
Answers come from the scanned PDFs, with buttons to open the source pages.

## Quick start (Windows)

0. Unzip to a **short path**, like `C:\Noakhali_QA`. Very long folder paths break the Python install
   (Windows 260-character limit).
1. Put the PDF folder **`Coastal_Noakhali`** (81 PDFs) inside this app folder.
   Or write its location in `.env` as `PDF_DIR=C:\path\to\Coastal_Noakhali`.
2. Double-click **`start.bat`**.
   - **First run only:** it installs Python 3.11 if missing, creates the environment
     and installs packages (3–10 minutes, needs internet).
   - The API keys are **already included** in `.env`. Nothing to enter.
   - If the keys stop working (expired or limit reached), open `.env` in Notepad and paste new free keys:
     - Groq: https://console.groq.com/keys → `GROQ_API_KEY=`
     - OpenRouter: https://openrouter.ai/keys → `LLM_API_KEY=`
   - Please do not share the `.env` file further.
3. The browser opens **http://localhost:8000**. Close the black window to stop the app.

No GPU, Node or npm is needed. The search index is already included, so no OCR is needed
if you have the same PDFs. `start.bat` checks this and warns you if files are missing or extra.

## Alternative: run with Docker (any OS)

With the PDFs in `Coastal_Noakhali/`:
```
docker build -t noakhali-qa .
docker run -p 7860:7860 --env-file .env noakhali-qa
```
Open http://localhost:7860.

## Deploy online for free (Render)

1. Push this folder to a **private** GitHub repo (`.gitignore` keeps `.env` out).
2. render.com → sign in with GitHub → **New → Blueprint** → pick the repo (`render.yaml` sets everything).
3. Enter `GROQ_API_KEY`, `LLM_API_KEY` and an `APP_PASSWORD` when asked.
4. After the build (~5–10 min) the app is at `https://noakhali-qa.onrender.com`.
   The browser asks for the password (any user name). The free plan sleeps after 15 min idle (~1 min wake-up).

(`deploy_hf.py` deploys to Hugging Face Spaces instead, but Docker Spaces need a PRO subscription.)

## Files

| File | Purpose |
|---|---|
| `start.bat` | Sets up on first run, then starts the app |
| `rebuild_index.bat` | Only for new or different PDFs: OCR + rebuild the index (slow on CPU) |
| `make_package.bat` | Builds `dist\Noakhali_QA.zip` to share (without PDFs, **with** the API keys in `.env`) |
| `.env` | API keys and settings. Template: `.env.example` |
| `backend/main.py` | FastAPI server: web page, `/api/chat`, `/api/stats`, `/api/questions`, `/api/page/{file}/{n}` |
| `backend/graph.py` | **The RAG graph** (LangGraph): router → SQL table or hybrid search → grade → rewrite → generate → check |
| `backend/retrieval.py` | Hybrid search: vector (Chroma) + keyword (BM25) + filters, returns whole pages |
| `backend/llm.py` | LLM calls with model fallback |
| `backend/ocr.py` | Ingestion: PDF pages → text (OCR) |
| `backend/extract_table.py` | Ingestion: one row per journal → `plantations.db` (SQLite) + `plantations.csv` |
| `backend/index.py` | Ingestion: chunks + metadata + embeddings → ChromaDB |
| `backend/evaluate.py` | Runs 14 test questions with known answers |
| `backend/check_pdfs.py` | Compares the PDF folder with the index |
| `backend/data/` | The ready-made data (OCR text, ChromaDB, plantations table, stats) |
| `models/` | Bundled embedding model (no download needed) |
| `web/index.html` | Chat page (HTML + Bootstrap + plain JS) |
| `questions.json` | Sample questions shown in the sidebar |
| `HOW_IT_WORKS.md` | Beginner explanation of the whole system |

## How a question is answered (RAG graph)

```
router ─┬─ "how many / total / list"  → SQL on the plantations table (exact numbers) ──┐
        ├─ "facts / explanations"     → hybrid search → grade → (nothing? rewrite ↺) ──┼─ generate → check → answer
        └─ greeting                   ──────────────────────────────────────────────────┘
```
Under each answer, the web page shows the route and a **steps** toggle (graph path and SQL used).

Test result (`backend/evaluate.py`): 14/14 questions correct, about 2–3 s per question.

## Known limits

- **12 journals are written in Bangla** (e.g. Raipur SFPC 2023-24, P1512007). The English OCR cannot read them,
  so the chatbot cannot answer from them, and they are not in the table. 3 more have Bangla pages inside.
- Table values come from OCR. 4 seedling numbers with clear OCR slips were corrected (see the `note` column
  in `backend/data/plantations.csv`).

## Models (`.env`)

- `LLM_MODELS`: writes the final answer (fast Groq Qwen first).
- `LLM_MODELS_FAST`: small graph steps (router, grade, rewrite, check).
- `LLM_MODELS_SQL`: writes SQL for count/total questions.

Each is a comma-separated list of `provider:model`, tried in order when a free model is busy.

## Share with someone on the same network

Start the app with `--host 0.0.0.0` instead of `127.0.0.1` in `start.bat`.
Others open `http://<your-computer-IP>:8000`. Windows Firewall may ask for permission.

# Sharing Plan: Send the App to Someone Who Already Has the PDFs

Goal: the other person runs the chatbot on **their own computer**, using **their own copy of the PDFs**.
Nothing is published online. No PDFs are sent.

## 1. The idea

Only send the **app + the ready-made index**. They put their PDF folder next to it and start.

```
You send (~15 MB zip)                     They already have
─────────────────────                     ─────────────────
backend/ (code + data/ index)             Coastal_Noakhali/  (the 81 PDFs)
web/index.html
questions.json, start.bat, setup.bat
.env.example, README.md, HOW_IT_WORKS.md
                     \                    /
                      └── same folder ───┘  →  double-click start.bat
```

The index (`backend/data/`) already contains the OCR text and search database.
So **they do not need a GPU and do not need to run OCR**, as long as they have the same PDFs.

## 2. Two cases

| Their PDFs | What they do | Time |
|---|---|---|
| **Same 81 files** (same names) | Use the index we send. Just run `setup.bat`, then `start.bat` | ~10 min |
| **Different or extra files** | Rebuild: `ocr.py` then `index.py` | GPU: ~30 min. CPU only: ~6–8 hours |

The app finds pages by **file name**. If the names differ, the source buttons will not open the right page.
A `check_pdfs.py` script will compare their folder to our list and say which case applies.

## 3. What I will build

| # | File | Purpose |
|---|---|---|
| 1 | `requirements.txt` | CPU-only packages for running the app (chromadb, fastapi, uvicorn, openai, python-dotenv, pymupdf) |
| 2 | `requirements-ocr.txt` | Extra packages, only needed to rebuild the index (rapidocr, onnxruntime) |
| 3 | `setup.bat` | One-time: create `.venv`, install `requirements.txt`, copy `.env.example` → `.env` |
| 4 | `start.bat` | Already exists. Starts the server and opens the browser |
| 5 | `.env.example` | Settings with **empty keys**. Your keys are never shared |
| 6 | `backend/check_pdfs.py` | Checks their PDF folder against the index. Says "OK" or "rebuild needed" |
| 7 | `make_package.bat` | Builds `Noakhali_QA.zip` **without** PDFs, `.venv`, `frontend/`, `.env` |
| 8 | `README.md` | Updated with the steps below, written for a non-programmer |

Allow the PDF folder location to be set in `.env` (`PDF_DIR=`), in case their folder has a different name or place.

Time to build and test: **about 1 hour**.

## 4. Steps for the other person

1. Install **Python 3.11** (tick "Add Python to PATH").
2. Unzip `Noakhali_QA.zip`.
3. Copy their `Coastal_Noakhali` PDF folder into it (or set `PDF_DIR` in `.env`).
4. Get their own free API keys:
   - Groq: https://console.groq.com/keys
   - OpenRouter: https://openrouter.ai/keys
5. Double-click **`setup.bat`** (once). Paste the keys into `.env` when it opens.
6. Double-click **`start.bat`**. The browser opens http://localhost:8000.

They need internet for the AI models and for the first search, which downloads an 80 MB embedding model once.

## 5. Important points

- **Do not send your `.env`.** It has your API keys. Each person uses their own free keys.
  This also gives each person their own rate limits.
- **No Node or npm is needed.** The old `frontend/` folder is not included.
- **Windows only** for the `.bat` files. On Mac/Linux, the same commands work with `.venv/bin/`.
- **Python version:** 3.11 recommended. The `numpy<2` pin avoids the error we had before.

## 6. How I will test it

1. Build the zip.
2. Unzip it into a new, empty folder on this computer.
3. Copy the PDFs in, run `setup.bat` and `start.bat` as a new user would.
4. Ask 5 sample questions and open a source page.

## 7. Later (optional)

- If several people in one office need it: run it on **one office computer** and others open
  `http://<that-computer's-IP>:8000` on the same network. No install for them.
- If it should be public: the Hugging Face Spaces plan from before.

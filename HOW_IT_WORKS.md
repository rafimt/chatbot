# How the Plantation Chatbot Works, from the Beginning

This guide explains the whole path, from a scanned PDF to an answer on your screen.
Each step uses the real files in this project.

---

## Part 1: The big idea (called "RAG")

An AI model like Qwen **has never seen your PDFs**. It learned general language from the internet, but it knows
nothing about Char Kalam Beat in 2020-21.

So we don't ask the model to *remember* anything. We give it the relevant pages together with the question:

> "Here are some pages from the documents. Using only these, answer: What species were planted in Char Kalam?"

This is called **RAG (Retrieval-Augmented Generation)**:
- **Retrieval:** find the right pages.
- **Augmented:** add them to the question.
- **Generation:** the model writes the answer.

Think of it as an open-book exam. The model is a smart student who hasn't studied your documents.
The backend finds the right pages in the book and hands them over with the question.

There are two phases:

```
PHASE A: PREPARATION (done once)          PHASE B: ANSWERING (every question)
─────────────────────────────             ───────────────────────────────────
PDFs                                      Your question
 │  ocr.py                                 │
 ▼                                         ▼
Text of every page                        Find matching pages  (Chroma)
 │  index.py                               │
 ▼                                         ▼
Chunks → numbers → database               Build a prompt (pages + question)
                                           │
                                           ▼
                                          Send to AI model (Groq/OpenRouter)
                                           │
                                           ▼
                                          Answer → JSON → web page
```

---

## Part 2: Preparation (done once)

### Step 1: OCR turns images into text (`backend/ocr.py`)

Your PDFs are **photos of paper**. To a computer, a scanned page is just millions of colored dots.
It can't read the word "Keora" in it.

**OCR (Optical Character Recognition)** is an AI that looks at the picture and finds the letters:
1. **Detect** where the text is on the page, as boxes around each line.
2. **Recognize** what each box says, for example "Plantation Area : 400.0 Hectare".
3. `ocr.py` then **sorts** the boxes top to bottom and left to right, so the lines come out in reading order.

The result is `backend/data/pages.jsonl`, one line per page:
```json
{"file": "P1280007.pdf", "page": 2, "text": "Raising Mangrove of 400.0 Hectare Plantation in Financial Year 2020-2021 ..."}
```
We used the **GPU** here because OCR is heavy math, and the GPU does it about 30× faster.
That's the only step that needs a GPU.

### Step 2: Chunking splits the text into pieces (`backend/index.py`)

Pages are split into **chunks** of about 1,200 characters. Each chunk overlaps the next by 200 characters,
so a sentence cut at the edge still appears whole in one of them.

Why split? When a question comes, we want to hand the model **small, focused pieces**, not whole documents.
Small pieces are cheaper, faster and more precise.

### Step 3: Embeddings turn meaning into numbers

This is the most important idea to understand.

An **embedding model** (here, the small MiniLM model inside ChromaDB) reads a piece of text and outputs a
**list of 384 numbers**:

```
"Keora seedlings planted at 1.5m spacing"  →  [0.12, -0.44, 0.08, ..., 0.31]   (384 numbers)
```

These numbers represent the **meaning**, not the exact words. Texts with similar meaning get similar numbers:

```
"Keora seedlings planted at 1.5m spacing"   → [0.12, -0.44, 0.08, ...]
"distance between mangrove plants"          → [0.11, -0.41, 0.09, ...]   ← very close!
"rainfall in July is 698 mm"                → [-0.50, 0.22, 0.73, ...]   ← far away
```

Imagine every chunk as a **dot on a map**, where related topics sit near each other.
Spacing and planting distance are in one area, and climate and rainfall are in another.

All 1,232 chunks are stored in **ChromaDB** (`backend/data/chroma/`), a **vector database**.
It's built to quickly answer one question: *which stored dots are closest to this new dot?*

We also made `backend/data/catalog.json`, a short summary of every journal's cover page
(range, year, type and area). It's used for "how many" questions.

---

## Part 3: Answering a question (every time)

Say you type **"Which species were planted in Char Kalam?"**

### Step 4: The browser sends JSON to the backend

`web/index.html` runs this JavaScript:
```js
fetch('/api/chat', {
  method: 'POST',
  body: JSON.stringify({ question: "Which species were planted in Char Kalam?" })
})
```
This is an **HTTP request**, a message sent over the network. The request body is JSON:
```json
{"question": "Which species were planted in Char Kalam?"}
```

### Step 5: FastAPI receives it (`backend/main.py`)

FastAPI is the **backend server**. It listens on port 8000 and routes each address to a Python function:

| Address | Python function | Returns |
|---|---|---|
| `GET /` | `home()` | the HTML page |
| `GET /api/stats` | `get_stats()` | counts shown in the sidebar |
| `GET /api/questions` | `get_questions()` | sample questions |
| `POST /api/chat` | `chat()` | the answer |
| `GET /api/page/{file}/{n}` | `page_image()` | a scanned page as a PNG |

`chat()` receives the question and does steps 6–11.

### Step 6: Retrieval finds the matching chunks

```python
hits = col.query(query_texts=[req.question], n_results=8)
```
1. The question is turned into 384 numbers with the same embedding model.
2. Chroma finds the **8 closest chunks** on the meaning map.
3. The chunk from `P1280007.pdf p.2` containing "Species: keora, Gewa, Bain" comes out near the top.

The words don't have to match exactly. Asking about "trees" can still find a chunk that says "species",
because the meanings are close.

### Step 7: Routing and building the prompt

The backend first checks the **type of question** with a simple pattern (`CATALOG_Q`):
- **"How many / list / most / compare…"** gets the **catalog** of all 81 journals,
  and is sent to **Ling**, which counts better.
- **Everything else** gets the **8 retrieved passages**, and is sent to **Groq Qwen**, which is fast.

Then it builds the **prompt**, the full text the model will read. It has two parts:

**System message** (the rules, always the same):
```
You answer questions about Plantation Journals of the SUFAL Project...
- Answer ONLY from the CATALOG and PASSAGES below...
- Do NOT write file names in the answer text.
- On the LAST line write: SOURCES: file p.N; ...
```
**User message** (changes every time):
```
PASSAGES:
[P1280007.pdf p.2] ... 10.Species keora,Gewa,Bain  11.No. of seedlings 17,77,600 ...
---
[P1280007.pdf p.5] ...
QUESTION: Which species were planted in Char Kalam?
```

### Step 8: The backend calls the AI model, also with JSON

The backend now acts as a **client** of Groq's server. It sends another HTTP request,
this time **from your backend to Groq**:

```json
POST https://api.groq.com/openai/v1/chat/completions
Authorization: Bearer gsk_...            ← your API key (who you are, for billing/limits)

{
  "model": "qwen/qwen3.8-27b",
  "temperature": 0.1,
  "messages": [
    {"role": "system", "content": "You answer questions about Plantation Journals..."},
    {"role": "user",   "content": "PASSAGES: ... QUESTION: Which species..."}
  ]
}
```

In Python, the `openai` library builds this JSON for you:
```python
resp = CLIENTS["groq"].chat.completions.create(model=..., messages=[...], temperature=0.1)
```

We use the `openai` library even though we're not calling OpenAI. Groq and OpenRouter copy
**the same JSON format** ("OpenAI-compatible"). That's why switching providers only means
changing a URL and a key.

`temperature` controls randomness. `0.1` means "be precise and consistent", which is right for facts.
Higher values give more creative writing.

### Step 9: How the model actually generates the answer

This is how "natural language" works inside the model.

**a) Tokens.** The model doesn't read letters or whole words. It reads **tokens**, word pieces:
```
"Which species were planted" → ["Which", " species", " were", " plant", "ed"]
```
About 1 token ≈ 4 characters of English. Limits like "7,000 tokens per minute" count these pieces.
That's why we had to shrink the catalog.

**b) The model predicts the next token.** A language model is, at its core, one repeated operation:
> Given all the text so far, what is the most likely **next token**?

It reads the whole prompt (rules + passages + question), then generates:
```
"The"  → "The species"  → "The species planted"  → ... → "Keora, Gewa, and Bain."
```
One token at a time, and each new token is added to the text before predicting the next.
That's why answers stream word by word in ChatGPT-style apps.

**c) Why it "understands".** During training, the model read trillions of words and learned patterns:
grammar, facts and how questions relate to answers. It stores this in billions of numbers called
**parameters**. The "27b" in Qwen 3.8 27B means **27 billion** parameters.
Inside, it uses a mechanism called **attention**. When writing "Keora", it "looks back" at the most
relevant part of the prompt, here the line `Species keora,Gewa,Bain` in the passage.

**d) The context window** is the maximum text the model can read at once.
For Qwen that's 262K tokens on OpenRouter and 131K on Groq.
Everything the model knows about your question must fit inside it.
That's why we retrieve pages instead of sending all 754.

**e) Why it can still be wrong.** The model predicts *likely* text, not verified truth.
If the right page wasn't retrieved, it may say "not found" or guess. That's why:
- the rules say "answer ONLY from the passages";
- we show **source pages** so you can check.

### Step 10: The model's reply, again JSON

Groq sends back:
```json
{
  "model": "qwen/qwen3.8-27b",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "The species planted in the Char Kalam plantation were Keora, Gewa, and Bain. This combination was used for the 400.0 hectare mangrove plantation...\nSOURCES: P1280007.pdf p.2"
    }
  }],
  "usage": {"prompt_tokens": 2950, "completion_tokens": 85}
}
```
If it fails, for example with a **429 "rate limited"** error, our loop tries the **next model** in the list.
That's the fallback system.

### Step 11: The backend cleans the answer and replies to the browser

`split_sources()`:
1. **Cuts off** the `SOURCES:` line and turns it into a list.
2. **Removes** stray `[file.pdf]` citations and `**` markers.

FastAPI turns the Python dictionary into **JSON** automatically:
```json
{
  "answer": "The species planted in the Char Kalam plantation were Keora, Gewa, and Bain. ...",
  "sources": [{"file": "P1280007.pdf", "page": 2}],
  "model": "groq:qwen/qwen3.8-27b"
}
```

### Step 12: The browser shows it

The JavaScript reads that JSON:
- `answer` → the white answer bubble;
- `sources` → green buttons. Clicking one calls `/api/page/P1280007.pdf/2`, and the backend renders that
  PDF page as an image;
- `model` → the small "answered by…" line.

---

## Part 4: The whole trip in one picture

```
 BROWSER                 YOUR BACKEND (FastAPI, main.py)              AI PROVIDER (Groq)
 ───────                 ───────────────────────────────              ──────────────────
 You type a question
   │ JSON {question}
   └──────────────────►  1. embed question → 384 numbers
                         2. Chroma: find 8 closest chunks
                         3. choose model (fact → Groq, count → Ling)
                         4. build prompt: rules + passages + question
                              │ JSON {model, messages}  + API key
                              └──────────────────────────────────►  read tokens,
                                                                     predict next token,
                                                                     repeat...
                              ◄──────────────────────────────────┘  JSON {choices:[{content}]}
                         5. if error 429 → try next model
                         6. split SOURCES line, clean text
   ◄─────────────────────┘ JSON {answer, sources, model}
 show answer + source buttons
```

**Where things run:**

| Part | Runs on | Needs |
|---|---|---|
| OCR | your GPU, once | GPU (optional but fast) |
| Embeddings + Chroma search | your CPU, every question | nothing special |
| FastAPI | your computer | Python |
| The language model | Groq's or OpenRouter's servers | internet + API key |
| Web page | your browser | internet (for Bootstrap) |

---

## Part 5: Key words to remember

| Term | Simple meaning |
|---|---|
| **LLM** | Large Language Model. Predicts the next word piece, very well |
| **Token** | A word piece, about 4 characters. Limits and prices are counted in tokens |
| **Prompt** | All the text sent to the model: rules + context + question |
| **System message** | The fixed rules and role for the model |
| **Context window** | The maximum tokens a model can read at once |
| **Embedding** | Text turned into numbers that represent meaning |
| **Vector database** | Stores embeddings and finds the closest ones fast (Chroma) |
| **RAG** | Retrieve relevant text, then generate an answer from it |
| **OCR** | Reading text from images |
| **API** | A way for programs to talk, here HTTP + JSON |
| **API key** | A password that identifies you to the provider |
| **Rate limit (429)** | "Too many requests or tokens, wait." That's why we have fallbacks |
| **Temperature** | Randomness. Low for facts, high for creativity |
| **Hallucination** | The model states something not in the sources. RAG and citations reduce it |

---

## Part 6: Learn more with your own app

1. Open http://localhost:8000/docs. FastAPI creates a test page where you can send JSON to `/api/chat`
   and see the raw JSON reply.
2. In the browser, press F12 → **Network** tab, then ask a question.
   You'll see the request and response JSON.
3. Change `temperature` or `TOP_K` in `backend/main.py`, restart, and see how the answers change.

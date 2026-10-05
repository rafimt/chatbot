"""Steps 3-4: hybrid retrieval = vector search (Chroma) + keyword search (BM25), with filters.

Vector search finds text with the same MEANING ("distance between plants" ~ "spacing").
BM25 finds the exact WORDS and names ("Char Kalam", "Water Development Board").
The two ranked lists are merged with Reciprocal Rank Fusion (RRF).
"""
import json
import re

import chromadb
from rank_bm25 import BM25Okapi

from backend.settings import DATA, EMBED

col = chromadb.PersistentClient(path=str(DATA / "chroma")).get_collection("pages", embedding_function=EMBED)

# Load every chunk once to build the in-memory BM25 index (~1.2K chunks, takes <1 s)
_all = col.get(include=["documents", "metadatas"])
IDS, DOCS, METAS = _all["ids"], _all["documents"], _all["metadatas"]


STOP = set("""a an the of and or in on at to for from by with is are was were be been what which who whom
whose when where why how many much do does did this that these those it its as there their they
please tell me about give list show all any""".split())


def tokenize(text):
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)  # OCR glue: "CharKalam" -> "Char Kalam"
    return [w for w in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()) if w not in STOP]


BM25 = BM25Okapi([tokenize(d) for d in DOCS])
POS = {id_: i for i, id_ in enumerate(IDS)}
PAGE_TEXT = {}
for _line in (DATA / "pages.jsonl").open(encoding="utf-8"):
    _p = json.loads(_line)
    PAGE_TEXT[(_p["file"], _p["page"])] = re.sub(r"[ \t]+", " ", _p["text"]).strip()


def _match(meta, filters):
    return all(not v or meta.get(k, "") == v for k, v in (filters or {}).items())


def search(query, k=8, filters=None, pool=30):
    """Return the top-k chunks as [{"id", "text", "file", "page", "score"}].

    filters: optional {"fiscal_year": "2020-21", "range": "jahajmara", "type": "strip"}
    """
    filters = {k_: v for k_, v in (filters or {}).items() if v}
    where = None
    if filters:
        conds = [{k_: v} for k_, v in filters.items()]
        where = conds[0] if len(conds) == 1 else {"$and": conds}

    # 1) vector ranking
    try:
        vec = col.query(query_texts=[query], n_results=pool, where=where)["ids"][0]
    except Exception:  # filter matched nothing
        vec = []
    # 2) keyword ranking (respecting the same filters)
    scores = BM25.get_scores(tokenize(query))
    order = sorted((i for i in range(len(IDS)) if _match(METAS[i], filters)), key=lambda i: -scores[i])
    kw = [IDS[i] for i in order[:pool] if scores[i] > 0]

    # 3) Reciprocal Rank Fusion: an item ranked high in either list rises to the top
    fused = {}
    for ranking in (vec, kw):
        for rank, id_ in enumerate(ranking):
            fused[id_] = fused.get(id_, 0) + 1 / (60 + rank)
    # 4) chunk -> whole page ("small-to-big"): a hit in one half of a page brings the full page,
    #    so an answer split across two chunks is not lost. Duplicate pages are merged.
    results, seen = [], set()
    for id_ in sorted(fused, key=fused.get, reverse=True):
        meta = METAS[POS[id_]]
        key = (meta["file"], meta["page"])
        if key in seen:
            continue
        seen.add(key)
        header = DOCS[POS[id_]].split("\n", 1)[0]  # "[file p.N] Mangrove plantation, ..."
        results.append({"id": id_, "file": key[0], "page": key[1], "score": round(fused[id_], 4),
                        "text": header + "\n" + PAGE_TEXT.get(key, "")[:2500]})
        if len(results) == k:
            break
    return results

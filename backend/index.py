"""Build the search index from data/pages.jsonl.

Outputs:
  data/chroma/        vector index of page chunks (metadata: file, page)
  data/catalog.json   cover-page summary of every journal (used for "how many" questions)
  data/stats.json     counts shown in the UI

Usage: python backend/index.py
"""
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow "python backend/index.py"
import chromadb  # noqa: E402

from backend.settings import DATA, EMBED  # noqa: E402  (bundled embedding model, CPU)
CHUNK, OVERLAP = 1200, 200
COVER_CHARS = 1200  # cover + "Basic Information" block (area, species, seedlings)


def clean(text):
    return re.sub(r"[ \t]+", " ", text).strip()


def chunks(text):
    if len(text) <= CHUNK:
        return [text]
    out, start = [], 0
    while start < len(text):
        out.append(text[start : start + CHUNK])
        start += CHUNK - OVERLAP
    return out


def load_table():
    """Rows of the plantations table (Step 1), keyed by file. Empty if not built yet."""
    db = DATA / "plantations.db"
    if not db.exists():
        return {}
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = {r["file"]: dict(r) for r in con.execute("SELECT * FROM plantations")}
    con.close()
    return rows


def summary(r):
    """'Mangrove plantation, Jahajmara Range, Char Kalam Beat, Hatiya, FY 2020-21, 400 ha'"""
    if not r or not r.get("type"):
        return None
    parts = [f'{r["type"].capitalize()} plantation',
             r.get("range") and f'{r["range"]} Range', r.get("beat") and f'{r["beat"]} Beat',
             r.get("upazila"), r.get("fiscal_year") and f'FY {r["fiscal_year"]}',
             r.get("area_ha") and f'{r["area_ha"]:g} ha', r.get("area_skm") and f'{r["area_skm"]:g} SKM']
    return ", ".join(p for p in parts if p)


def main():
    pages = [json.loads(l) for l in (DATA / "pages.jsonl").open(encoding="utf-8")]
    by_file = defaultdict(list)
    for p in pages:
        by_file[p["file"]].append(p)

    # Catalog: first non-empty page(s) of each journal = cover with range, beat, FY, area, type
    catalog = []
    for f, ps in sorted(by_file.items()):
        ps.sort(key=lambda p: p["page"])
        cover = " | ".join(clean(p["text"]).replace("\n", " ; ") for p in ps[:2] if p["text"].strip())
        catalog.append({"file": f, "pages": len(ps), "cover": cover[:COVER_CHARS]})
    (DATA / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

    client = chromadb.PersistentClient(path=str(DATA / "chroma"))
    try:
        client.delete_collection("pages")
    except Exception:
        pass
    col = client.create_collection("pages", metadata={"hnsw:space": "cosine"}, embedding_function=EMBED)

    table = load_table()
    ids, docs, metas = [], [], []
    header = {c["file"]: summary(table.get(c["file"])) or c["cover"][:150] for c in catalog}
    for p in pages:
        text = clean(p["text"])
        if len(text) < 30:
            continue
        row = table.get(p["file"], {})
        for i, ch in enumerate(chunks(text)):
            ids.append(f'{p["file"]}|{p["page"]}|{i}')
            # prefix with the journal summary so every chunk knows its range/year/type
            docs.append(f'[{p["file"]} p.{p["page"]}] {header[p["file"]]}\n{ch}')
            # metadata enables filters like "only FY 2020-21" (Chroma needs str, not None)
            metas.append({"file": p["file"], "page": p["page"],
                          "range": (row.get("range") or "").lower(),
                          "fiscal_year": row.get("fiscal_year") or "",
                          "type": row.get("type") or ""})

    for s in range(0, len(ids), 200):
        col.add(ids=ids[s : s + 200], documents=docs[s : s + 200], metadatas=metas[s : s + 200])

    stats = {"documents": len(by_file), "pages": len(pages), "chunks": len(ids),
             "empty_pages": sum(1 for p in pages if len(clean(p["text"])) < 30)}
    (DATA / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(stats)


if __name__ == "__main__":
    main()

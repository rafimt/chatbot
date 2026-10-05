"""Step 1 (ingestion): build the structured plantations table from the OCR text.

One row per journal: type, range, beat, upazila, union, fiscal year, area, seedlings, species.
1. Rules read the fixed journal form (free, gives hints).
2. An LLM reads the first pages + hints and returns clean JSON (fixes OCR noise).
   Results are cached in data/extract_cache.json, so a rerun only does missing files.

Usage: python backend/extract_table.py [--rules-only]  -> backend/data/plantations.db + plantations.csv
"""
import csv
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.settings import DATA  # noqa: E402

CACHE = DATA / "extract_cache.json"
LLM_PROMPT = """Below is OCR text (with spelling errors) from the first pages of a plantation journal of the
SUFAL Project, Coastal Forest Division, Noakhali, Bangladesh, plus rough rule-based HINTS that may be wrong.
Return ONLY a JSON object with these keys (null if not stated in the text, never guess):
type: one of "mangrove", "mangrove enrichment", "strip", "golpata", "other"
range: range or center name without the word "Range" (e.g. "Jahajmara", "Subarnachar SFPC")
beat: beat name without the word "Beat"
upazila: upazila name (e.g. "Hatiya", "Noakhali Sadar", "Subarnachar", "Companigonj")
union_name: union name(s)
fiscal_year: like "2020-21"
area_ha: number, hectares (mangrove plantations), else null
area_skm: number, seedling kilometers (strip plantations), else null
seedlings: integer number of seedlings
species: comma-separated species names, spelled correctly (e.g. "Keora, Gewa, Bain")
Fix obvious OCR errors in numbers (4oo.0 -> 400.0, 17,77,600 -> 1777600)."""

FIELDS = ["file", "pages", "language", "type", "range", "beat", "upazila", "union_name", "fiscal_year",
          "area_ha", "area_skm", "seedlings", "species", "note"]


def num(s):
    """OCR-tolerant number: '4oo.0' -> 400.0, '17,77,600' -> 1777600."""
    prev = None
    while prev != s:  # repeat so runs like "4oo" become "400"
        prev, s = s, re.sub(r"(?<=[\d.])[oO]|[oO](?=[\d.])", "0", s)
    s = s.replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def first(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return m.group(1).strip(" .:;,°。") if m else None


def clean_name(s):
    if not s:
        return None
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?i)\b(range|beat|upazila|union)\b.*$", "", s).strip(" ,.:;°。0")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)  # "CharAlim" -> "Char Alim"
    return s or None


def parse(file, text, n_pages):
    t = re.sub(r"[ \t]+", " ", text)
    row = {"file": file, "pages": n_pages}

    low = t.lower().replace(" ", "")
    if "strip" in low or "seedlingkilomet" in low or "skm" in low:
        row["type"] = "strip"
    elif "enrichment" in low:
        row["type"] = "mangrove enrichment"
    elif "mangrove" in low:
        row["type"] = "mangrove"
    elif "golpata" in low or "nypa" in low:
        row["type"] = "golpata"
    else:
        row["type"] = None

    fy = first(r"(?:financial\s*year|F\.?\s*Y\.?)\W{0,6}(20\d\d\s*-\s*(?:20)?\d\d)", t) \
        or first(r"(20[12]\d\s*-\s*(?:20)?[12]\d)", t)
    if fy:
        a, b = re.split(r"\s*-\s*", fy)
        row["fiscal_year"] = f"{a}-{b[-2:]}"
    else:
        row["fiscal_year"] = None

    row["range"] = clean_name(first(r"Range\s*[:°。0]\s*([A-Za-z][A-Za-z ]{2,30}?)\s*Range", t)
                              or first(r"\d\.?\s*(?:Range|Center)\s*[:°。0]?\s*([A-Za-z][A-Za-z ]{2,30}?)\s*(?:Range|SFPC|\n)", t)
                              or first(r"([A-Z][A-Za-z]{2,20}(?: [A-Z][a-z]+)?)\s*Range", t))
    row["beat"] = clean_name(first(r"Beat\s*[:°。0]\s*([A-Za-z][A-Za-z ]{2,30}?)\s*Beat", t)
                             or first(r"([A-Z][A-Za-z]{2,20}(?: [A-Z][a-z]+)?)\s*Beat", t))
    row["upazila"] = clean_name(first(r"Upazila\s*[:°。0]?\s*([A-Za-z][A-Za-z ]{2,25})", t))
    row["union_name"] = clean_name(first(r"\bUnion\s*[:°。0]?\s*([A-Za-z][A-Za-z &,]{2,60}?)(?:Union|Parishad|\n)", t))

    ha = first(r"(?:Plantation\s*Area|Area)\s*[:°。0=]*\s*([\doO.,]+)\s*(?:Hectare|ha\b|Hec)", t)
    row["area_ha"] = num(ha) if ha else None
    skm = first(r"([\doO.,]+)\s*\(?\s*(?:Seedling\)?\s*(?:Kilomet|KM)|SKM|S\.K\.M)", t) \
        or first(r"AREA\s*=?\s*([\doO.,]+)\s*KM", t)
    row["area_skm"] = num(skm) if skm else None
    if row["type"] == "strip":
        row["area_ha"] = None  # strip plantations are measured in seedling km

    sd = first(r"No\.?\s*of\s*seedlings\s*[:°。0=]*\s*([\doO,.]{3,})", t) \
        or first(r"NUMBER\s*OF\s*SEEDLINGS\s*=?\s*([\doO,.]{3,})", t)
    row["seedlings"] = int(num(sd)) if sd and num(sd) else None

    sp = first(r"Species\s*[:°。0]?\s*([A-Za-z][A-Za-z ,&/]{3,200}?)(?:etc|\n\s*\d|\n\s*\d*\.?\s*No)", t)
    row["species"] = re.sub(r"\s+", " ", sp).strip(" ,") if sp else None
    return row


# Spelling variants seen in the OCR -> one canonical name (so GROUP BY range works)
CANON = {
    "range": {"char bata": "Charbata", "charbata": "Charbata", "conganionj": "Companigonj",
              "mizdhee": "Maijdee SFNTC", "maijdeesfntc": "Maijdee SFNTC", "maijdee sfntc": "Maijdee SFNTC",
              "kairhat": "Kabirhat SFPC", "nalchera": "Nalchira", "subarnachar": "Subarnachar SFPC",
              "sadar": "Sadar", "all rangel noakhali": None},
    "beat": {"jahajmara sadhar": "Jahajmara Sadar", "sadar": "Sadar"},
    "upazila": {"hatiya char": "Hatiya", "hatia char": "Hatiya", "hatia": "Hatiya",
                "subarnachar char": "Subarnachar", "map agmtsfpc": None},
}
SEEDLINGS_PER_HA = 4444  # "planting of 4444 seedlings has been taken as one seedling hectare"
SEEDLINGS_PER_SKM = 1000


def normalize(row):
    """Canonical names + sanity check of seedling numbers. Corrections are recorded in row['note']."""
    notes = []
    for field, table in CANON.items():
        v = row.get(field)
        if isinstance(v, str):
            v = re.sub(r"\s+", " ", v).strip()
            key = v.lower()
            v = table[key] if key in table else (v.title() if v.isupper() else v)
            row[field] = v
    expected = None
    if row.get("type") in ("mangrove",) and row.get("area_ha"):
        expected = row["area_ha"] * SEEDLINGS_PER_HA
    elif row.get("type") == "strip" and row.get("area_skm"):
        expected = row["area_skm"] * SEEDLINGS_PER_SKM
    s = row.get("seedlings")
    # densities of 2,500-4,444 per ha are both used, so only fix gross OCR slips (x10, x80 ...)
    if expected and s and not 0.4 <= s / expected <= 1.25:
        notes.append(f"seedlings OCR value {s:,} replaced by expected {round(expected):,}")
        row["seedlings"] = round(expected)
    row["note"] = "; ".join(notes) or None
    return row


def readable(text):
    """English OCR worked on this page (Bangla pages come out as symbol noise)."""
    return len(re.findall(r"[A-Za-z]{3,}", text)) >= 25


def language(pages):
    """en = mostly readable, mixed = English cover but Bangla pages inside, bn = unreadable."""
    frac = sum(readable(p["text"]) for p in pages) / len(pages)
    if frac >= 0.5:
        return "en"
    cover = pages[0]["text"]
    return "mixed" if len(re.findall(r"[A-Za-z]{3,}", cover)) >= 12 else "bn"


def llm_extract(head, hints, clients):
    """Ask an LLM for clean JSON. Rotates models; waits and retries on rate limits."""
    msg = f"{LLM_PROMPT}\n\nHINTS: {json.dumps(hints)}\n\nOCR TEXT:\n{head[:4500]}"
    models = [("groq", "openai/gpt-oss-120b"), ("groq", "qwen/qwen3.8-27b"),
              ("openrouter", "inclusionai/ling-3.0-flash-sante:free")]
    for attempt in range(12):
        provider, model = models[attempt % len(models)]
        try:
            r = clients[provider].chat.completions.create(
                model=model, temperature=0, messages=[{"role": "user", "content": msg}],
                response_format={"type": "json_object"})
            return json.loads(r.choices[0].message.content), model
        except Exception as e:
            if "429" in str(e) or "413" in str(e):
                time.sleep(8)  # free-tier per-minute limits
            else:
                print("   ", model, str(e)[:120])
    return None, None


def main():
    pages = [json.loads(l) for l in (DATA / "pages.jsonl").open(encoding="utf-8")]
    by_file = defaultdict(list)
    for p in pages:
        by_file[p["file"]].append(p)

    use_llm = "--rules-only" not in sys.argv
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if use_llm:
        from openai import OpenAI
        clients = {
            "groq": OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY"),
                           timeout=60, max_retries=0),
            "openrouter": OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("LLM_API_KEY"),
                                 timeout=90, max_retries=0),
        }

    rows = []
    for i, (f, ps) in enumerate(sorted(by_file.items()), 1):
        ps.sort(key=lambda p: p["page"])
        head = "\n".join(p["text"] for p in ps[:4])  # cover + Basic Information
        row = parse(f, head, len(ps))
        row["language"] = language(ps)
        if use_llm and row["language"] != "bn":
            if f not in cache:
                hints = {k: v for k, v in row.items() if k not in ("file", "pages", "language")}
                data, model = llm_extract(head, hints, clients)
                if data:
                    cache[f] = {**data, "_model": model}
                    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
                print(f"[{i}/{len(by_file)}] {f}: {model or 'FAILED, kept rule values'}", flush=True)
            for k in FIELDS[3:-1]:
                if k in cache.get(f, {}):
                    row[k] = cache[f][k]
        if row["language"] == "bn":  # unreadable Bangla OCR: rule values are noise
            row.update({k: None for k in FIELDS[3:]})
        rows.append(normalize(row))

    db = DATA / "plantations.db"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE plantations (
        file TEXT PRIMARY KEY, pages INT, language TEXT, type TEXT, range TEXT, beat TEXT,
        upazila TEXT, union_name TEXT, fiscal_year TEXT, area_ha REAL, area_skm REAL,
        seedlings INT, species TEXT, note TEXT)""")
    con.executemany(f"INSERT INTO plantations VALUES ({','.join('?' * len(FIELDS))})",
                    [[r.get(k) for k in FIELDS] for r in rows])
    con.commit()
    con.close()

    with (DATA / "plantations.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} journals -> {db.name}, plantations.csv")
    for k in FIELDS[2:]:
        filled = sum(1 for r in rows if r.get(k) not in (None, ""))
        print(f"  {k:12} filled {filled}/{len(rows)}")


if __name__ == "__main__":
    main()

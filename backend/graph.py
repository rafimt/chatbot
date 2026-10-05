"""Step 5: the RAG graph (LangGraph).

  router ─┬─ sql ──────────────────────────────┐
          ├─ retrieve ─ grade ─┬─ (relevant) ───┤
          │      ▲             └─ rewrite ─┘    ├─ generate ─ check ─┬─ END
          └─ chitchat ─────────────────────────┘          ▲          │
                                                          └─ (not grounded, once)
"""
import json
import re
import sqlite3
from typing import TypedDict

from langgraph.graph import END, StateGraph

from backend import retrieval
from backend.llm import ANSWER_MODELS, FAST_MODELS, SQL_MODELS, chat
from backend.settings import DATA

DB = DATA / "plantations.db"
MAX_REWRITES = 2


class State(TypedDict, total=False):
    question: str
    route: str          # "sql" | "docs" | "chitchat"
    filters: dict       # {"fiscal_year", "range", "type"} for retrieval
    query: str          # search query (may be rewritten)
    docs: list          # retrieved pages
    sql: str
    sql_result: str
    answer: str
    sources: list
    model: str
    rewrites: int
    retried: bool
    grounded: bool
    trace: list         # which nodes ran (shown for learning/debugging)


# ---------------------------------------------------------------- helpers
def _db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)  # read-only: the LLM's SQL cannot change data


def _values(col):
    with _db() as con:
        return [r[0] for r in con.execute(f"SELECT DISTINCT {col} FROM plantations WHERE {col} IS NOT NULL")]


SCHEMA = f"""Table plantations (one row per plantation journal, SUFAL Project, Coastal Forest Division Noakhali):
  file TEXT, pages INT, language TEXT ('en','mixed','bn' = Bangla, not readable, all fields NULL),
  type TEXT {_values('type')},
  range TEXT {_values('range')},
  beat TEXT, upazila TEXT {_values('upazila')}, union_name TEXT,
  fiscal_year TEXT {sorted(_values('fiscal_year'))},
  area_ha REAL (mangrove, hectares), area_skm REAL (strip, seedling kilometers),
  seedlings INT, species TEXT (comma list), note TEXT (data corrections)"""


def _trace(s, name):
    return (s.get("trace") or []) + [name]


# ---------------------------------------------------------------- nodes
def router(s: State) -> State:
    out, _ = chat(FAST_MODELS, f"""You route questions about plantation journals.
{SCHEMA}
Return JSON: {{"route": "sql"|"docs"|"chitchat", "fiscal_year": str|null, "range": str|null, "type": str|null}}
- "sql": counting, totals, sums, averages, lists, rankings, comparisons across journals
  (how many, total area, which range has most, list all ...).
- "docs": facts or explanations inside journals (species, spacing, methods, reasons, site details, climate).
- "chitchat": greetings or questions unrelated to the journals.
fiscal_year/range/type: only if the question clearly names one (use the exact values listed above), else null.""",
                  s["question"], as_json=True)
    route = out.get("route") if out.get("route") in ("sql", "docs", "chitchat") else "docs"
    filters = {"fiscal_year": out.get("fiscal_year"), "range": (out.get("range") or "").lower() or None,
               "type": out.get("type")}
    return {"route": route, "filters": filters, "query": s["question"], "rewrites": 0,
            "trace": _trace(s, f"router→{route}")}


def sql_tool(s: State) -> State:
    system = f"""Write ONE SQLite SELECT query that answers the question. {SCHEMA}
Rules: SELECT only. Always include the file column when listing rows. For COUNT/SUM/AVG also return
GROUP_CONCAT(file) AS files. Use LIKE '%x%' for names.
Range and center names (incl. "... SFPC", "... SFNTC") are in the range column, not union_name.
Names are stored WITHOUT the words "Beat", "Range", "Upazila", "Union": use beat LIKE '%Char Kalam%',
never '%Char Kalam Beat%'.
When you GROUP BY or ORDER BY a column, ALWAYS add "WHERE <that column> IS NOT NULL"
(unreadable Bangla journals have NULL fields and must not appear as a group).
If the question is about ONE place (a beat, char, or range in one year), do NOT sum: list the matching rows
with type, area_ha, area_skm and seedlings, because one place can have several journals (e.g. a mangrove
plantation and an enrichment plantation).
Return JSON: {{"sql": "..."}}"""
    user, err = s["question"], ""
    for _ in range(2):  # one retry with the error message
        out, _m = chat(SQL_MODELS, system, user + err, as_json=True)
        sql = (out.get("sql") or "").strip().rstrip(";")
        if not re.match(r"(?is)^\s*(select|with)\b", sql) or ";" in sql:
            err = "\nPrevious attempt was not a single SELECT. Try again."
            continue
        try:
            with _db() as con:
                cur = con.execute(sql)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchmany(60)
            if not rows or all(v in (None, 0) for v in rows[0]) and len(rows) == 1:
                # nothing in the table (e.g. name spelled differently) -> fall back to document search
                return {"sql": sql, "route": "docs", "trace": _trace(s, "sql(0 rows→docs)")}
            result = json.dumps([dict(zip(cols, r)) for r in rows], ensure_ascii=False, default=str)
            return {"sql": sql, "sql_result": result, "trace": _trace(s, "sql")}
        except Exception as e:
            err = f"\nPrevious SQL failed: {sql}\nError: {e}. Fix it."
    return {"sql": sql, "sql_result": "ERROR: could not run a query", "trace": _trace(s, "sql(failed)")}


def retrieve(s: State) -> State:
    docs = retrieval.search(s["query"], k=6, filters=s.get("filters"))
    if not docs and s.get("filters"):  # filter too strict -> search everything
        docs = retrieval.search(s["query"], k=6)
    return {"docs": docs, "trace": _trace(s, "retrieve")}


def grade(s: State) -> State:
    """Keep only pages that help answer the question (one LLM call for all pages)."""
    listing = "\n\n".join(f"[{i}] {d['text'][:700]}" for i, d in enumerate(s["docs"]))
    try:
        out, _ = chat(FAST_MODELS, """Which numbered passages contain information that helps answer the question?
Return JSON: {"relevant": [numbers]}. Return an empty list if none help.""",
                      f"QUESTION: {s['question']}\n\nPASSAGES:\n{listing}", as_json=True)
        keep = [s["docs"][i] for i in out.get("relevant", []) if isinstance(i, int) and 0 <= i < len(s["docs"])]
    except Exception:
        keep = s["docs"]  # grading is an extra; never fail the answer because of it
    return {"docs": keep, "trace": _trace(s, f"grade({len(keep)}/{len(s['docs'])})")}


def rewrite(s: State) -> State:
    out, _ = chat(FAST_MODELS, """The previous search did not find the answer. Rewrite the question as a better search query
for OCR text of plantation journals: use likely words from the journal form (e.g. "Species", "Plantation Area",
"Site Selection Criteria", "No. of seedlings"), add synonyms, keep names. Return JSON: {"query": "..."}""",
                  s["question"], as_json=True)
    return {"query": out.get("query") or s["question"], "filters": {}, "rewrites": s.get("rewrites", 0) + 1,
            "trace": _trace(s, "rewrite")}


ANSWER_RULES = """You answer questions about Plantation Journals of the SUFAL Project, Coastal Forest Division,
Noakhali, Bangladesh. Rules:
- Answer ONLY from the CONTEXT. If it does not contain the answer, say "I could not find this in the documents."
- Write a clear, natural answer in full sentences. Start with the direct answer, then 1-3 sentences of context
  (plantation, place, year, species). Give numbers with units. Fix obvious OCR spelling errors.
- Units: area_ha = hectares. SKM / area_skm = "seedling kilometers" (length of a planted strip),
  NEVER "square kilometers".
- If several journals match (e.g. a mangrove plantation and an enrichment plantation), name each one
  with its own number instead of adding them together.
- Do NOT write file names, page numbers or bracket citations in the answer text.
- On the very LAST line write the sources you used: SOURCES: P1280007.pdf p.2; Noakhali Range 2023-24.pdf p.3
  (for TABLE rows use p.1). If none, write: SOURCES: none"""


def generate(s: State) -> State:
    if s["route"] == "chitchat":
        context = "(no documents needed)"
    elif s["route"] == "sql":
        context = (f"TABLE query result (from the plantations table; 12 journals written in Bangla could not be "
                   f"read and are not included):\nSQL: {s.get('sql')}\nROWS: {s.get('sql_result')}")
    else:
        context = "PASSAGES:\n" + "\n\n---\n\n".join(d["text"] for d in s.get("docs", []))
    extra = "\nIMPORTANT: your previous answer contained claims not in the context. Use ONLY the context." \
        if s.get("retried") else ""
    text, model = chat(ANSWER_MODELS, ANSWER_RULES + extra, f"CONTEXT:\n{context}\n\nQUESTION: {s['question']}")
    answer, sources = split_sources(text)
    if s["route"] == "sql":  # sources = the journals in the query result (not the model's guess)
        found = REF_RE.findall(s.get("sql_result") or "")
        sources = list({f.lower(): {"file": FILES[f.lower()][0], "page": 1} for f, _ in found}.values())[:6]
    return {"answer": answer, "sources": sources, "model": model, "trace": _trace(s, "generate")}


def check(s: State) -> State:
    """Grounding check: is every claim supported by the context?"""
    # SQL answers come straight from exact table values, so only document answers are checked
    if s["route"] != "docs" or "could not find" in s["answer"].lower():
        return {"grounded": True, "trace": _trace(s, "check(skip)")}
    context = s.get("sql_result") if s["route"] == "sql" else \
        "\n\n".join(d["text"][:1500] for d in s.get("docs", []))
    try:
        out, _ = chat(FAST_MODELS, """Is every fact (names, numbers, dates) in the ANSWER supported by the CONTEXT?
Ignore wording and spelling differences. Return JSON: {"grounded": true|false}""",
                      f"CONTEXT:\n{context[:6000]}\n\nANSWER:\n{s['answer']}", as_json=True)
        ok = bool(out.get("grounded", True))
    except Exception:
        ok = True
    return {"grounded": ok, "retried": s.get("retried") or not ok, "trace": _trace(s, f"check({'ok' if ok else 'fail'})")}


# ---------------------------------------------------------------- sources (from the answer's last line)
FILES = {}
with _db() as _con:
    FILES = {r[0].lower(): (r[0], r[1]) for r in _con.execute("SELECT file, pages FROM plantations")}
SOURCES_RE = re.compile(r"^\s*SOURCES:\s*(.*)$", re.I | re.M)
CITE_RE = re.compile(r"\s*\[[^\]]*\.pdf[^\]]*\]", re.I)
REF_RE = re.compile("(" + "|".join(re.escape(f) for f in sorted(FILES, key=len, reverse=True)) +
                    r")\s*(?:p\.?\s*(\d+))?", re.I)


def split_sources(text):
    """Remove the SOURCES line and inline citations; return (clean answer, used sources)."""
    m = SOURCES_RE.search(text)
    refs = m.group(1) if m else text
    used = []
    for name, page in REF_RE.findall(refs):
        file, pages = FILES[name.lower()]
        src = {"file": file, "page": min(int(page or 1), pages)}
        if src not in used:
            used.append(src)
    if m:
        text = text[: m.start()]
    return CITE_RE.sub("", text).replace("**", "").strip(), used[:6]


# ---------------------------------------------------------------- graph wiring
def _after_grade(s):
    if s["docs"]:
        return "generate"
    return "rewrite" if s.get("rewrites", 0) < MAX_REWRITES else "generate"


def _after_check(s):
    # answer not found in the pages -> rewrite the query and search again (self-correction)
    if s["route"] == "docs" and "could not find" in s["answer"].lower() and s.get("rewrites", 0) < MAX_REWRITES:
        return "rewrite"
    # not grounded -> regenerate once with a stricter instruction; never loop more than that
    return "generate" if not s["grounded"] and s["trace"].count("generate") < 2 else END


g = StateGraph(State)
g.add_node("router", router)
g.add_node("sql", sql_tool)
g.add_node("retrieve", retrieve)
g.add_node("grade", grade)
g.add_node("rewrite", rewrite)
g.add_node("generate", generate)
g.add_node("check", check)

g.set_entry_point("router")
g.add_conditional_edges("router", lambda s: s["route"],
                        {"sql": "sql", "docs": "retrieve", "chitchat": "generate"})
g.add_conditional_edges("sql", lambda s: "retrieve" if s["route"] == "docs" else "generate",
                        {"retrieve": "retrieve", "generate": "generate"})
g.add_edge("retrieve", "grade")
g.add_conditional_edges("grade", _after_grade, {"generate": "generate", "rewrite": "rewrite"})
g.add_edge("rewrite", "retrieve")
g.add_edge("generate", "check")
g.add_conditional_edges("check", _after_check, {"generate": "generate", "rewrite": "rewrite", END: END})

rag_graph = g.compile()


def ask(question: str) -> dict:
    s = rag_graph.invoke({"question": question, "trace": []})
    return {"answer": s["answer"], "sources": s.get("sources", []), "model": s.get("model"),
            "route": s["route"], "trace": s.get("trace", []), "sql": s.get("sql")}

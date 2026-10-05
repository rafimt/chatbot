"""Step 7: evaluate the RAG graph on questions with known answers.

Expected values come from the plantations table and the PDF text (checked by hand).
An answer passes if it contains any of the accepted strings (spaces/commas ignored).

Usage: python backend/evaluate.py      -> prints a report, writes backend/data/eval_results.json
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.graph import ask  # noqa: E402
from backend.settings import DATA  # noqa: E402

TESTS = [
    # (question, accepted answers, expected route)
    ("How many strip plantations are recorded?", ["22"], "sql"),
    ("How many mangrove plantations are recorded?", ["40"], "sql"),
    ("Which range has the most plantation journals?", ["Jahajmara"], "sql"),
    ("How many journals are from Hatiya upazila?", ["43"], "sql"),
    ("How many plantations were done in financial year 2020-2021?", ["9"], "sql"),
    ("What is the total strip plantation length in seedling kilometers?", ["442"], "sql"),
    ("Which species were planted in the Char Kalam plantation?", ["Bain"], "docs"),
    ("What spacing was used for the Keora mangrove plantations?", ["1.5"], "docs"),
    ("Who is the land regulatory agency for the Noakhali Range strip plantation?",
     ["WaterDevelopmentBoard"], "docs"),
    ("What is the plantation area of Char Kalam Beat in 2020-2021?", ["400"], None),
    ("How many seedlings were planted in the Char Kalam plantation of 2020-21?", ["1777600"], None),
    ("Which unions are covered by the Noakhali Range strip plantation 2023-24?", ["Dharm"], None),
    ("What does 'one seedling hectare' mean in these journals?", ["4444"], "docs"),
    ("Hello, what can you do?", [""], "chitchat"),
]


def norm(s):
    return re.sub(r"[\s,]", "", s or "").lower()


def main():
    results, passed = [], 0
    for q, accepted, route in TESTS:
        t = time.time()
        try:
            r = ask(q)
            ok = any(norm(a) in norm(r["answer"]) for a in accepted) and (route is None or r["route"] == route)
            res = {"question": q, "ok": ok, "seconds": round(time.time() - t, 1), "route": r["route"],
                   "trace": r["trace"], "answer": r["answer"], "sql": r.get("sql")}
        except Exception as e:
            ok, res = False, {"question": q, "ok": False, "seconds": round(time.time() - t, 1), "error": str(e)[:200]}
        passed += ok
        results.append(res)
        print(f"{'PASS' if ok else 'FAIL'} {res['seconds']:5.1f}s [{res.get('route', '-'):8}] {q}")
        if not ok:
            print("      ->", (res.get("answer") or res.get("error", ""))[:200].replace("\n", " "))
        time.sleep(2)  # be gentle with free-tier rate limits
    secs = [r["seconds"] for r in results]
    print(f"\n{passed}/{len(TESTS)} passed | average {sum(secs) / len(secs):.1f}s | max {max(secs):.1f}s")
    (DATA / "eval_results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

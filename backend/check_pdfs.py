"""Compare the PDF folder with the files in the index. Exit code 0 = OK, 1 = problem.

Usage: python backend/check_pdfs.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.settings import DATA, PDF_DIR  # noqa: E402


def main():
    if not PDF_DIR.is_dir():
        print(f"[!] PDF folder not found: {PDF_DIR}")
        print("    Copy the 'Coastal_Noakhali' folder into the app folder, or set PDF_DIR in .env")
        return 1
    indexed = {c["file"]: c["pages"] for c in json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))}
    present = {p.name for p in PDF_DIR.glob("*.pdf")}
    missing = sorted(set(indexed) - present)
    extra = sorted(present - set(indexed))

    print(f"PDF folder: {PDF_DIR}")
    print(f"Indexed journals: {len(indexed)} | PDFs found: {len(present)}")
    if missing:
        print(f"[!] {len(missing)} indexed PDFs are missing (their source pages will not open): "
              + ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else ""))
    if extra:
        print(f"[!] {len(extra)} PDFs are not in the index (the chatbot cannot read them yet): "
              + ", ".join(extra[:10]) + (" ..." if len(extra) > 10 else ""))
        print("    To include them, run rebuild_index.bat")
    if not missing and not extra:
        print("[OK] PDFs match the index.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

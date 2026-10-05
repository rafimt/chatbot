"""OCR every PDF page -> data/pages.jsonl (one JSON line per page). Resumable.

Usage: python backend/ocr.py [--limit N]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pymupdf

if hasattr(ort, "preload_dlls"):
    ort.preload_dlls()  # GPU build: load pip-installed CUDA/cuDNN so OCR runs ~30x faster
GPU = "CUDAExecutionProvider" in ort.get_available_providers()
from rapidocr_onnxruntime import RapidOCR  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.settings import DATA, PDF_DIR  # noqa: E402

OUT = DATA / "pages.jsonl"
DPI = 200


def lines_to_text(result):
    """Group OCR boxes into reading-order lines (top-to-bottom, left-to-right)."""
    if not result:
        return ""
    boxes = []
    for box, text, _score in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append((sum(ys) / 4, min(xs), max(ys) - min(ys), text))
    boxes.sort()
    lines, cur, cur_y = [], [], None
    for y, x, h, text in boxes:
        if cur_y is None or abs(y - cur_y) <= max(h * 0.6, 8):
            cur.append((x, text))
            cur_y = y if cur_y is None else cur_y
        else:
            lines.append(" ".join(t for _, t in sorted(cur)))
            cur, cur_y = [(x, text)], y
    if cur:
        lines.append(" ".join(t for _, t in sorted(cur)))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only process N files (testing)")
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            done.add(json.loads(line)["file"])

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    print(f"OCR on {'GPU' if GPU else 'CPU (slow, ~30 s/page)'}; PDFs from {PDF_DIR}", flush=True)
    engine = RapidOCR(det_use_cuda=GPU, cls_use_cuda=GPU, rec_use_cuda=GPU)

    with OUT.open("a", encoding="utf-8") as f:
        for i, pdf in enumerate(pdfs, 1):
            if pdf.name in done:
                continue
            doc = pymupdf.open(pdf)
            rows = []
            for pno, page in enumerate(doc, 1):
                pix = page.get_pixmap(dpi=DPI)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img = img[:, :, :3]
                result, _ = engine(img)
                rows.append({"file": pdf.name, "page": pno, "text": lines_to_text(result)})
            # write whole file at once so a crash never leaves a half-done PDF
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(pdfs)}] {pdf.name}: {len(rows)} pages", flush=True)


if __name__ == "__main__":
    sys.exit(main())

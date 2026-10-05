"""Deploy the app to a Hugging Face Docker Space.

Usage (from the app folder):
  .venv\\Scripts\\python deploy_hf.py <hf_username>/<space_name> [--public]

Needs a Hugging Face token with WRITE access: set HF_TOKEN in .env, or run `huggingface-cli login` first.
The Space is PRIVATE unless --public is given. API keys are stored as Space Secrets (not uploaded as files).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

SPACE_README = """---
title: Noakhali Plantation Q&A
emoji: 🌳
colorFrom: green
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

Ask questions about the SUFAL plantation journals (Coastal Forest Division, Noakhali).
Answers come from the scanned PDFs, with source pages. See HOW_IT_WORKS.md.
"""

# only what the running app needs (no .env, .venv, frontend, build files)
IGNORE = [".env", ".venv/*", "frontend/*", "dist/*", "**/__pycache__/*", "*.bat", "deploy_hf.py",
          "backend/data/extract_cache.json", "backend/data/*.log", "README.md", "SHARING_PLAN.md", "PLAN.md"]


def main():
    if len(sys.argv) < 2 or "/" not in sys.argv[1]:
        sys.exit(__doc__)
    repo_id, private = sys.argv[1], "--public" not in sys.argv
    api = HfApi(token=os.getenv("HF_TOKEN") or None)
    print(f"Logged in as: {api.whoami()['name']}")

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=private, exist_ok=True)
    print(f"Space ready: {repo_id} ({'private' if private else 'PUBLIC'})")

    for key in ("GROQ_API_KEY", "LLM_API_KEY"):
        if os.getenv(key):
            api.add_space_secret(repo_id, key, os.getenv(key))
            print(f"Secret set: {key}")
    for key in ("LLM_MODELS", "LLM_MODELS_FAST", "LLM_MODELS_SQL"):
        if os.getenv(key):
            api.add_space_variable(repo_id, key, os.getenv(key))

    print("Uploading files (PDFs are ~230 MB, this can take several minutes)...")
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(ROOT),
                      ignore_patterns=IGNORE, commit_message="Deploy Noakhali Q&A")
    api.upload_file(repo_id=repo_id, repo_type="space", path_or_fileobj=SPACE_README.encode(),
                    path_in_repo="README.md", commit_message="Space settings")
    print(f"\nDone. Build log and app: https://huggingface.co/spaces/{repo_id}")
    print("The first build takes about 3-5 minutes.")


if __name__ == "__main__":
    main()

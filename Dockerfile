# Noakhali Plantation Q&A - container for Hugging Face Spaces (CPU only)
FROM python:3.11-slim

# Hugging Face runs the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# API keys come from the host's secret settings (GROQ_API_KEY, LLM_API_KEY), never from a file.
# PORT is set by the host (Render: 10000); 7860 for Hugging Face / local docker run.
EXPOSE 7860
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}

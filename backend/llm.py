"""One place to call LLMs: OpenAI-compatible clients, model lists from .env, automatic fallback."""
import json
import os
import time

from openai import OpenAI

import backend.settings  # noqa: F401  (loads .env)

CLIENTS = {  # short timeout, no hidden retries: a busy model falls through to the next one fast
    "groq": OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY") or "missing",
                   timeout=30, max_retries=0),
    "openrouter": OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("LLM_API_KEY") or "missing",
                         timeout=60, max_retries=0),
}


def model_list(var, default):
    """Parse "provider:model,provider:model" from .env."""
    return [m.strip().split(":", 1) for m in os.getenv(var, default).split(",") if m.strip()]


# writing the final answer (quality)
ANSWER_MODELS = model_list("LLM_MODELS", "groq:qwen/qwen3.8-27b,openrouter:inclusionai/ling-3.0-flash-sante:free")
# small helper jobs: routing, grading, rewriting, checking (speed)
FAST_MODELS = model_list("LLM_MODELS_FAST",
                         "groq:openai/gpt-oss-20b,groq:qwen/qwen3.8-27b,openrouter:inclusionai/ling-3.0-flash-sante:free")
# writing SQL
SQL_MODELS = model_list("LLM_MODELS_SQL", "groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b")


def chat(models, system, user, as_json=False, rounds=2):
    """Try each model in order (twice, with a pause). Returns (text or dict, "provider:model")."""
    errors = []
    for attempt, (provider, model) in enumerate(models * rounds):
        if attempt and attempt % len(models) == 0:
            time.sleep(4)
        try:
            kwargs = {"response_format": {"type": "json_object"}} if as_json else {}
            r = CLIENTS[provider].chat.completions.create(
                model=model, temperature=0.1,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
            text = r.choices[0].message.content if r.choices else None
            if text:
                return (json.loads(text) if as_json else text), f"{provider}:{model}"
            errors.append(f"{provider}:{model}: empty")
        except Exception as e:  # rate limit, provider down, bad JSON -> next model
            errors.append(f"{provider}:{model}: {str(e)[:120]}")
    raise RuntimeError("All models failed. " + " | ".join(errors))

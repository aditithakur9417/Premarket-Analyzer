# Free LLM for deployed Premarket Desk

The desk enrich step needs an LLM. You do **not** need a paid OpenAI plan.
Use any of these free paths.

## Quick pick

| Situation | Use |
|-----------|-----|
| Deploy on your own VPS / Docker (8GB+ RAM) | **Ollama** in `docker compose` (fully free) |
| Small VPS / no RAM for a model | **Groq** free API key |
| Prefer Google | **Gemini** free API key |
| Want OpenRouter free models | OpenAI-compatible env vars |

`LLM_PROVIDER=auto` (default) tries: **Ollama → Groq → Gemini → OpenAI-compatible**.

---

## 1) Fully free: Ollama with Docker (recommended on 8GB+ VPS)

```bash
# In .env point the desk at the compose service:
# OLLAMA_BASE_URL=http://ollama:11434

# First time — pull model (~4GB)
docker compose --profile ollama --profile pull run --rm ollama-pull

# Run desk + Ollama
docker compose --profile ollama up -d --build
```

`.env`:
```env
LLM_PROVIDER=auto
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b
```

On a tiny VPS / Railway / Render: **skip Ollama**. Use Groq or Gemini only:

```bash
docker compose up -d --build   # desk only; no GPU/RAM for a model
```

---

## 2) Free cloud key: Groq (easiest remote)

1. Create a key at https://console.groq.com/keys (free tier, rate-limited)
2. Put in `.env`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant
```

Works on Railway / Render / Fly / any small container — no GPU.

---

## 3) Free cloud key: Google Gemini

1. Key at https://aistudio.google.com/apikey
2. `.env`:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-flash-latest
```

---

## 4) OpenRouter free models (optional)

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-...
OPENAI_MODEL=meta-llama/llama-3.1-8b-instruct:free
```

---

## Check what is active

From the project root:

```bash
.venv/bin/python -c "from premarket.analyze import llm_status; print(llm_status())"
```

Or hit desk Settings with **Use local Ollama LLM** enabled — enrichment uses whichever free provider resolves.

---

## Local Mac (no Docker)

```bash
ollama pull qwen2.5:7b
ollama serve
# .env
LLM_PROVIDER=auto
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Or only set `GROQ_API_KEY` / `GEMINI_API_KEY` and leave Ollama off.

---

## Notes

- Heuristic scoring still works if **no** LLM is available (desk never hard-fails).
- Free cloud tiers have **rate limits** — fine for one morning run; not for thousands of users.
- For privacy of India news text, prefer **self-hosted Ollama**.

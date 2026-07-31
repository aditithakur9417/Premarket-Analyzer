"""LLM enrichment — free providers for local + deployed desk.

Priority when LLM_PROVIDER=auto:
  1. Ollama (self-hosted, fully free)
  2. Groq free API key (https://console.groq.com)
  3. Google Gemini free API key (https://aistudio.google.com/apikey)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .filters import StockCatalyst


def _env(key: str, default: str = "") -> str:
    val = (os.environ.get(key) or "").strip()
    if val:
        return val
    # Fall back to pydantic Settings (.env) when running under the FastAPI app
    try:
        from backend.app.config import get_settings

        s = get_settings()
        mapping = {
            "LLM_PROVIDER": s.llm_provider,
            "OLLAMA_BASE_URL": s.ollama_base_url,
            "OLLAMA_MODEL": s.ollama_model,
            "GROQ_API_KEY": s.groq_api_key,
            "GROQ_MODEL": s.groq_model,
            "GEMINI_API_KEY": s.gemini_api_key,
            "GOOGLE_API_KEY": s.gemini_api_key,
            "GEMINI_MODEL": s.gemini_model,
            "OPENAI_BASE_URL": s.openai_base_url,
            "OPENAI_API_KEY": s.openai_api_key,
            "OPENAI_MODEL": s.openai_model,
        }
        return (mapping.get(key) or default or "").strip()
    except Exception:
        return default



def llm_provider() -> str:
    return _env("LLM_PROVIDER", "auto").lower() or "auto"


def ollama_base() -> str:
    return _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def ollama_model() -> str:
    return _env("OLLAMA_MODEL", "qwen2.5:7b")


def groq_api_key() -> str:
    return _env("GROQ_API_KEY")


def groq_model() -> str:
    return _env("GROQ_MODEL", "llama-3.1-8b-instant")


def gemini_api_key() -> str:
    return _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")


def gemini_model() -> str:
    return _env("GEMINI_MODEL", "gemini-flash-latest")


def openai_base() -> str:
    """Any OpenAI-compatible free endpoint (OpenRouter free models, etc.)."""
    return _env("OPENAI_BASE_URL", "").rstrip("/")


def openai_api_key() -> str:
    return _env("OPENAI_API_KEY") or _env("OPENROUTER_API_KEY")


def openai_model() -> str:
    return _env("OPENAI_MODEL", "meta-llama/llama-3.1-8b-instruct:free")


def _http_json(url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 90) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _ollama_ok() -> bool:
    try:
        data = _http_json(f"{ollama_base()}/api/tags", timeout=3)
        names = {m.get("name") for m in data.get("models", [])}
        model = ollama_model()
        return model in names or any(model.split(":")[0] in (n or "") for n in names)
    except Exception:
        return False


def _groq_ok() -> bool:
    return bool(groq_api_key())


def _gemini_ok() -> bool:
    return bool(gemini_api_key())


def _openai_compat_ok() -> bool:
    return bool(openai_base() and openai_api_key())


def resolve_provider() -> str | None:
    """Return active provider name or None if nothing free is configured."""
    pref = llm_provider()
    order = {
        "ollama": ["ollama"],
        "groq": ["groq"],
        "gemini": ["gemini"],
        "openai": ["openai"],
        "openai_compatible": ["openai"],
        "auto": ["ollama", "groq", "gemini", "openai"],
    }.get(pref, ["ollama", "groq", "gemini", "openai"])

    checks = {
        "ollama": _ollama_ok,
        "groq": _groq_ok,
        "gemini": _gemini_ok,
        "openai": _openai_compat_ok,
    }
    for name in order:
        if checks.get(name, lambda: False)():
            return name
    return None


def llm_available() -> bool:
    return resolve_provider() is not None


# Backward-compatible name used across the codebase
def ollama_available(model: str | None = None) -> bool:  # noqa: ARG001
    return llm_available()


def _ask_ollama(prompt: str) -> str:
    payload = {
        "model": ollama_model(),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 800},
    }
    data = _http_json(f"{ollama_base()}/api/generate", payload, timeout=120)
    return (data.get("response") or "").strip()


def _ask_openai_compat(prompt: str, *, base: str, api_key: str, model: str, extra_headers: dict[str, str] | None = None) -> str:
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 800,
        "messages": [
            {"role": "system", "content": "You are an institutional India equity pre-market desk analyst. Reply with valid JSON only when asked."},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}
    data = _http_json(f"{base}/chat/completions", payload, headers=headers, timeout=90)
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()


def _ask_groq(prompt: str) -> str:
    return _ask_openai_compat(
        prompt,
        base="https://api.groq.com/openai/v1",
        api_key=groq_api_key(),
        model=groq_model(),
    )


def _ask_openai(prompt: str) -> str:
    headers = {}
    # OpenRouter asks for optional referer/title
    if "openrouter.ai" in openai_base():
        headers["HTTP-Referer"] = _env("OPENROUTER_REFERER", "https://github.com/premarket-desk")
        headers["X-Title"] = "Premarket Desk"
    return _ask_openai_compat(
        prompt,
        base=openai_base(),
        api_key=openai_api_key(),
        model=openai_model(),
        extra_headers=headers,
    )


def _ask_gemini(prompt: str) -> str:
    model = gemini_model()
    key = gemini_api_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
    }
    data = _http_json(url, payload, timeout=90)
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = ((cands[0].get("content") or {}).get("parts")) or []
    texts = [p.get("text") or "" for p in parts]
    return "\n".join(texts).strip()


def _ask(prompt: str) -> str:
    provider = resolve_provider()
    if provider == "ollama":
        return _ask_ollama(prompt)
    if provider == "groq":
        return _ask_groq(prompt)
    if provider == "gemini":
        return _ask_gemini(prompt)
    if provider == "openai":
        return _ask_openai(prompt)
    raise RuntimeError("No free LLM provider available")


def llm_status() -> dict[str, Any]:
    return {
        "provider_pref": llm_provider(),
        "active": resolve_provider(),
        "ollama": {"base": ollama_base(), "model": ollama_model(), "ok": _ollama_ok()},
        "groq": {"configured": _groq_ok(), "model": groq_model()},
        "gemini": {"configured": _gemini_ok(), "model": gemini_model()},
        "openai_compatible": {"configured": _openai_compat_ok(), "base": openai_base(), "model": openai_model()},
    }


def enrich_top_catalysts(
    catalysts: list[StockCatalyst],
    limit: int = 8,
    global_context: str = "",
) -> list[StockCatalyst]:
    """Ask LLM to refine why / opening / risks for top catalysts."""
    if not llm_available():
        return catalysts

    # Prefer highest priority / conviction names
    ordered = sorted(
        catalysts,
        key=lambda x: (getattr(x, "priority_rank", 0), x.conviction, x.strength),
        reverse=True,
    )[:limit]
    for c in ordered:
        locked_opening = c.opening_impact
        locked_strength = c.strength
        unverified_lock = c.filing_status == "unverified" and c.event_type in {
            "m_and_a",
            "order_win",
            "fundraising",
            "buyback",
            "open_offer",
            "regulatory_approval",
            "earnings_beat",
            "earnings_miss",
            "business_entry",
            "promoter_buying",
        }
        headlines = "\n".join(f"- {a.title}: {a.body[:280]}" for a in c.articles[:4])
        mkt = ""
        if c.prev_day_chg_pct is not None or c.cap_tier:
            mkt = (
                f"Market: cap={c.cap_tier or '?'}, prior_day={c.prev_day_chg_pct}, "
                f"liq={c.liquidity_tier}, sector={c.sector or '?'}\n"
            )
        filing_line = f"Filing status: {c.filing_status or 'n/a'}. {c.filing_note or ''}\n"
        constraints = ""
        if unverified_lock:
            constraints = (
                "HARD CONSTRAINT: filing is unverified — you MUST NOT choose Gap Up Likely or Gap Down Risk; "
                "prefer Mild Positive / Mild Negative / Watch for Breakout / Neutral.\n"
            )
        prompt = f"""You are an institutional India equity pre-market desk analyst.
Stock: {c.name} ({c.symbol})
Heuristic bias: {c.bias}, event: {c.event_type}, strength: {c.strength}/5
Current opening label: {c.opening_impact}
{mkt}{filing_line}{constraints}Global/GIFT context: {global_context or 'n/a'}

Headlines in news window:
{headlines}

Reply ONLY valid JSON with keys:
why_it_matters (1-2 sentences, trading-relevant),
opening_impact (one of: Gap Up Likely, Mild Positive, Watch for Breakout, Watch for Fade, Neutral, Mild Negative, Gap Down Risk),
risks (1 short sentence),
strength_1_to_5 (integer).
Respect sell-the-news if prior_day already moved hard. Respect GIFT risk-off for mid/small longs.
No markdown."""
        try:
            raw = _ask(prompt)
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                obj = json.loads(raw[start : end + 1])
            else:
                continue
            if obj.get("why_it_matters"):
                c.why = str(obj["why_it_matters"]).strip()
            if obj.get("risks"):
                c.risks = str(obj["risks"]).strip()
            if obj.get("opening_impact"):
                proposed = str(obj["opening_impact"]).strip()
                if unverified_lock and proposed in {"Gap Up Likely", "Gap Down Risk"}:
                    c.opening_impact = locked_opening  # keep heuristic downgrade
                else:
                    c.opening_impact = proposed
            s = obj.get("strength_1_to_5")
            if isinstance(s, int) and 1 <= s <= 5:
                blended = max(1, min(5, round((c.strength + s) / 2)))
                if unverified_lock:
                    c.strength = min(blended, locked_strength, 3)
                else:
                    c.strength = blended
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError, RuntimeError):
            continue
    return catalysts


def market_view_llm(
    bullish: list[StockCatalyst],
    bearish: list[StockCatalyst],
    global_context: str = "",
) -> dict[str, Any] | None:
    if not llm_available():
        return None
    b = ", ".join(f"{c.symbol}({c.event_type},{c.strength})" for c in bullish[:6]) or "none"
    s = ", ".join(f"{c.symbol}({c.event_type},{c.strength})" for c in bearish[:6]) or "none"
    prompt = f"""India pre-market desk. Combine overnight stock catalysts with global tape.
Bullish: {b}
Bearish: {s}
Global/GIFT: {global_context or 'n/a'}
Reply ONLY JSON: bias (Bullish|Bearish|Mixed|Mildly Bullish|Mildly Bearish), confidence_1_to_10 (int), reasons (array of 3-4 short strings), biggest_opportunity (string), biggest_risk (string).
Weight GIFT Nifty heavily for index open direction; stock catalysts for single-name trades."""
    try:
        raw = _ask(prompt)
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
    except Exception:
        return None
    return None

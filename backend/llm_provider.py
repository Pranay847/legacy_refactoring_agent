"""Provider-neutral text generation for hosted and local MACE deployments."""

from threading import BoundedSemaphore

import anthropic
import httpx

try:
    from config import settings
except ImportError:  # package imports
    from backend.config import settings


MODEL = "claude-sonnet-4-5"
FAST_MODEL = "claude-haiku-4-5"
SMALL_CLUSTER_THRESHOLD = 6
MAX_TOKENS = 8192

_ollama_slots = BoundedSemaphore(settings.ollama_generation_workers)
_groq_slots = BoundedSemaphore(settings.groq_generation_workers)


def validate_generation_config() -> None:
    provider = settings.llm_provider
    if provider not in {"anthropic", "ollama", "groq"}:
        raise RuntimeError("LLM_PROVIDER must be 'anthropic', 'ollama', or 'groq'.")
    if provider == "anthropic" and not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
    if provider == "groq" and not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")


def generation_is_configured() -> bool:
    try:
        validate_generation_config()
    except RuntimeError:
        return False
    return True


def generation_worker_count(requested: int | None, cluster_count: int) -> int:
    workers = requested if requested is not None else settings.generation_workers
    cap = settings.generation_max_workers
    if settings.llm_provider == "ollama":
        cap = min(cap, settings.ollama_generation_workers)
    elif settings.llm_provider == "groq":
        cap = min(cap, settings.groq_generation_workers)
    return max(1, min(workers, cap, cluster_count or 1))


def model_for_cluster_size(size: int) -> str:
    if settings.llm_provider == "ollama":
        return settings.ollama_model
    if settings.llm_provider == "groq":
        return settings.groq_model
    return FAST_MODEL if size <= SMALL_CLUSTER_THRESHOLD else MODEL


def call_llm(prompt: str, model: str = MODEL, *, system: str | None = None,
             max_tokens: int | None = None) -> str:
    validate_generation_config()
    provider = settings.llm_provider
    if provider == "ollama":
        return _call_ollama(prompt, system=system, max_tokens=max_tokens)
    if provider == "groq":
        return _call_groq(prompt, system=system, max_tokens=max_tokens)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    request = {
        "model": model,
        "max_tokens": max_tokens or MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        request["system"] = system
    return client.messages.create(**request).content[0].text


def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _call_ollama(prompt: str, *, system: str | None, max_tokens: int | None) -> str:
    try:
        with _ollama_slots:
            response = httpx.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": _messages(prompt, system),
                    "stream": False,
                    "options": {"num_predict": max_tokens or MAX_TOKENS},
                },
                timeout=600.0,
            )
        response.raise_for_status()
        return response.json()["message"]["content"]
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Cannot communicate with Ollama at {settings.ollama_base_url}: {exc}"
        ) from exc


def _call_groq(prompt: str, *, system: str | None, max_tokens: int | None) -> str:
    output_limit = min(max_tokens or settings.groq_max_tokens, settings.groq_max_tokens)
    try:
        with _groq_slots:
            response = httpx.post(
                f"{settings.groq_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": settings.groq_model,
                    "messages": _messages(prompt, system),
                    "max_completion_tokens": output_limit,
                    "temperature": 0.1,
                },
                timeout=180.0,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise RuntimeError(
                "Groq's free rate limit was reached. Wait for it to reset, then retry."
            ) from exc
        try:
            detail = exc.response.json().get("error", {}).get("message") or exc.response.text
        except (ValueError, AttributeError):
            detail = exc.response.text
        raise RuntimeError(
            f"Groq returned HTTP {exc.response.status_code}: {detail[:1000]}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError("Groq generation timed out after 180 seconds.") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Cannot communicate with Groq at {settings.groq_base_url}: {exc}"
        ) from exc

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Groq returned an invalid generation response.") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Groq returned an empty generation response.")
    return content

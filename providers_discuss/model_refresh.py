from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


OFFICIAL_MODEL_REFRESH_SOURCES: dict[str, list[str]] = {
    "gemini": [
        "https://ai.google.dev/gemini-api/docs/models",
        "https://ai.google.dev/api/models",
    ],
}


@dataclass(frozen=True)
class SourceFetch:
    url: str
    status: str
    error: str = ""


def refresh_models(*, provider: str, timeout_seconds: int = 15) -> dict[str, Any]:
    provider = provider.strip().lower()
    urls = OFFICIAL_MODEL_REFRESH_SOURCES.get(provider)
    if not urls:
        raise ValueError(f"unsupported model refresh provider: {provider}")

    models_by_id: dict[str, set[str]] = {}
    sources: list[SourceFetch] = []
    for url in urls:
        try:
            text = _fetch_text(url, timeout_seconds=timeout_seconds)
        except (OSError, urllib.error.URLError) as exc:
            sources.append(SourceFetch(url=url, status="failed", error=str(exc)))
            continue
        sources.append(SourceFetch(url=url, status="ok"))
        for model in extract_model_ids(provider=provider, text=text):
            models_by_id.setdefault(model, set()).add(url)

    models = [
        {"model": model, "sources": sorted(sources_for_model)}
        for model, sources_for_model in sorted(models_by_id.items(), key=lambda item: _model_sort_key(provider, item[0]))
    ]
    return {
        "schema": "providers-discuss.model-refresh.v1",
        "provider": provider,
        "source_policy": "official_sources_only",
        "sources": [source.__dict__ for source in sources],
        "models": models,
        "status": "pass" if models else "no_models_found",
    }


def extract_model_ids(*, provider: str, text: str) -> list[str]:
    if provider != "gemini":
        raise ValueError(f"unsupported model extraction provider: {provider}")
    candidates = set(re.findall(r"\bgemini-(?:\d+(?:\.\d+)?|flash|pro)[a-z0-9.-]*(?:-[a-z0-9.-]+)*\b", text, flags=re.IGNORECASE))
    return sorted(model.lower() for model in candidates if _looks_like_gemini_model_id(model))


def _fetch_text(url: str, *, timeout_seconds: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "providers-discuss-model-refresh/1.0",
            "Accept": "text/html,application/json,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _looks_like_gemini_model_id(model: str) -> bool:
    text = model.lower()
    if text.startswith(("gemini-api", "gemini-model", "gemini-doc")):
        return False
    return any(token in text for token in ("flash", "pro", "lite", "live", "tts", "latest", "preview", "experimental"))


def _model_sort_key(provider: str, model: str) -> tuple[Any, ...]:
    if provider != "gemini":
        return (model,)
    text = model.lower()
    version = _numeric_version(text)
    class_rank = 0 if "flash" in text else 1 if "pro" in text else 2
    stability_rank = 0 if not any(token in text for token in ("preview", "experimental", "latest")) else 1
    return (-version[0], -version[1], class_rank, stability_rank, text)


def _numeric_version(model: str) -> tuple[int, int]:
    match = re.search(r"gemini-(\d+)(?:\.(\d+))?", model)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))

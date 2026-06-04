"""Offline AI analysis for captured danmu sessions."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
MAX_MESSAGES_FOR_ANALYSIS = 1500


class AIAnalysisError(RuntimeError):
    """Raised when the AI provider cannot produce a report."""


def analyze_danmu_session(session: dict[str, object], messages: list[dict[str, object]]) -> dict[str, object]:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        raise AIAnalysisError("AI API key is not configured. Set DEEPSEEK_API_KEY, OPENAI_API_KEY, or AI_API_KEY.")

    base_url = (
        os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("AI_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL") or DEFAULT_MODEL

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(session, messages[:MAX_MESSAGES_FOR_ANALYSIS])},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise AIAnalysisError(f"AI provider returned HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise AIAnalysisError(f"AI provider request failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        report = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AIAnalysisError(f"AI provider returned an invalid response: {raw[:500]}") from exc

    return normalize_report(report, model)


def normalize_report(report: dict[str, object], model: str) -> dict[str, object]:
    return {
        "model": model,
        "summary": str(report.get("summary") or ""),
        "topics": _string_list(report.get("topics")),
        "sentiment": str(report.get("sentiment") or ""),
        "keywords": _string_list(report.get("keywords")),
        "risks": _string_list(report.get("risks")),
        "suggestions": _string_list(report.get("suggestions")),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _system_prompt() -> str:
    return (
        "?????????????????????????????????????????"
        "?????????????????? JSON ???"
    )


def _user_prompt(session: dict[str, object], messages: list[dict[str, object]]) -> str:
    lines = []
    for message in messages:
        nickname = str(message.get("nickname") or "????")
        text = str(message.get("text") or "")
        received_at = str(message.get("received_at") or "")
        if text.strip():
            lines.append(f"[{received_at}] {nickname}: {text}")

    return (
        "???????????????????? JSON?\n"
        "{\n"
        '  "summary": "??????",\n'
        '  "topics": ["????1", "????2"],\n'
        '  "sentiment": "??????",\n'
        '  "keywords": ["???1", "???2"],\n'
        '  "risks": ["?????????????????"],\n'
        '  "suggestions": ["?????????"]\n'
        "}\n\n"
        f"??????? {session.get('room_id')}??? {session.get('id')}???? {session.get('message_count')}?\n"
        "?????\n"
        + "\n".join(lines)
    )

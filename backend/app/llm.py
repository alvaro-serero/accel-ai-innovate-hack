"""All LLM calls go through here. Owner: Alvaro.

    from backend.app.llm import claude_json, aclaude_json, openai_json, SONNET, HAIKU

    data = claude_json(system="You rank internships...", user="...", model=HAIKU)
    data = await aclaude_json(...)          # same, async (for asyncio.gather batches)
    data = await aclaude_json(..., model=HAIKU, effort="low")  # cheap bulk calls
    data = openai_json(system=..., user=...) # Taleb's independent judge

Every function asks for JSON and returns a parsed dict or list (one retry on bad JSON).
USAGE keeps a running token count per model for the cost stat.
"""
import json
import re
import threading
from collections import defaultdict

from anthropic import Anthropic, AsyncAnthropic
from openai import OpenAI

from backend.app.config import settings

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"

USAGE: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})
_lock = threading.Lock()

_anthropic: Anthropic | None = None
_aanthropic: AsyncAnthropic | None = None
_openai: OpenAI | None = None

JSON_RULE = "\n\nAnswer with valid JSON only. No prose, no markdown fences."


def _track(model: str, inp: int, out: int) -> None:
    with _lock:
        USAGE[model]["input"] += inp
        USAGE[model]["output"] += out
        USAGE[model]["calls"] += 1


def extract_json(text: str):
    """Parse JSON even if the model wrapped it in prose or ``` fences."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"no JSON found in: {text[:200]}")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start : end + 1])


def _client() -> Anthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic


def _aclient() -> AsyncAnthropic:
    global _aanthropic
    if _aanthropic is None:
        _aanthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _aanthropic


def _text(resp) -> str:
    # Claude 5 models may put a thinking block before the answer: read only the text blocks.
    text = "".join(b.text for b in resp.content if b.type == "text")
    if not text:
        raise ValueError(f"no text block (stop_reason={resp.stop_reason})")  # caught by the retry
    return text


def _effort(effort: str | None) -> dict:
    """effort='low' makes bulk calls cheaper and faster (less thinking). None = model default."""
    return {"output_config": {"effort": effort}} if effort else {}


def claude_json(system: str, user: str, model: str = SONNET, max_tokens: int = 2000, effort: str | None = None):
    for attempt in range(2):
        resp = _client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system + JSON_RULE,
            messages=[{"role": "user", "content": user}],
            **_effort(effort),
        )
        _track(model, resp.usage.input_tokens, resp.usage.output_tokens)
        try:
            return extract_json(_text(resp))
        except (ValueError, json.JSONDecodeError):
            if attempt == 1:
                raise


async def aclaude_json(
    system: str, user: str, model: str = HAIKU, max_tokens: int = 1000, effort: str | None = None
):
    for attempt in range(2):
        resp = await _aclient().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system + JSON_RULE,
            messages=[{"role": "user", "content": user}],
            **_effort(effort),
        )
        _track(model, resp.usage.input_tokens, resp.usage.output_tokens)
        try:
            return extract_json(_text(resp))
        except (ValueError, json.JSONDecodeError):
            if attempt == 1:
                raise


def openai_json(system: str, user: str, model: str | None = None, max_tokens: int = 1500):
    """Independent judge (eval only). Returns a JSON object (dict)."""
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.openai_api_key)
    model = model or settings.openai_model
    resp = _openai.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system + JSON_RULE},
            {"role": "user", "content": user},
        ],
    )
    usage = resp.usage
    _track(model, usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0)
    return extract_json(resp.choices[0].message.content)

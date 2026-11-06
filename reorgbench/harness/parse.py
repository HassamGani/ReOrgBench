"""Pull one action out of model text. Tolerates a code fence or a sentence around the JSON; nothing more."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class ParseError(ValueError):
    pass


def _first_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find("{", start + 1)
    return None


def parse_action(text: str) -> dict[str, Any]:
    m = _FENCE.search(text)
    candidate = m.group(1) if m else _first_object(text)
    if candidate is None:
        raise ParseError("no JSON object found")
    try:
        action = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e}") from e
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        raise ParseError('the object needs a "type" field')
    return action

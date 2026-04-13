"""Utilities for parsing LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from an LLM response that may contain extra text.

    Finds the first ``{...}`` block in *text* and parses it.
    Raises ``ValueError`` if no valid JSON object is found.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(match.group())

"""
AI-powered batch categorization using Claude.

Sends merchant descriptions to Claude Haiku and returns suggested category names.
Falls back gracefully when ANTHROPIC_API_KEY is not set.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a personal finance assistant helping categorize bank transaction descriptions \
into expense categories.

You have deep knowledge of Canadian businesses, merchants, and services — especially \
in Quebec and major Canadian cities. Use your knowledge of real business names to \
identify what kind of business a transaction description refers to, even when the \
description contains location codes, abbreviations, or truncated names.

Available categories (choose ONLY from this list):
- Groceries
- Restaurants & Coffee
- Transportation
- Utilities
- Entertainment
- Shopping
- Health
- Travel
- Financial
- Income
- Other

Rules:
1. Return ONLY a JSON object mapping each description to a category name.
2. Use exactly the category names listed above.
3. When unsure, use "Other".
4. Do not add any explanation outside the JSON.

Example input:
["PREMIER MOISSON GAREMONTREAL Q", "STM OPUS MONTREAL QC", "NETFLIX.COM"]

Example output:
{"PREMIER MOISSON GAREMONTREAL Q": "Restaurants & Coffee", "STM OPUS MONTREAL QC": "Transportation", "NETFLIX.COM": "Entertainment"}
"""


def suggest_categories(descriptions: list[str]) -> dict[str, str]:
    """
    Returns {description: category_name} for each description.
    Processes in batches of 25 to stay within token limits.
    Returns empty dict if API key is missing or call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI categorization")
        return {}

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed")
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    results: dict[str, str] = {}

    # Process in batches of 25
    batch_size = 25
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i : i + batch_size]
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(batch),
                    }
                ],
            )
            text = next((b.text for b in response.content if b.type == "text"), "")
            # Strip markdown code fences the model occasionally wraps around JSON
            text = (
                text.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            if not text:
                logger.warning(
                    "AI returned empty response for batch %d", i // batch_size
                )
                continue
            batch_result = json.loads(text)
            results.update(batch_result)
        except Exception as exc:
            logger.error("AI categorization batch %d failed: %s", i // batch_size, exc)

    return results

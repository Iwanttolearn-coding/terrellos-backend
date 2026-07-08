"""
ai_provider.py — Shared AI generation helper with automatic fallback.

Tries OpenAI first (primary, higher quality for gpt-4o). If OpenAI fails for
ANY reason (billing/quota, rate limit, outage), automatically retries the same
prompt against Perplexity's OpenAI-compatible chat completions API so
ministry-facing features (Word Study, Bible Teaching, Devotionals) stay online
instead of surfacing a 500 to the user.

Usage:
    from ai_provider import generate
    content = generate(system="...", prompt="...", max_tokens=2500, temperature=0.5)
"""
import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

_openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_perplexity_client = (
    OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
    if PERPLEXITY_API_KEY else None
)

# sonar-pro handles longer structured/scholarly output well and is Perplexity's
# closest equivalent to gpt-4o for this kind of long-form generation.
PERPLEXITY_MODEL = "sonar-pro"


def generate(system: str, prompt: str, max_tokens: int = 3000, temperature: float = 0.5,
             model: str = "gpt-4o") -> str:
    """
    Generate text using OpenAI first; automatically falls back to Perplexity
    if OpenAI fails for any reason. Raises RuntimeError only if BOTH providers
    fail (or neither is configured).
    """
    last_err = None

    if _openai_client:
        try:
            resp = _openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            logger.warning("OpenAI generation failed, falling back to Perplexity: %s", e)

    if _perplexity_client:
        try:
            resp = _perplexity_client.chat.completions.create(
                model=PERPLEXITY_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e2:
            last_err = e2
            logger.error("Perplexity fallback also failed: %s", e2)

    if last_err:
        raise RuntimeError(f"All AI providers failed. Last error: {last_err}")
    raise RuntimeError("No AI provider configured (missing OPENAI_API_KEY and PERPLEXITY_API_KEY).")

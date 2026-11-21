"""
LLM client using LiteLLM Router for multi-key failover support.

Key concepts
------------
* We configure one "model entry" per API key so the Router can round-robin /
  fail-over across keys.
* Failure simulation: when ENABLE_FAILURE_SIMULATION=true and the caller
  supplies an X-Simulate-Failure header we raise synthetic errors for specific
  key indices before touching the real API.
* We track `fallback_attempts` by counting how many model entries the router
  skipped before delivering a successful response.
"""

import os
import time
import json
from typing import List, Optional, Dict, Tuple, Any

import litellm
from litellm import Router
from litellm.exceptions import (
    RateLimitError,
    ServiceUnavailableError,
    APIError,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_MODEL_NAME = "gemini/gemini-2.0-flash"
_FAILURE_SIM_ENABLED = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"

# Parse API keys: comma-separated values
_raw_keys = os.getenv("LLM_API_KEYS", "")
API_KEYS: List[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# Fallback: at least one dummy key so the router doesn't explode at import time
if not API_KEYS:
    API_KEYS = ["dummy-key-1", "dummy-key-2"]

# ---------------------------------------------------------------------------
# Build Router model_list – one entry per API key
# ---------------------------------------------------------------------------

def _build_model_list(keys: List[str]) -> List[dict]:
    return [
        {
            "model_name": _MODEL_NAME,
            "litellm_params": {
                "model": _MODEL_NAME,
                "api_key": key,
            },
            # We store the key index so we can reference it in metadata
            "model_info": {"id": f"key_{i + 1}"},
        }
        for i, key in enumerate(keys)
    ]


_router: Optional[Router] = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = Router(
            model_list=_build_model_list(API_KEYS),
            num_retries=len(API_KEYS) - 1,
            retry_after=0,
            allowed_fails=len(API_KEYS),
        )
    return _router


def reset_router() -> None:
    """Force re-creation of the router (useful in tests)."""
    global _router
    _router = None


# ---------------------------------------------------------------------------
# Failure simulation helpers
# ---------------------------------------------------------------------------

def _parse_simulate_header(header: str) -> Dict[str, int]:
    """
    Parse 'key_1=429,key_2=500' or '*=429' into a dict.
    """
    result: Dict[str, int] = {}
    for part in header.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key_id, code_str = part.split("=", 1)
        try:
            result[key_id.strip()] = int(code_str.strip())
        except ValueError:
            pass
    return result


def _make_error(status_code: int, key_id: str) -> Exception:
    message = f"Simulated error {status_code} for {key_id}"
    if status_code == 429:
        return RateLimitError(message=message, llm_provider="google", model=_MODEL_NAME)
    elif status_code >= 500:
        return ServiceUnavailableError(message=message, llm_provider="google", model=_MODEL_NAME)
    else:
        return APIError(
            status_code=status_code,
            message=message,
            llm_provider="google",
            model=_MODEL_NAME,
        )


# ---------------------------------------------------------------------------
# Public chat function
# ---------------------------------------------------------------------------

async def chat_completion(
    messages: List[dict],
    simulate_header: Optional[str] = None,
) -> Tuple[str, dict]:
    """
    Call the LLM (or return a cached result) and return (reply_text, metadata).

    metadata keys:
        resolution_source, model, latency_ms, input_tokens, output_tokens,
        key_id, fallback_attempts
    """
    sim_map: Dict[str, int] = {}
    if _FAILURE_SIM_ENABLED and simulate_header:
        sim_map = _parse_simulate_header(simulate_header)

    # ------------------------------------------------------------------
    # With simulation: attempt each key manually so we can inject errors
    # ------------------------------------------------------------------
    if sim_map:
        return await _chat_with_simulation(messages, sim_map)

    # ------------------------------------------------------------------
    # Normal path: use LiteLLM Router
    # ------------------------------------------------------------------
    return await _chat_via_router(messages)


async def _chat_via_router(messages: List[dict]) -> Tuple[str, dict]:
    """Normal (non-simulated) completion using the LiteLLM Router."""
    router = get_router()
    t0 = time.monotonic()

    # LiteLLM cache check is transparent – if there's a hit the router returns
    # the cached response immediately.
    response = await router.acompletion(
        model=_MODEL_NAME,
        messages=messages,
        caching=True,
    )

    latency_ms = int((time.monotonic() - t0) * 1000)

    reply = response.choices[0].message.content or ""
    usage = response.usage or {}

    # Detect cache hit via LiteLLM's hidden field
    cache_hit = getattr(response, "_hidden_params", {}).get("cache_hit", False)

    # Determine which key was used
    key_id: Optional[str] = None
    fallback_attempts = 0
    if not cache_hit:
        # The router stores which deployment was used in _hidden_params
        hidden = getattr(response, "_hidden_params", {})
        model_id = hidden.get("model_id", "")
        if model_id:
            # model_id matches model_info.id from model_list e.g. "key_1"
            key_id = model_id
        else:
            key_id = "key_1"

    resolution_source = "LLM_CACHE" if cache_hit else "LIVE_INFERENCE"

    metadata = {
        "resolution_source": resolution_source,
        "model": _MODEL_NAME,
        "latency_ms": latency_ms,
        "input_tokens": getattr(usage, "prompt_tokens", 0) if hasattr(usage, "prompt_tokens") else usage.get("prompt_tokens", 0),
        "output_tokens": getattr(usage, "completion_tokens", 0) if hasattr(usage, "completion_tokens") else usage.get("completion_tokens", 0),
        "key_id": key_id if not cache_hit else None,
        "fallback_attempts": fallback_attempts,
    }

    return reply, metadata


async def _chat_with_simulation(
    messages: List[dict],
    sim_map: Dict[str, int],
) -> Tuple[str, dict]:
    """
    Manual key iteration with injected failures for simulation mode.
    Raises HTTPException-compatible ServiceUnavailableError if all keys fail.
    """
    from fastapi import HTTPException

    fallback_attempts = 0
    last_exc: Optional[Exception] = None

    for i, key in enumerate(API_KEYS):
        key_id = f"key_{i + 1}"
        status_code = sim_map.get(key_id) or sim_map.get("*")

        if status_code is not None:
            last_exc = _make_error(status_code, key_id)
            fallback_attempts += 1
            continue  # skip to next key

        # Try real call with this specific key
        t0 = time.monotonic()
        try:
            response = await litellm.acompletion(
                model=_MODEL_NAME,
                messages=messages,
                api_key=key,
                caching=True,
            )
        except Exception as exc:
            last_exc = exc
            fallback_attempts += 1
            continue

        latency_ms = int((time.monotonic() - t0) * 1000)
        reply = response.choices[0].message.content or ""
        usage = response.usage or {}

        cache_hit = getattr(response, "_hidden_params", {}).get("cache_hit", False)
        resolution_source = "LLM_CACHE" if cache_hit else "LIVE_INFERENCE"

        metadata = {
            "resolution_source": resolution_source,
            "model": _MODEL_NAME,
            "latency_ms": latency_ms,
            "input_tokens": getattr(usage, "prompt_tokens", 0) if hasattr(usage, "prompt_tokens") else usage.get("prompt_tokens", 0),
            "output_tokens": getattr(usage, "completion_tokens", 0) if hasattr(usage, "completion_tokens") else usage.get("completion_tokens", 0),
            "key_id": key_id if not cache_hit else None,
            "fallback_attempts": fallback_attempts,
        }
        return reply, metadata

    # All keys failed
    raise HTTPException(status_code=503, detail="all providers unavailable")

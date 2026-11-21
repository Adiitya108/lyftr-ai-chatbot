"""Cache configuration using LiteLLM's built-in caching."""

import litellm
from litellm.caching import Cache

_cache_enabled = False


def setup_cache() -> bool:
    """
    Initialise LiteLLM's in-memory cache.
    Returns True if cache was successfully enabled.
    """
    global _cache_enabled
    try:
        litellm.cache = Cache(type="local")  # InMemoryCache
        _cache_enabled = True
    except Exception:
        _cache_enabled = False
    return _cache_enabled


def is_cache_enabled() -> bool:
    return _cache_enabled

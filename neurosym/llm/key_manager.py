"""Thread-safe multi-provider API key pool and rate-limit cooldown manager."""

import logging
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class KeyStatus:
    """Tracks individual API key health and cooldown state."""
    key: str
    provider: str
    is_active: bool = True
    cooldown_until: float = 0.0
    failure_count: int = 0
    total_calls: int = 0


class ProviderKeyPool:
    """
    Manages API keys across multiple providers (Gemini, Groq, OpenRouter, OpenAI)
    with automatic round-robin load distribution and cooldown tracking upon 429 quota exhaustion.
    """

    def __init__(self, initial_keys: Optional[Dict[str, List[str]]] = None):
        self._lock = Lock()
        self._pools: Dict[str, List[KeyStatus]] = {
            "gemini": [],
            "groq": [],
            "openrouter": [],
            "openai": []
        }
        self._indices: Dict[str, int] = {
            "gemini": 0,
            "groq": 0,
            "openrouter": 0,
            "openai": 0
        }
        if initial_keys:
            with self._lock:
                for prov, keys in initial_keys.items():
                    self._pools[prov] = [KeyStatus(key=k, provider=prov) for k in keys if k]
        else:
            self.reload_keys_from_env()

    def reload_keys_from_env(self):
        """Reads environment variables and populates key pools."""
        with self._lock:
            self._load_provider_keys("gemini", ["GEMINI_API_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"])
            self._load_provider_keys("groq", ["GROQ_API_KEYS", "GROQ_API_KEY"])
            self._load_provider_keys("openrouter", ["OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"])
            self._load_provider_keys("openai", ["OPENAI_API_KEYS", "OPENAI_API_KEY"])

            total_keys = sum(len(v) for v in self._pools.values())
            logger.info(
                f"Loaded {total_keys} API keys into pool: "
                f"Gemini={len(self._pools['gemini'])}, "
                f"Groq={len(self._pools['groq'])}, "
                f"OpenRouter={len(self._pools['openrouter'])}, "
                f"OpenAI={len(self._pools['openai'])}"
            )

    def _load_provider_keys(self, provider: str, env_vars: List[str]):
        """Parses comma-separated or singular keys from environment variable names."""
        raw_keys = []
        for var_name in env_vars:
            val = os.environ.get(var_name, "").strip()
            if val:
                # Support comma, semicolon, or space separation
                for part in val.replace(";", ",").split(","):
                    k = part.strip()
                    if k and k not in raw_keys:
                        raw_keys.append(k)

        # Preserve existing health state if already loaded
        existing_keys = {ks.key: ks for ks in self._pools[provider]}
        new_statuses = []
        for k in raw_keys:
            if k in existing_keys:
                new_statuses.append(existing_keys[k])
            else:
                new_statuses.append(KeyStatus(key=k, provider=provider))

        self._pools[provider] = new_statuses

    def get_active_key(self, provider: str) -> Optional[str]:
        """
        Retrieves the next active (non-cooling) key for a given provider using round-robin.
        Automatically unblocks keys whose cooldown timer has expired.
        """
        with self._lock:
            pool = self._pools.get(provider, [])
            if not pool:
                return None

            now = time.time()
            # Restore expired cooldowns
            for ks in pool:
                if not ks.is_active and now >= ks.cooldown_until:
                    ks.is_active = True
                    ks.cooldown_until = 0.0
                    logger.info(f"API key for {provider} (...{ks.key[-4:] if len(ks.key) > 4 else '***'}) cooldown expired; restored to active pool.")

            active_keys = [ks for ks in pool if ks.is_active]
            if not active_keys:
                return None

            idx = self._indices[provider] % len(active_keys)
            chosen = active_keys[idx]
            self._indices[provider] = (idx + 1) % len(active_keys)
            chosen.total_calls += 1
            return chosen.key

    def mark_key_rate_limited(self, provider: str, key: str, cooldown_seconds: float = 60.0):
        """
        Places a rate-limited key into cooldown for cooldown_seconds so requests
        immediately route to alternative keys without repetitive 429 stalls.
        """
        with self._lock:
            pool = self._pools.get(provider, [])
            for ks in pool:
                if ks.key == key:
                    ks.is_active = False
                    ks.cooldown_until = time.time() + cooldown_seconds
                    ks.failure_count += 1
                    logger.warning(
                        f"Placed {provider} key (...{key[-4:] if len(key) > 4 else '***'}) in cooldown for {cooldown_seconds:.1f}s (Failures: {ks.failure_count})."
                    )
                    break

    def has_any_active_keys(self, provider: str) -> bool:
        """Checks if a provider has at least one active key ready for requests."""
        with self._lock:
            now = time.time()
            pool = self._pools.get(provider, [])
            return any(ks.is_active or now >= ks.cooldown_until for ks in pool)

    def get_all_configured_providers(self) -> List[str]:
        """Returns list of providers that have at least one key configured in total."""
        with self._lock:
            return [p for p, keys in self._pools.items() if len(keys) > 0]

    def get_pool_summary(self) -> Dict[str, Dict[str, Any]]:
        """Returns health summary across all provider pools."""
        with self._lock:
            now = time.time()
            summary = {}
            for prov, pool in self._pools.items():
                active = sum(1 for ks in pool if ks.is_active or now >= ks.cooldown_until)
                cooling = len(pool) - active
                summary[prov] = {
                    "total_keys": len(pool),
                    "active_keys": active,
                    "cooling_keys": cooling
                }
            return summary

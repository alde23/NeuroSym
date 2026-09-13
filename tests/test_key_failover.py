"""Unit tests for multi-key rotation, cooldown management, and provider failover."""

import time
from unittest.mock import patch
import pytest

from neurosym.llm.key_manager import ProviderKeyPool
from neurosym.llm.client import LLMClient


def test_key_pool_loading_and_rotation():
    """Verifies that keys are round-robin rotated."""
    pool = ProviderKeyPool(initial_keys={
        "gemini": ["gemini_key_1", "gemini_key_2", "gemini_key_3"],
        "groq": ["groq_key_1", "groq_key_2"]
    })
    
    # Check loaded counts
    summary = pool.get_pool_summary()
    assert summary["gemini"]["total_keys"] == 3
    assert summary["groq"]["total_keys"] == 2

    # Verify round-robin for Gemini
    k1 = pool.get_active_key("gemini")
    k2 = pool.get_active_key("gemini")
    k3 = pool.get_active_key("gemini")
    k4 = pool.get_active_key("gemini")

    assert k1 == "gemini_key_1"
    assert k2 == "gemini_key_2"
    assert k3 == "gemini_key_3"
    assert k4 == "gemini_key_1"  # loops back to first


def test_rate_limit_cooldown_and_exclusion():
    """Verifies that a rate-limited key is placed in cooldown and bypassed immediately."""
    pool = ProviderKeyPool(initial_keys={
        "gemini": ["key_alpha", "key_beta"]
    })

    # Mark key_alpha as rate-limited with 5s cooldown
    pool.mark_key_rate_limited("gemini", "key_alpha", cooldown_seconds=5.0)

    # Next calls should exclusively return key_beta
    assert pool.get_active_key("gemini") == "key_beta"
    assert pool.get_active_key("gemini") == "key_beta"

    # Both keys cooling down
    pool.mark_key_rate_limited("gemini", "key_beta", cooldown_seconds=5.0)
    assert pool.get_active_key("gemini") is None
    assert pool.has_any_active_keys("gemini") is False


def test_cooldown_expiration_restores_key():
    """Verifies that keys automatically restore to active once cooldown timer expires."""
    pool = ProviderKeyPool(initial_keys={
        "groq": ["groq_short_cooldown"]
    })

    # Mark with very short cooldown (0.05s)
    pool.mark_key_rate_limited("groq", "groq_short_cooldown", cooldown_seconds=0.05)
    assert pool.get_active_key("groq") is None

    time.sleep(0.08)

    # Key should be unblocked and ready
    restored_key = pool.get_active_key("groq")
    assert restored_key == "groq_short_cooldown"


def test_llm_client_cascades_to_groq_when_gemini_fails():
    """Verifies that LLMClient falls over from Gemini to Groq if Gemini hits 429."""
    pool = ProviderKeyPool(initial_keys={
        "gemini": ["fake_gemini_key"],
        "groq": ["fake_groq_key"]
    })
    client = LLMClient(key_pool=pool)

    # Mock Gemini to fail with 429
    with patch.object(client, "_call_gemini_single_key", return_value=None) as mock_gemini:
        with patch.object(client, "_call_groq_single_key", return_value={"reply": "Response from Groq", "verdict": "FEASIBLE"}) as mock_groq:
            res = client.generate_json("Test prompt")
            
            assert mock_gemini.called
            assert mock_groq.called
            assert res["reply"] == "Response from Groq"


def test_llm_client_falls_back_to_structured_engine_when_all_fail():
    """Verifies deterministic offline fallback if all provider keys fail."""
    pool = ProviderKeyPool(initial_keys={
        "gemini": ["dead_gemini_key"]
    })
    client = LLMClient(key_pool=pool)

    with patch.object(client, "_call_gemini_single_key", return_value=None):
        prompt = "Senior Horizon Europe Grants & Feasibility Advisory AI ### CURRENT USER INQUIRY: What is the budget? ###"
        res = client.generate_json(prompt)
        assert "Recommended Budget Band" in res.get("reply", "")
        assert res.get("verdict") == "FEASIBLE"

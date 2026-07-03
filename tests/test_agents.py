import os

import pytest

from app.agents import call_llm_for_generation


@pytest.mark.integration
def test_llm_openrouter_success_and_auth_error():
    # Test with the current (presumably valid) key
    result = call_llm_for_generation("Test prompt for OpenRouter success", num_hypotheses=2, temperature=0.7)
    assert isinstance(result, list)
    # If the key is valid, all returned hypotheses should not be error
    assert all(h.get("title") != "Error" for h in result)

    # Now test with an invalid key
    orig_key = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = "invalid_key_for_regression_test"
    try:
        result = call_llm_for_generation(
            "Test prompt for OpenRouter auth regression", num_hypotheses=2, temperature=0.7
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Error"
        assert "OpenRouter" in result[0]["text"] or "401" in result[0]["text"]
    finally:
        # Restore the original key
        if orig_key is not None:
            os.environ["OPENROUTER_API_KEY"] = orig_key
        else:
            del os.environ["OPENROUTER_API_KEY"]

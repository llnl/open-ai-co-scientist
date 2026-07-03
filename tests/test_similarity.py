"""Tests for app.utils.similarity_score.

Offline tests inject a stub embedding model into the module-level singleton;
the real-model test downloads from Hugging Face and is marked `network`.
"""

import pytest
import torch

import app.utils as utils


class _StubModel:
    """Deterministic stand-in for SentenceTransformer (returns torch tensors,
    matching what similarity_score expects from .encode(convert_to_tensor=True))."""

    _vectors = {
        "climate change agriculture": [1.0, 0.0, 0.0],
        "climate change farming": [0.9, 0.1, 0.0],
        "quantum computing": [0.0, 0.0, 1.0],
    }

    def encode(self, text, convert_to_tensor=False):
        return torch.tensor(self._vectors.get(text, [0.5, 0.5, 0.5]))


@pytest.fixture
def stub_model(monkeypatch):
    monkeypatch.setattr(utils, "_sentence_transformer_model", _StubModel())


def test_similar_texts_score_higher_than_different(stub_model):
    similar = utils.similarity_score("climate change agriculture", "climate change farming")
    different = utils.similarity_score("climate change agriculture", "quantum computing")
    assert similar > different


def test_score_clamped_to_unit_interval(stub_model):
    score = utils.similarity_score("climate change agriculture", "climate change farming")
    assert 0.0 <= score <= 1.0


def test_empty_string_returns_zero(stub_model):
    assert utils.similarity_score("", "anything") == 0.0
    assert utils.similarity_score("anything", "   ") == 0.0


@pytest.mark.network
def test_real_model_relative_ordering():
    """Downloads the real sentence-transformer model; run with `make test-all`."""
    high = utils.similarity_score(
        "The impact of climate change on global agriculture",
        "How climate change affects farming worldwide",
    )
    low = utils.similarity_score(
        "Quantum computing fundamentals",
        "Sustainable urban planning strategies",
    )
    assert high > low

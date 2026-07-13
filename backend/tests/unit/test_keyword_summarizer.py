import json
from datetime import date

import pytest
import requests

from reviewerfinder.discovery.keyword_summarizer import KEYWORD_SETS_SCHEMA, generate_keyword_sets
from reviewerfinder.models import Paper

VALID_RESPONSE = [
    {"label": "Methodology", "keywords": ["transformers", "attention", "sequence modeling"]},
    {"label": "Application domain", "keywords": ["protein folding", "structural biology", "proteomics"]},
    {"label": "Underlying technique", "keywords": ["deep learning", "neural networks", "representation learning"]},
    {"label": "Theoretical framework", "keywords": ["geometric deep learning", "equivariance", "graph networks"]},
    {"label": "Problem being solved", "keywords": ["structure prediction", "folding accuracy", "benchmarking"]},
]


class FakeOllamaResponse:
    def __init__(self, content_text, status_code=200):
        self._content_text = content_text
        self.status_code = status_code

    def json(self):
        return {"message": {"role": "assistant", "content": self._content_text}}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def make_paper(**overrides) -> Paper:
    defaults = dict(
        title="Deep learning for protein structure prediction",
        abstract="A transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        run_date=date.today(),
    )
    defaults.update(overrides)
    return Paper(**defaults)


def test_generate_keyword_sets_parses_valid_response(mocker):
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(json.dumps(VALID_RESPONSE)),
    )

    sets = generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")

    assert len(sets) == 5
    assert sets[0].set_index == 1
    assert sets[0].label == "Methodology"
    assert sets[0].keywords == ["transformers", "attention", "sequence modeling"]
    assert sets[4].set_index == 5


def test_generate_keyword_sets_sends_schema_constrained_format(mocker):
    """A loose "format": "json" only guarantees valid JSON syntax, not the
    specific 5-object shape -- Ollama's structured-outputs schema param is
    what actually constrains the model to the right shape.
    """
    mock_post = mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(json.dumps(VALID_RESPONSE)),
    )

    generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["format"] == KEYWORD_SETS_SCHEMA


def test_generate_keyword_sets_strips_markdown_code_fence(mocker):
    fenced = "```json\n" + json.dumps(VALID_RESPONSE) + "\n```"
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(fenced),
    )

    sets = generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")

    assert len(sets) == 5


def test_generate_keyword_sets_extracts_array_from_surrounding_prose(mocker):
    """Local models are more prone than Claude to adding a stray sentence
    despite being told not to -- the fallback [...] extraction should
    still recover the array.
    """
    wrapped = "Sure, here are the keyword sets:\n" + json.dumps(VALID_RESPONSE) + "\nHope that helps!"
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(wrapped),
    )

    sets = generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")

    assert len(sets) == 5


def test_generate_keyword_sets_raises_clear_error_when_ollama_unreachable(mocker):
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        side_effect=requests.ConnectionError("connection refused"),
    )

    with pytest.raises(RuntimeError, match="Couldn't reach Ollama"):
        generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")


def test_generate_keyword_sets_raises_on_invalid_json(mocker):
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse("not json at all"),
    )

    with pytest.raises(RuntimeError, match="wasn't valid JSON"):
        generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")


def test_generate_keyword_sets_raises_on_wrong_set_count(mocker):
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(json.dumps(VALID_RESPONSE[:3])),
    )

    with pytest.raises(RuntimeError, match="Expected 5 keyword sets"):
        generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")


def test_generate_keyword_sets_raises_on_wrong_keyword_count(mocker):
    malformed = json.loads(json.dumps(VALID_RESPONSE))
    malformed[0]["keywords"] = ["only", "two"]
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(json.dumps(malformed)),
    )

    with pytest.raises(RuntimeError, match="Malformed keyword set"):
        generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")


def test_generate_keyword_sets_raises_on_missing_label(mocker):
    malformed = json.loads(json.dumps(VALID_RESPONSE))
    del malformed[0]["label"]
    mocker.patch(
        "reviewerfinder.discovery.keyword_summarizer.requests.post",
        return_value=FakeOllamaResponse(json.dumps(malformed)),
    )

    with pytest.raises(RuntimeError, match="Malformed keyword set"):
        generate_keyword_sets(make_paper(), base_url="http://localhost:11434", model="llama3.1")

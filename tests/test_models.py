"""Tests for shared request and compatibility models."""

import pytest
from pydantic import ValidationError

from gateway.core.models import BatchKey, BatchMetadata, InferenceRequest


def test_batch_key_contains_backend_compatibility_fields() -> None:
    request = InferenceRequest(
        input_text="hello",
        model="test-model",
        max_tokens=32,
        temperature=0.25,
    )

    assert BatchKey.from_request(request) == BatchKey(
        model="test-model",
        max_tokens=32,
        temperature=0.25,
    )


def test_batch_metadata_exposes_same_batch_key() -> None:
    request = InferenceRequest(
        input_text="hello",
        model="test-model",
        max_tokens=32,
        temperature=0.25,
    )

    metadata = BatchMetadata.create(request)

    assert metadata.batch_key == BatchKey.from_request(request)


def test_inference_request_rejects_invalid_generation_values() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(input_text="hello", max_tokens=0)

    with pytest.raises(ValidationError):
        InferenceRequest(input_text="hello", temperature=2.1)

    with pytest.raises(ValidationError):
        InferenceRequest(input_text="hello", model="")

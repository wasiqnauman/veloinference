"""API tests."""

import httpx
from fastapi.testclient import TestClient

from gateway.config import Settings
from gateway.core.batcher import QueueOverloadedError
from gateway.main import create_app


def test_healthcheck() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "backend": "mock",
        "mode": "batched",
        "policy": "fixed",
    }


def test_infer_returns_batched_response_shape() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/infer",
            json={"input_text": "hello", "model": "mock"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "mock"
    assert body["output_text"] == "mock:hello|batch=1"
    assert body["batch_size"] == 1
    assert body["batch_id"]


def test_infer_pass_through_mode() -> None:
    app = create_app(Settings(gateway_mode="pass_through"))

    with TestClient(app) as client:
        response = client.post(
            "/v1/infer",
            json={"input_text": "hello", "model": "mock"},
        )

    assert response.status_code == 200
    assert response.json()["batch_id"] is None
    assert response.json()["batch_size"] == 1


def test_adaptive_policy_mode_is_available() -> None:
    app = create_app(Settings(batch_policy="adaptive"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["policy"] == "adaptive"


class _FailingService:
    async def infer(self, _payload: object, **_kwargs: object) -> object:
        raise httpx.ReadTimeout("backend timed out")


class _OverloadedService:
    async def infer(self, _payload: object, **_kwargs: object) -> object:
        raise QueueOverloadedError("full")


def test_route_maps_timeout_to_504() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.inference_service = _FailingService()
        response = client.post("/v1/infer", json={"input_text": "hello"})

    assert response.status_code == 504
    assert response.json() == {"detail": "Backend request timed out"}


def test_route_maps_queue_overload_to_503() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.inference_service = _OverloadedService()
        response = client.post("/v1/infer", json={"input_text": "hello"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Gateway queue is full"}

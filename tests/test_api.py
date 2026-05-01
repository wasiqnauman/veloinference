"""API tests."""

from fastapi.testclient import TestClient

from gateway.main import create_app


def test_healthcheck() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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

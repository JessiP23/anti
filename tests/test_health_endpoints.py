from fastapi.testclient import TestClient

from services.action.main import app as action_app
from services.decision.main import app as decision_app
from services.detector.main import app as detector_app
from services.gateway.main import app as gateway_app
from services.ml_worker.main import app as ml_worker_app


def test_gateway_health() -> None:
    response = TestClient(gateway_app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "model_version" in payload


def test_detector_health() -> None:
    response = TestClient(detector_app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "model_version" in payload


def test_decision_health() -> None:
    response = TestClient(decision_app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "model_version" in payload


def test_action_health() -> None:
    response = TestClient(action_app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "model_version" in payload


def test_ml_worker_health() -> None:
    response = TestClient(ml_worker_app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "model_version" in payload

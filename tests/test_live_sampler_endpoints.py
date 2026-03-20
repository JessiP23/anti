import importlib
import json

from fastapi.testclient import TestClient


def test_live_sampler_batch_flush_and_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GATEWAY_SAMPLER_DIR", str(tmp_path))
    monkeypatch.setenv("GATEWAY_SAMPLER_FLUSH_INTERVAL_SECONDS", "60")
    from services.gateway import main as gateway_main

    module = importlib.reload(gateway_main)
    with TestClient(module.app) as client:
        batch_res = client.post(
            "/v1/live-sampler/test-game/test-server/batch",
            json={
                "events": [
                    {
                        "player_id": "p1",
                        "session_id": "s1",
                        "event_type": "hit_registered",
                        "payload": {
                            "hit_zone": "head",
                            "distance_m": 120,
                            "server_validated": True,
                        },
                        "label": "suspicious",
                    },
                    {
                        "player_id": "p1",
                        "session_id": "s1",
                        "event_type": "player_moved",
                        "payload": {"speed": 400},
                        "label": "clean",
                    },
                ]
            },
        )
        assert batch_res.status_code == 200
        assert batch_res.json()["accepted"] == 2
        flush_res = client.post("/v1/live-sampler/test-game/test-server/flush")
        assert flush_res.status_code == 200
        assert flush_res.json()["flushed"] == 2
        status_res = client.get("/v1/live-sampler/test-game/test-server/status")
        assert status_res.status_code == 200
        status_payload = status_res.json()
        assert status_payload["buffered"] == 0
        assert status_payload["files_written"] >= 1
    files = sorted((tmp_path / "test-game" / "test-server").glob("samples_*.jsonl"))
    assert files
    lines = [line for line in files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 2
    first_record = json.loads(lines[0])
    assert "label" in first_record
    assert "event" in first_record
    assert "client_checksum" in first_record["event"]

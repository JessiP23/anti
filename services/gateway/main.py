import hashlib
import json

import httpx
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.features.schema import PlayerEvent, SessionSummary


class Settings(BaseSettings):
    version: str = "0.1.0"
    model_version: str = "dev"
    detector_url: str = "http://detector:8001"
    decision_url: str = "http://decision:8003"
    action_url: str = "http://action:8004"
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", case_sensitive=False)


settings = Settings()
app = FastAPI(title="gateway", version=settings.version)


def _checksum(event: PlayerEvent) -> str:
    payload = json.dumps(event.payload, sort_keys=True)
    raw = f"{event.event_id}{event.timestamp_ms}{payload}".encode()
    return hashlib.sha256(raw).hexdigest()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version, "model_version": settings.model_version}


@app.post("/v1/summary")
async def ingest_summary(summary: SessionSummary) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.post(
            f"{settings.decision_url}/score-summary",
            json=summary.model_dump(),
        )
        result.raise_for_status()
    return {"status": "ok"}


@app.post("/v1/event")
async def ingest_event(event: PlayerEvent) -> dict[str, str | float]:
    if _checksum(event) != event.client_checksum:
        raise HTTPException(status_code=400, detail="checksum_mismatch")
    async with httpx.AsyncClient(timeout=10.0) as client:
        detector_res = await client.post(
            f"{settings.detector_url}/score-event",
            json=event.model_dump(),
        )
        detector_res.raise_for_status()
        detector_data = detector_res.json()
        decision_payload = {
            "player_id": event.player_id,
            "session_id": event.session_id,
            "detector_score": detector_data["score"],
            "signals": detector_data["signals"],
        }
        decision_res = await client.post(f"{settings.decision_url}/decide", json=decision_payload)
        decision_res.raise_for_status()
        decision_data = decision_res.json()
        if decision_data["decision"] in {"auto_shadow_ban", "auto_flag"}:
            await client.post(
                f"{settings.action_url}/act",
                json={
                    "player_id": event.player_id,
                    "session_id": event.session_id,
                    "decision": decision_data["decision"],
                    "score": decision_data["score"],
                },
            )
    return {
        "status": "ok",
        "detector_score": detector_data["score"],
        "decision_score": decision_data["score"],
        "decision": decision_data["decision"],
    }

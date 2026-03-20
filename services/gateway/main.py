import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.features.schema import EventType, PlayerEvent, SessionSummary


class Settings(BaseSettings):
    version: str = "0.1.0"
    model_version: str = "dev"
    detector_url: str = "http://detector:8001"
    decision_url: str = "http://decision:8003"
    action_url: str = "http://action:8004"
    sampler_dir: str = "data/live_samples"
    sampler_flush_interval_seconds: int = 5
    sampler_max_records_per_file: int = 1000
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", case_sensitive=False)


settings = Settings()
app = FastAPI(title="gateway", version=settings.version)
_sampler_lock = asyncio.Lock()
_sampler_records: dict[str, list[dict[str, Any]]] = {}
_sampler_file_index: dict[str, int] = {}
_sampler_record_count: dict[str, int] = {}
_sampler_last_flush_ms: dict[str, int] = {}
_sampler_meta: dict[str, tuple[str, str]] = {}
_sampler_task: asyncio.Task[Any] | None = None


class RawSamplerEvent(BaseModel):
    player_id: str
    session_id: str
    event_type: EventType
    payload: dict[str, Any]
    label: str = "unknown"
    sdk_version: str = "live_sampler"
    timestamp_ms: int | None = None


class LiveSamplerBatchRequest(BaseModel):
    events: list[RawSamplerEvent] = Field(default_factory=list)


def _sampler_key(game_id: str, server_id: str) -> str:
    return f"{game_id}::{server_id}"


def _sampler_base_path(game_id: str, server_id: str) -> Path:
    return Path(settings.sampler_dir) / game_id / server_id


def _build_sample_record(game_id: str, server_id: str, event: RawSamplerEvent) -> dict[str, Any]:
    timestamp_ms = event.timestamp_ms or int(time.time() * 1000)
    event_id = str(uuid.uuid4())
    payload = json.dumps(event.payload, sort_keys=True)
    checksum = hashlib.sha256(f"{event_id}{timestamp_ms}{payload}".encode()).hexdigest()
    return {
        "label": event.label,
        "captured_at_ms": timestamp_ms,
        "event": {
            "event_id": event_id,
            "game_id": game_id,
            "server_id": server_id,
            "player_id": event.player_id,
            "session_id": event.session_id,
            "timestamp_ms": timestamp_ms,
            "event_type": event.event_type,
            "payload": event.payload,
            "client_checksum": checksum,
            "sdk_version": event.sdk_version,
        },
    }


def _flush_sampler_locked(key: str, game_id: str, server_id: str) -> int:
    records = _sampler_records.get(key, [])
    if not records:
        _sampler_last_flush_ms[key] = int(time.time() * 1000)
        return 0
    base = _sampler_base_path(game_id=game_id, server_id=server_id)
    base.mkdir(parents=True, exist_ok=True)
    index = _sampler_file_index.get(key, 0)
    count = _sampler_record_count.get(key, 0)
    for record in records:
        if count >= settings.sampler_max_records_per_file:
            index += 1
            count = 0
        target = base / f"samples_{index:06d}.jsonl"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        count += 1
    flushed = len(records)
    _sampler_records[key] = []
    _sampler_file_index[key] = index
    _sampler_record_count[key] = count
    _sampler_last_flush_ms[key] = int(time.time() * 1000)
    return flushed


async def _sampler_flush_loop() -> None:
    interval_ms = settings.sampler_flush_interval_seconds * 1000
    while True:
        await asyncio.sleep(1)
        now = int(time.time() * 1000)
        async with _sampler_lock:
            for key, records in list(_sampler_records.items()):
                if not records:
                    continue
                last_flush = _sampler_last_flush_ms.get(key, now)
                if now - last_flush < interval_ms:
                    continue
                game_id, server_id = _sampler_meta[key]
                _flush_sampler_locked(key=key, game_id=game_id, server_id=server_id)


@app.on_event("startup")
async def startup() -> None:
    global _sampler_task
    _sampler_task = asyncio.create_task(_sampler_flush_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    if _sampler_task:
        _sampler_task.cancel()
        try:
            await _sampler_task
        except asyncio.CancelledError:
            pass


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
async def ingest_event(event: PlayerEvent) -> dict[str, Any]:
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
        "signals": detector_data["signals"],
        "detector_model_version": detector_data["model_version"],
        "decision_score": decision_data["score"],
        "decision": decision_data["decision"],
    }


@app.post("/v1/live-sampler/{game_id}/{server_id}/batch")
async def ingest_live_sampler_batch(
    game_id: str,
    server_id: str,
    payload: LiveSamplerBatchRequest,
) -> dict[str, Any]:
    key = _sampler_key(game_id=game_id, server_id=server_id)
    async with _sampler_lock:
        _sampler_meta[key] = (game_id, server_id)
        _sampler_records.setdefault(key, [])
        _sampler_last_flush_ms.setdefault(key, int(time.time() * 1000))
        for event in payload.events:
            _sampler_records[key].append(_build_sample_record(game_id, server_id, event))
        buffered = len(_sampler_records[key])
        flushed = 0
        interval_ms = settings.sampler_flush_interval_seconds * 1000
        now = int(time.time() * 1000)
        last_flush = _sampler_last_flush_ms.get(key, now)
        if now - last_flush >= interval_ms:
            flushed = _flush_sampler_locked(key=key, game_id=game_id, server_id=server_id)
            buffered = len(_sampler_records[key])
    return {
        "status": "ok",
        "accepted": len(payload.events),
        "buffered": buffered,
        "flushed": flushed,
        "flush_interval_seconds": settings.sampler_flush_interval_seconds,
    }


@app.post("/v1/live-sampler/{game_id}/{server_id}/flush")
async def flush_live_sampler(game_id: str, server_id: str) -> dict[str, Any]:
    key = _sampler_key(game_id=game_id, server_id=server_id)
    async with _sampler_lock:
        _sampler_meta[key] = (game_id, server_id)
        _sampler_records.setdefault(key, [])
        flushed = _flush_sampler_locked(key=key, game_id=game_id, server_id=server_id)
        buffered = len(_sampler_records[key])
    return {"status": "ok", "flushed": flushed, "buffered": buffered}


@app.get("/v1/live-sampler/{game_id}/{server_id}/status")
async def live_sampler_status(game_id: str, server_id: str) -> dict[str, Any]:
    key = _sampler_key(game_id=game_id, server_id=server_id)
    async with _sampler_lock:
        buffered = len(_sampler_records.get(key, []))
        file_index = _sampler_file_index.get(key, 0)
        record_count = _sampler_record_count.get(key, 0)
    base = _sampler_base_path(game_id=game_id, server_id=server_id)
    files = sorted(base.glob("samples_*.jsonl")) if base.exists() else []
    return {
        "status": "ok",
        "buffered": buffered,
        "file_index": file_index,
        "current_file_records": record_count,
        "files_written": len(files),
        "output_dir": str(base.resolve()),
        "flush_interval_seconds": settings.sampler_flush_interval_seconds,
        "max_records_per_file": settings.sampler_max_records_per_file,
    }

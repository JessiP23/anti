import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .local_scorer import LocalScorer


@dataclass
class AntiCheatClient:
    game_id: str
    server_id: str
    player_id: str
    session_id: str
    gateway_url: str
    sdk_version: str = "0.1.0"
    max_speed: float = 800.0

    def new_session(self) -> "AntiCheatSession":
        return AntiCheatSession(client=self, scorer=LocalScorer(max_speed=self.max_speed))


@dataclass
class AntiCheatSession:
    client: AntiCheatClient
    scorer: LocalScorer

    def _build_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        now = timestamp_ms or int(time.time() * 1000)
        event_id = str(uuid.uuid4())
        serialized = json.dumps(payload, sort_keys=True)
        checksum = hashlib.sha256(f"{event_id}{now}{serialized}".encode()).hexdigest()
        return {
            "event_id": event_id,
            "game_id": self.client.game_id,
            "server_id": self.client.server_id,
            "player_id": self.client.player_id,
            "session_id": self.client.session_id,
            "timestamp_ms": now,
            "event_type": event_type,
            "payload": payload,
            "client_checksum": checksum,
            "sdk_version": self.client.sdk_version,
        }

    def _update_local_scorer(
        self,
        event_type: str,
        payload: dict[str, Any],
        timestamp_ms: int,
    ) -> None:
        if event_type == "shot_fired":
            self.scorer.on_shot_fired(float(timestamp_ms))
        if event_type == "input_frame":
            delta = payload.get("mouse_delta", [0.0, 0.0])
            if isinstance(delta, list) and len(delta) >= 2:
                self.scorer.on_mouse_move(float(delta[0]), float(delta[1]))
        if event_type == "player_moved":
            speed = float(payload.get("speed", 0.0))
            self.scorer.on_move(speed)

    def capture_sample(
        self,
        event_type: str,
        payload: dict[str, Any],
        sample_path: str,
        label: str = "unknown",
    ) -> dict[str, Any]:
        now = int(time.time() * 1000)
        event = self._build_event(event_type=event_type, payload=payload, timestamp_ms=now)
        record = {"label": label, "captured_at_ms": now, "event": event}
        path = Path(sample_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return record

    async def replay_samples(self, sample_path: str) -> dict[str, Any]:
        path = Path(sample_path)
        sent = 0
        flagged = 0
        failed = 0
        async with httpx.AsyncClient(timeout=10.0) as http:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                event = record["event"]
                response = await http.post(f"{self.client.gateway_url}/v1/event", json=event)
                if response.status_code >= 400:
                    failed += 1
                    continue
                sent += 1
                decision = response.json().get("decision")
                if decision in {"auto_flag", "auto_shadow_ban"}:
                    flagged += 1
        return {"sent": sent, "flagged": flagged, "failed": failed}

    async def emit_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time() * 1000)
        self._update_local_scorer(event_type=event_type, payload=payload, timestamp_ms=now)
        event = self._build_event(event_type=event_type, payload=payload, timestamp_ms=now)
        risk = self.scorer.compute_risk_score()
        if risk < 0.3:
            return {"status": "dropped_local", "risk": risk}
        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.post(f"{self.client.gateway_url}/v1/event", json=event)
            response.raise_for_status()
            data = response.json()
        return {"status": "sent", "risk": risk, "response": data}


@dataclass
class LiveSamplerSender:
    game_id: str
    server_id: str
    gateway_url: str
    player_id: str
    session_id: str
    sdk_version: str = "0.1.0"
    batch_size: int = 25
    flush_interval_seconds: int = 3
    timeout_seconds: float = 10.0
    http_client: httpx.AsyncClient | None = None
    _buffer: list[dict[str, Any]] = field(default_factory=list)
    _last_flush_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    _owned_client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def _batch_url(self) -> str:
        return f"{self.gateway_url}/v1/live-sampler/{self.game_id}/{self.server_id}/batch"

    def _flush_url(self) -> str:
        return f"{self.gateway_url}/v1/live-sampler/{self.game_id}/{self.server_id}/flush"

    def _status_url(self) -> str:
        return f"{self.gateway_url}/v1/live-sampler/{self.game_id}/{self.server_id}/status"

    def _build_raw_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        label: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": payload,
            "label": label,
            "sdk_version": self.sdk_version,
            "timestamp_ms": timestamp_ms or int(time.time() * 1000),
        }

    def _should_flush(self) -> bool:
        if len(self._buffer) >= self.batch_size:
            return True
        elapsed_ms = int(time.time() * 1000) - self._last_flush_ms
        return elapsed_ms >= self.flush_interval_seconds * 1000

    def _client(self) -> httpx.AsyncClient:
        if self.http_client:
            return self.http_client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._owned_client

    async def enqueue_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        label: str = "unknown",
        timestamp_ms: int | None = None,
    ) -> dict[str, int]:
        self._buffer.append(
            self._build_raw_event(
                event_type=event_type,
                payload=payload,
                label=label,
                timestamp_ms=timestamp_ms,
            )
        )
        flushed = 0
        if self._should_flush():
            flushed = await self.flush()
        return {"buffered": len(self._buffer), "flushed": flushed}

    async def flush(self) -> int:
        if not self._buffer:
            return 0
        payload = {"events": self._buffer}
        response = await self._client().post(self._batch_url(), json=payload)
        response.raise_for_status()
        flushed = len(self._buffer)
        self._buffer = []
        self._last_flush_ms = int(time.time() * 1000)
        return flushed

    async def force_flush_remote(self) -> dict[str, Any]:
        response = await self._client().post(self._flush_url())
        response.raise_for_status()
        return response.json()

    async def status(self) -> dict[str, Any]:
        response = await self._client().get(self._status_url())
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        if self._buffer:
            await self.flush()
        if self._owned_client:
            await self._owned_client.aclose()
            self._owned_client = None

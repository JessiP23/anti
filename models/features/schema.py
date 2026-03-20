from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class EventType(StrEnum):
    SHOT_FIRED = "shot_fired"
    HIT_REGISTERED = "hit_registered"
    PLAYER_MOVED = "player_moved"
    INPUT_FRAME = "input_frame"
    SESSION_SUMMARY = "session_summary"


class PlayerEvent(BaseModel):
    event_id: str
    game_id: str
    server_id: str
    player_id: str
    session_id: str
    timestamp_ms: int
    event_type: EventType
    payload: dict[str, Any]
    client_checksum: str
    sdk_version: str


class SummaryFeatures(BaseModel):
    headshot_rate: float
    avg_reaction_time_ms: float
    snap_velocity_p95: float
    aim_jitter_variance: float
    pre_shot_correction_avg: float
    recoil_entropy: float
    trigger_interval_cv: float
    burst_autocorr: float
    shots_fired: int
    hits_registered: int
    avg_speed: float
    max_speed: float
    movement_entropy: float
    strafe_period_detected: float
    path_curvature_var: float
    kills: int
    deaths: int
    assists: int
    playtime_seconds: int
    map_id: str
    game_mode: str


class SessionSummary(BaseModel):
    game_id: str
    player_id: str
    session_id: str
    window_start_ms: int
    window_end_ms: int
    sdk_version: str
    features: SummaryFeatures

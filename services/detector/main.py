import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from sklearn.ensemble import IsolationForest

from models.features.compute import build_feature_vector
from models.features.schema import PlayerEvent


class Settings(BaseSettings):
    version: str = "0.1.0"
    model_version: str = "iso_v1"
    max_speed: float = 800.0
    model_config = SettingsConfigDict(env_prefix="DETECTOR_", case_sensitive=False)


class DetectionResponse(BaseModel):
    score: float
    signals: list[str]
    model_version: str


settings = Settings()
app = FastAPI(title="detector", version=settings.version)
iso_forest = IsolationForest(contamination=0.01, random_state=42)
iso_forest.fit(np.random.normal(size=(300, 48)))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version, "model_version": settings.model_version}


@app.post("/score-event", response_model=DetectionResponse)
async def score_event(event: PlayerEvent) -> DetectionResponse:
    signals: list[str] = []
    payload = event.payload
    if event.event_type == "hit_registered" and payload.get("hit_zone") == "head":
        if payload.get("distance_m", 0) > 90:
            signals.append("impossible_headshot")
    if event.event_type == "player_moved":
        if float(payload.get("speed", 0.0)) > settings.max_speed * 1.08:
            signals.append("speed_hack")
    if event.event_type == "shot_fired":
        if int(payload.get("trigger_interval_ms", 9999)) < 8:
            signals.append("trigger_bot")
    vector = build_feature_vector([event]).reshape(1, -1)
    iso_score = float(-iso_forest.score_samples(vector)[0])
    iso_prob = max(0.0, min(1.0, iso_score))
    rule_score = 1.0 if signals else 0.0
    score = (rule_score * 0.7) + (iso_prob * 0.3)
    return DetectionResponse(score=score, signals=signals, model_version=settings.model_version)

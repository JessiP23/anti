from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.features.schema import SessionSummary


class Settings(BaseSettings):
    version: str = "0.1.0"
    model_version: str = "decision_v1"
    auto_shadow_ban: float = 0.95
    auto_flag: float = 0.8
    escalate_ml: float = 0.5
    monitor: float = 0.3
    clear: float = 0.15
    model_config = SettingsConfigDict(env_prefix="DECISION_", case_sensitive=False)


class DecisionInput(BaseModel):
    player_id: str
    session_id: str
    detector_score: float
    signals: list[str]
    clean_hours: int = 0


class DecisionOutput(BaseModel):
    player_id: str
    session_id: str
    decision: str
    score: float


settings = Settings()
app = FastAPI(title="decision", version=settings.version)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version, "model_version": settings.model_version}


def _adjust_score(score: float, clean_hours: int) -> float:
    if clean_hours > 200:
        return score * 0.7
    return score


def _decision(score: float) -> str:
    if score >= settings.auto_shadow_ban:
        return "auto_shadow_ban"
    if score >= settings.auto_flag:
        return "auto_flag"
    if score >= settings.escalate_ml:
        return "escalate_ml"
    if score >= settings.monitor:
        return "monitor"
    if score >= settings.clear:
        return "clear"
    return "clear"


@app.post("/decide", response_model=DecisionOutput)
async def decide(payload: DecisionInput) -> DecisionOutput:
    score = _adjust_score(payload.detector_score, payload.clean_hours)
    return DecisionOutput(
        player_id=payload.player_id,
        session_id=payload.session_id,
        decision=_decision(score),
        score=score,
    )


@app.post("/score-summary")
async def score_summary(summary: SessionSummary) -> dict[str, str]:
    return {"status": "ok", "player_id": summary.player_id}

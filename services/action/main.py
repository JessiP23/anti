from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    version: str = "0.1.0"
    model_version: str = "action_v1"
    model_config = SettingsConfigDict(env_prefix="ACTION_", case_sensitive=False)


class ActionRequest(BaseModel):
    player_id: str
    session_id: str
    decision: str
    score: float


settings = Settings()
app = FastAPI(title="action", version=settings.version)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version, "model_version": settings.model_version}


@app.post("/act")
async def act(payload: ActionRequest) -> dict[str, str]:
    if payload.decision == "auto_shadow_ban":
        action = "shadow_ban"
    elif payload.decision == "auto_flag":
        action = "flag"
    else:
        action = "monitor"
    return {"status": "ok", "action": action, "player_id": payload.player_id}

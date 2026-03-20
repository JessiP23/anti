import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import xgboost as xgb
except Exception:
    xgb = None


class Settings(BaseSettings):
    version: str = "0.1.0"
    model_version: str = "xgb_v1"
    model_config = SettingsConfigDict(env_prefix="ML_WORKER_", case_sensitive=False)


class ScoreRequest(BaseModel):
    features: list[float]


class ScoreResponse(BaseModel):
    score: float
    model_version: str


settings = Settings()
app = FastAPI(title="ml_worker", version=settings.version)
_weights = np.random.normal(size=(48,))
if xgb is not None:
    _model = xgb.XGBClassifier(n_estimators=10, max_depth=3, learning_rate=0.2)
    _x = np.random.normal(size=(100, 48))
    _y = np.random.randint(0, 2, size=(100,))
    _model.fit(_x, _y)
else:
    _model = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version, "model_version": settings.model_version}


@app.post("/score", response_model=ScoreResponse)
async def score(payload: ScoreRequest) -> ScoreResponse:
    vector = np.array(payload.features, dtype=np.float32).reshape(1, -1)
    if _model is not None:
        probability = float(_model.predict_proba(vector)[0, 1])
    else:
        raw = float(np.dot(vector[0], _weights) / (np.linalg.norm(_weights) + 1e-6))
        probability = float(1 / (1 + np.exp(-raw)))
    return ScoreResponse(score=probability, model_version=settings.model_version)

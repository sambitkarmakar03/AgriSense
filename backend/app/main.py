from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, diagnosis, fields, irrigation, knowledge_base, readings, system, weather
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="AgriSense API",
    description=(
        "Explainable irrigation decision support and four-class crop-leaf model inference. "
        "Disease-rule fusion and human review workflows are not yet implemented."
    ),
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

for route_module in (auth, fields, readings, weather, irrigation, knowledge_base, system, diagnosis):
    app.include_router(route_module.router)

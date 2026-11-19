"""Placeholder router for the future crop-disease diagnosis phase.

No diagnosis endpoints are registered yet. Image validation, ONNX inference,
heatmaps, feedback, and review workflows will be implemented in a later phase.
"""

from fastapi import APIRouter

router = APIRouter(tags=["diagnosis (future integration)"])

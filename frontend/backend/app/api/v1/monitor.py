from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.telemetry_kpi import compute_telemetry_kpi, resolve_telemetry_csv_path

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/telemetry-kpi")
def telemetry_kpi() -> dict:
    settings = get_settings()
    csv_path = resolve_telemetry_csv_path(settings.telemetry_csv_path)

    try:
        data = compute_telemetry_kpi(csv_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"ok": True, "data": data, "source": str(csv_path)}

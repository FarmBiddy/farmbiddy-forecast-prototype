"""
Shell integration: capability discovery + dispatcher endpoints.

These routes are intentionally additive and do not change existing
`/farmer/*` behaviour.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path

from identity.access import FarmAccessDeniedError
from identity.context import RequestIdentity, get_current_identity
from models.api_models import (
    CapabilityListResponse,
    CapabilityRunRequest,
    CapabilityRunResponse,
)
from services.category_budget_service import CategoryBudgetNotFoundError
from services.document_service import DocumentNotFoundError
from services.financial_record_service import FinancialRecordNotFoundError
from services.capability_registry import get_capability, list_capabilities
from services.farmer_dashboard_service import resolve_farm_file, resolve_sectors


router = APIRouter(tags=["Capabilities"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get(
    "/v1/capabilities",
    response_model=CapabilityListResponse,
    summary="List shell-callable capabilities (discovery).",
)
def capabilities_list():
    return CapabilityListResponse(capabilities=list_capabilities())


@router.post(
    "/v1/capabilities/{key}/run",
    response_model=CapabilityRunResponse,
    summary="Run a shell-callable capability and return JSON output.",
)
def capabilities_run(
    key: str = Path(..., description="Capability key, e.g. dashboard.preview"),
    request: CapabilityRunRequest | None = None,
    identity: RequestIdentity = Depends(get_current_identity),
):
    if request is None:
        # Defensive: FastAPI should populate this, but keeps error messaging nicer.
        raise HTTPException(status_code=400, detail="Missing request body.")

    cap = get_capability(key)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"Unknown capability: {key}")

    farm_file = resolve_farm_file(request.farm_file)
    sectors_used = resolve_sectors(request.sectors, farm_id=farm_file)

    missing = [p for p in cap.required_params if p not in request.params]
    if missing:
        raise HTTPException(status_code=422, detail={"missing_params": missing})

    try:
        result = cap.handler(farm_file, sectors_used, request.params, identity)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FinancialRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CategoryBudgetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FarmAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    meta: Dict[str, Any] = {
        "farm_file": farm_file,
        "sectors_used": sectors_used,
        "generated_at": _now_iso(),
    }

    return CapabilityRunResponse(capability_key=key, meta=meta, result=result)


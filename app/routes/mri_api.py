"""
app/routes/mri_api.py
======================
Maya Revenue MRI — backend foundation.

CRUD over mri_scans / mri_intake / mri_probes / mri_reports.
No probe execution, no AI calls, no report generation, no scheduling —
this module persists records only. Probes/scoring/reporting land in
later phases.

Supabase access uses the existing service-key + httpx REST pattern
(matches app/routes/appointment_followup_api.py and
app/services/lead_capture.py). The service key bypasses RLS.

Endpoints:
    POST   /mri/scans                        create scan
    GET    /mri/scans                        list scans (filter by client_id, status)
    GET    /mri/scans/{scan_id}              fetch scan + intake + probes + reports
    PATCH  /mri/scans/{scan_id}              update allow-listed scan fields
    POST   /mri/scans/{scan_id}/intake       create or update intake row
    POST   /mri/scans/{scan_id}/probes       insert probe placeholders (no execution)
"""

import logging
import os
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.mri_probe_runner import (
    ProbeAlreadyExecutedError,
    ProbeRunnerError,
    SUPPORTED_PROBE_TYPES,
    run_probe,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_T_SCANS = "mri_scans"
_T_INTAKE = "mri_intake"
_T_PROBES = "mri_probes"
_T_REPORTS = "mri_reports"

_REST_TIMEOUT = 10.0

_PATCHABLE_SCAN_FIELDS = {
    "status",
    "maya_score",
    "revenue_at_risk_monthly",
    "recoverable_monthly",
    "top_leaks",
    "metadata",
}


def _headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _ensure_supabase_configured() -> None:
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase env not configured")


# ─────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────

class CreateScanRequest(BaseModel):
    client_id: str
    clinic_name: str
    vertical: Optional[str] = None
    metadata: Optional[dict] = None


class UpdateScanRequest(BaseModel):
    status: Optional[str] = None
    maya_score: Optional[float] = None
    revenue_at_risk_monthly: Optional[float] = None
    recoverable_monthly: Optional[float] = None
    top_leaks: Optional[List[Any]] = None
    metadata: Optional[dict] = None


class IntakeRequest(BaseModel):
    questionnaire_json: Optional[dict] = None
    funnel_metrics_json: Optional[dict] = None
    uploaded_files_json: Optional[List[Any]] = None


class ProbePlaceholder(BaseModel):
    probe_type: str
    persona_json: Optional[dict] = None
    scheduled_at: Optional[str] = None  # ISO 8601 timestamptz


class CreateProbesRequest(BaseModel):
    probes: List[ProbePlaceholder] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/mri/scans")
async def create_scan(req: CreateScanRequest):
    _ensure_supabase_configured()

    payload: dict = {
        "client_id": req.client_id,
        "clinic_name": req.clinic_name,
    }
    if req.vertical is not None:
        payload["vertical"] = req.vertical
    if req.metadata is not None:
        payload["metadata"] = req.metadata

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_T_SCANS}",
            json=payload,
            headers=_headers(),
        )
        if resp.status_code >= 400:
            logger.error(
                "[MRI] create_scan failed client_id=%s status=%s body=%s",
                req.client_id, resp.status_code, resp.text,
            )
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()

    scan = rows[0] if isinstance(rows, list) and rows else rows
    logger.info(
        "[MRI] create_scan client_id=%s clinic=%s scan_id=%s",
        req.client_id, req.clinic_name, scan.get("id") if isinstance(scan, dict) else None,
    )
    return scan


@router.get("/mri/scans")
async def list_scans(client_id: Optional[str] = None, status: Optional[str] = None):
    _ensure_supabase_configured()

    params: dict = {"select": "*", "order": "created_at.desc"}
    if client_id:
        params["client_id"] = f"eq.{client_id}"
    if status:
        params["status"] = f"eq.{status}"

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_SCANS}",
            params=params,
            headers=_headers("count=none"),
        )
        if resp.status_code >= 400:
            logger.error(
                "[MRI] list_scans failed client_id=%s status_filter=%s status=%s body=%s",
                client_id, status, resp.status_code, resp.text,
            )
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()

    logger.info(
        "[MRI] list_scans client_id=%s status=%s count=%d",
        client_id, status, len(rows),
    )
    return {"scans": rows}


@router.get("/mri/scans/{scan_id}")
async def get_scan(scan_id: str):
    _ensure_supabase_configured()

    h = _headers("count=none")
    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        scan_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_SCANS}",
            params={"id": f"eq.{scan_id}", "select": "*"},
            headers=h,
        )
        if scan_resp.status_code >= 400:
            logger.error(
                "[MRI] get_scan scan fetch failed scan_id=%s status=%s body=%s",
                scan_id, scan_resp.status_code, scan_resp.text,
            )
            raise HTTPException(status_code=scan_resp.status_code, detail=scan_resp.text)
        scans = scan_resp.json()
        if not scans:
            raise HTTPException(status_code=404, detail="Scan not found")

        intake_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_INTAKE}",
            params={"scan_id": f"eq.{scan_id}", "select": "*"},
            headers=h,
        )
        probes_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
            params={"scan_id": f"eq.{scan_id}", "select": "*", "order": "created_at.asc"},
            headers=h,
        )
        reports_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_REPORTS}",
            params={"scan_id": f"eq.{scan_id}", "select": "*", "order": "version.desc"},
            headers=h,
        )

    intake_rows = intake_resp.json() if intake_resp.status_code < 400 else []
    probe_rows = probes_resp.json() if probes_resp.status_code < 400 else []
    report_rows = reports_resp.json() if reports_resp.status_code < 400 else []

    bundle = {
        "scan": scans[0],
        "intake": intake_rows[0] if intake_rows else None,
        "probes": probe_rows,
        "reports": report_rows,
    }
    logger.info(
        "[MRI] get_scan scan_id=%s probes=%d reports=%d intake=%s",
        scan_id, len(probe_rows), len(report_rows), bool(intake_rows),
    )
    return bundle


@router.patch("/mri/scans/{scan_id}")
async def update_scan(scan_id: str, req: UpdateScanRequest):
    _ensure_supabase_configured()

    body = req.model_dump(exclude_none=True)
    if not body:
        raise HTTPException(status_code=400, detail="No updatable fields supplied")

    disallowed = set(body.keys()) - _PATCHABLE_SCAN_FIELDS
    if disallowed:
        raise HTTPException(
            status_code=400,
            detail=f"Disallowed fields: {sorted(disallowed)}",
        )

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        resp = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_T_SCANS}",
            params={"id": f"eq.{scan_id}"},
            json=body,
            headers=_headers(),
        )
        if resp.status_code >= 400:
            logger.error(
                "[MRI] update_scan failed scan_id=%s status=%s body=%s",
                scan_id, resp.status_code, resp.text,
            )
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()

    if not rows:
        raise HTTPException(status_code=404, detail="Scan not found")

    logger.info(
        "[MRI] update_scan scan_id=%s fields=%s",
        scan_id, sorted(body.keys()),
    )
    return rows[0]


@router.post("/mri/scans/{scan_id}/intake")
async def upsert_intake(scan_id: str, req: IntakeRequest):
    _ensure_supabase_configured()

    fields: dict = {}
    if req.questionnaire_json is not None:
        fields["questionnaire_json"] = req.questionnaire_json
    if req.funnel_metrics_json is not None:
        fields["funnel_metrics_json"] = req.funnel_metrics_json
    if req.uploaded_files_json is not None:
        fields["uploaded_files_json"] = req.uploaded_files_json

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        existing = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_INTAKE}",
            params={"scan_id": f"eq.{scan_id}", "select": "id"},
            headers=_headers("count=none"),
        )
        if existing.status_code >= 400:
            logger.error(
                "[MRI] upsert_intake lookup failed scan_id=%s status=%s body=%s",
                scan_id, existing.status_code, existing.text,
            )
            raise HTTPException(status_code=existing.status_code, detail=existing.text)
        existing_rows = existing.json()

        if existing_rows:
            intake_id = existing_rows[0]["id"]
            action = "updated"
            if not fields:
                # Nothing to update — return the existing row.
                fetch = await client.get(
                    f"{_SUPABASE_URL}/rest/v1/{_T_INTAKE}",
                    params={"id": f"eq.{intake_id}", "select": "*"},
                    headers=_headers("count=none"),
                )
                if fetch.status_code >= 400:
                    raise HTTPException(status_code=fetch.status_code, detail=fetch.text)
                fetched = fetch.json()
                logger.info(
                    "[MRI] upsert_intake scan_id=%s action=noop intake_id=%s",
                    scan_id, intake_id,
                )
                return fetched[0] if fetched else None

            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_T_INTAKE}",
                params={"id": f"eq.{intake_id}"},
                json=fields,
                headers=_headers(),
            )
        else:
            action = "created"
            payload = {"scan_id": scan_id, **fields}
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_T_INTAKE}",
                json=payload,
                headers=_headers(),
            )

        if resp.status_code >= 400:
            logger.error(
                "[MRI] upsert_intake %s failed scan_id=%s status=%s body=%s",
                action, scan_id, resp.status_code, resp.text,
            )
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        intake_rows = resp.json()

    intake = intake_rows[0] if isinstance(intake_rows, list) and intake_rows else intake_rows
    logger.info(
        "[MRI] upsert_intake scan_id=%s action=%s intake_id=%s",
        scan_id, action,
        intake.get("id") if isinstance(intake, dict) else None,
    )
    return intake


@router.post("/mri/probes/{probe_id}/run")
async def run_probe_endpoint(probe_id: str):
    """
    Execute a single probe (P1_wa_offhours or P2_call_peak only in this MVP).

    Loads the probe + parent scan, dispatches by probe_type, persists the
    result (status, executed_at, metadata_json, transcript), and returns
    the updated probe row.

    Configuration / validation failures (missing target number, unsupported
    probe_type, missing Twilio creds, etc.) → 400.
    External Twilio errors → row is persisted with status='error' and the
    response is the updated row (not a 5xx) so the caller can inspect it.
    """
    _ensure_supabase_configured()
    try:
        result = await run_probe(probe_id)
    except ProbeAlreadyExecutedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ProbeRunnerError as exc:
        logger.error("[MRI-PROBE] probe_error probe_id=%s error=%s", probe_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("/mri/scans/{scan_id}/probes")
async def create_probe_placeholders(scan_id: str, req: CreateProbesRequest):
    _ensure_supabase_configured()

    if not req.probes:
        raise HTTPException(status_code=400, detail="probes array is empty")

    rows_to_insert: List[dict] = []
    for p in req.probes:
        row: dict = {"scan_id": scan_id, "probe_type": p.probe_type}
        if p.persona_json is not None:
            row["persona_json"] = p.persona_json
        if p.scheduled_at is not None:
            row["scheduled_at"] = p.scheduled_at
        rows_to_insert.append(row)

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
            json=rows_to_insert,
            headers=_headers(),
        )
        if resp.status_code >= 400:
            logger.error(
                "[MRI] create_probe_placeholders failed scan_id=%s status=%s body=%s",
                scan_id, resp.status_code, resp.text,
            )
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()

    logger.info(
        "[MRI] create_probe_placeholders scan_id=%s count=%d types=%s",
        scan_id, len(rows), [p.probe_type for p in req.probes],
    )
    return {"probes": rows}

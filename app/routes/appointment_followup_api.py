"""
app/routes/appointment_followup_api.py
=======================================
GET /followup/due — returns leads that need an appointment follow-up right now.

Make.com calls this endpoint on a cron (every 30 min).
For each lead returned, Make sends a WhatsApp follow-up message.

Logic:
- For each agent with appointment_followup_enabled=true, check timing:
    - "1_day"   → appointment_at is between 23h and 25h from now
    - "2_hours" → appointment_at is between 1h50m and 2h10m from now
    - "1_hour"  → appointment_at is between 50m and 70m from now
- Returns leads that match, with phone + name + appointment_at + agent info
"""

import os
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_FOLLOWUP_SECRET = os.getenv("FOLLOWUP_SECRET", "")

_TIMING_WINDOWS = {
    "1_day":   (timedelta(hours=23), timedelta(hours=25)),
    "2_hours": (timedelta(hours=1, minutes=50), timedelta(hours=2, minutes=10)),
    "1_hour":  (timedelta(minutes=50), timedelta(minutes=70)),
}


@router.get("/followup/due")
async def get_due_followups(x_followup_secret: str = Header(default="")):
    if _FOLLOWUP_SECRET and x_followup_secret != _FOLLOWUP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    headers = {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch all agents with followup enabled
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/agents_config",
            params={
                "appointment_followup_enabled": "eq.true",
                "select": "id,client_id,agent_name,appointment_followup_timing,whatsapp_number",
            },
            headers=headers,
        )
        r.raise_for_status()
        agents = r.json()

    if not agents:
        return {"due": []}

    now = datetime.now(timezone.utc)
    due = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for agent in agents:
            timing = agent.get("appointment_followup_timing") or "1_day"
            window = _TIMING_WINDOWS.get(timing)
            if not window:
                continue

            window_start = (now + window[0]).isoformat()
            window_end = (now + window[1]).isoformat()

            r = await client.get(
                f"{_SUPABASE_URL}/rest/v1/leads",
                params={
                    "client_id": f"eq.{agent['client_id']}",
                    "appointment_at": f"gte.{window_start}",
                    "select": "id,name,phone,appointment_at,notes",
                },
                headers=headers,
            )
            r.raise_for_status()
            leads = r.json()

            # Filter upper bound (Supabase REST doesn't support AND on same field easily)
            for lead in leads:
                appt = lead.get("appointment_at")
                if not appt:
                    continue
                appt_dt = datetime.fromisoformat(appt.replace("Z", "+00:00"))
                if now + window[0] <= appt_dt <= now + window[1]:
                    due.append({
                        "lead_id":        lead["id"],
                        "name":           lead.get("name") or "",
                        "phone":          lead["phone"],
                        "appointment_at": appt,
                        "notes":          lead.get("notes") or "",
                        "agent_name":     agent["agent_name"],
                        "whatsapp_from":  agent.get("whatsapp_number") or "",
                    })

    return {"due": due, "checked_at": now.isoformat()}

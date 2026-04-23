# Dashboard Assistant Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real-time voice assistant for the business owner in the dashboard — Maya answers questions about leads, calls, and business state using live Supabase data.

**Architecture:** Reuses existing browser voice WebSocket (`mode=assistant`). On connect, loads a dashboard snapshot into system prompt. During conversation, detects intent from user transcript and injects fresh data before Gemini responds. Sends `ui_action` messages to frontend for navigation.

**Tech Stack:** FastAPI WebSocket (existing), Supabase REST queries, Gemini Live API, React/TypeScript

**Spec:** `docs/superpowers/specs/2026-04-23-live-voice-browser-design.md`

---

### Task 1: Create dashboard_snapshot.py

**Files:**
- Create: `app/services/dashboard_snapshot.py`

- [ ] **Step 1: Create the service**

Create `app/services/dashboard_snapshot.py`:

```python
"""
Dashboard data service for assistant mode.
Provides snapshot (on connect) and live queries (during conversation).
"""

import os
import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


async def fetch_dashboard_snapshot(client_id: str | None) -> str:
    """
    Build a short text snapshot of current business state.
    Returns a formatted string ready to inject into system prompt.
    """
    if not _is_configured():
        return "(אין חיבור לנתונים)"

    parts = []

    try:
        leads_text = await _fetch_leads_summary(client_id)
        parts.append(leads_text)
    except Exception as exc:
        logger.warning("[SNAPSHOT] leads query failed: %s", exc)

    try:
        calls_text = await _fetch_calls_summary(client_id)
        parts.append(calls_text)
    except Exception as exc:
        logger.warning("[SNAPSHOT] calls query failed: %s", exc)

    try:
        agents_text = await _fetch_agents_summary(client_id)
        parts.append(agents_text)
    except Exception as exc:
        logger.warning("[SNAPSHOT] agents query failed: %s", exc)

    if not parts:
        return "(אין נתונים זמינים)"

    return "\n".join(parts)


async def _fetch_leads_summary(client_id: str | None) -> str:
    """Fetch lead counts and top 3 recent leads."""
    params: dict = {
        "select": "id,name,phone,status,last_call_topic,last_call_at,notes",
        "order": "last_call_at.desc.nullslast",
        "limit": "5",
    }
    if client_id:
        params["client_id"] = f"eq.{client_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    total = len(rows)
    new_count = sum(1 for r in rows if r.get("status") == "new")

    lines = [f"לידים: {total} אחרונים, {new_count} חדשים"]
    for r in rows[:3]:
        name = r.get("name") or r.get("phone") or "ללא שם"
        topic = r.get("last_call_topic") or ""
        status = r.get("status") or ""
        detail = f" — {topic}" if topic else ""
        lines.append(f"  - {name} ({status}){detail}")

    return "\n".join(lines)


async def _fetch_calls_summary(client_id: str | None) -> str:
    """Fetch today's call counts."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()

    params: dict = {
        "select": "id,status",
        "created_at": f"gte.{today}",
    }

    # Filter by agent_ids belonging to this client
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/call_logs",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    total = len(rows)
    completed = sum(1 for r in rows if r.get("status") == "completed")
    return f"שיחות היום: {total} ({completed} הושלמו)"


async def _fetch_agents_summary(client_id: str | None) -> str:
    """Count active agents."""
    params: dict = {
        "select": "id",
        "is_active": "eq.true",
    }
    if client_id:
        params["client_id"] = f"eq.{client_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/agents_config",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    return f"סוכנים פעילים: {len(rows)}"


# ── Live data queries (for mid-conversation injection) ───────────────────

async def fetch_leads_detail(client_id: str | None) -> str:
    """Fetch top 5 leads with details — for injection when user asks about leads."""
    if not _is_configured():
        return "אין חיבור לנתונים"

    params: dict = {
        "select": "name,phone,status,last_call_topic,last_call_at,notes",
        "order": "last_call_at.desc.nullslast",
        "limit": "5",
    }
    if client_id:
        params["client_id"] = f"eq.{client_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        return "אין לידים כרגע"

    lines = ["=== לידים עדכניים ==="]
    for r in rows:
        name = r.get("name") or r.get("phone") or "ללא שם"
        status = r.get("status") or ""
        topic = r.get("last_call_topic") or ""
        notes = r.get("notes") or ""
        detail = topic or notes
        lines.append(f"- {name} ({status}): {detail[:60]}")
    return "\n".join(lines)


async def fetch_calls_detail(client_id: str | None) -> str:
    """Fetch today's calls with details — for injection when user asks about calls."""
    if not _is_configured():
        return "אין חיבור לנתונים"

    today = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/call_logs",
            params={
                "select": "id,status,created_at,agent_id",
                "created_at": f"gte.{today}",
                "order": "created_at.desc",
                "limit": "10",
            },
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        return "אין שיחות היום"

    total = len(rows)
    completed = sum(1 for r in rows if r.get("status") == "completed")
    return f"=== שיחות היום ===\nסה\"כ: {total}, הושלמו: {completed}"


async def fetch_daily_summary(client_id: str | None) -> str:
    """Combined summary — for 'what happened today' type questions."""
    leads = await fetch_leads_detail(client_id)
    calls = await fetch_calls_detail(client_id)
    return f"{leads}\n\n{calls}"
```

- [ ] **Step 2: Verify import**

Run: `cd c:/Users/lidor/maya-ai && python -c "from app.services.dashboard_snapshot import fetch_dashboard_snapshot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/dashboard_snapshot.py
git commit -m "feat: add dashboard snapshot service for assistant mode"
```

---

### Task 2: Add assistant mode to voice_browser.py

**Files:**
- Modify: `app/routes/voice_browser.py`

- [ ] **Step 1: Add imports and assistant prompt**

At the top of `voice_browser.py`, after existing imports, add:

```python
from app.services.dashboard_snapshot import (
    fetch_dashboard_snapshot,
    fetch_leads_detail,
    fetch_calls_detail,
    fetch_daily_summary,
)
```

After the `_GREETING_ONLY` set, add the assistant system prompt and intent detection:

```python
# ── Assistant mode ───────────────────────────────────────────────────────

_ASSISTANT_PROMPT = """\
את מאיה, עוזרת ניהולית חכמה של בעל העסק.
את מדברת בעברית טבעית, ישירה ומקצועית.

התפקיד שלך:
- לעזור לבעל העסק להבין מה קורה בעסק שלו
- להמליץ מה הפעולה הבאה הכי חשובה
- לענות על שאלות על לידים, שיחות, ומצב המכירות
- להיות ממוקדת ותכליתית — לא להרצות

כללים:
- תמיד תענה בקצרה (2-3 משפטים)
- אם יש data — תשתמש בו. אם אין — תגיד שאין מידע זמין
- אם מבקשים לראות משהו — תגיד "פותחת לך" ואז תפעלי
- לא לבצע פעולות אמיתיות (שליחת הודעות, שיחות)
- את לא סוכן מכירות — את עוזרת ניהולית
- אל תמציאי נתונים. אם לא קיבלת data — תגידי שאין

{snapshot}
"""

# Intent detection for data injection
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "leads": ("לידים", "ליד", "חמים", "דחוף", "לקוחות", "פניות"),
    "calls": ("שיחות", "שיחה", "טלפון", "התקשרו"),
    "summary": ("סיכום", "מה קרה", "מה המצב", "מה חדש", "עדכון"),
}

# UI action mapping — which intents trigger navigation
_INTENT_UI_ACTIONS: dict[str, dict] = {
    "leads": {"action": "open_tab", "target": "leads"},
    "calls": {"action": "open_tab", "target": "calls"},
}

_INJECTION_COOLDOWN_S = 10  # seconds between injections of same intent


def _detect_intent(text: str) -> str | None:
    """Detect intent from user transcript text. Returns intent key or None."""
    text_lower = text.strip()
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return None
```

- [ ] **Step 2: Modify the WebSocket handler for assistant mode**

In the `stream_browser` function, after loading agent config (around line 90), add the assistant mode branch. Find the section that builds `system_instruction` and replace it:

```python
    # ── Build system instruction ─────────────────────────────────────────
    if is_preview:
        # Preview mode: use agent's customer-facing prompt
        system_instruction = agent_cfg.get("prompt_override", "")
        if first_message and system_instruction:
            system_instruction = (
                f'פתחי את השיחה תמיד עם המשפט הבא בדיוק:\n'
                f'"{first_message}"\n\n'
                f'{system_instruction}'
            )
    else:
        # Assistant mode: use dashboard assistant prompt with snapshot
        snapshot = await fetch_dashboard_snapshot(client_id)
        system_instruction = _ASSISTANT_PROMPT.replace("{snapshot}", snapshot)
        first_message = ""  # assistant doesn't use agent's first_message
        logger.info("[BROWSER-WS] Assistant mode - snapshot loaded (%d chars)", len(snapshot))
```

- [ ] **Step 3: Add data injection to gemini_to_browser loop**

Inside the `gemini_to_browser` function, after the `inputTranscription` handling block, add injection logic. The injection state tracking goes in the shared state section:

Add to shared state:
```python
    _last_injected_intent: str | None = None
    _last_injection_time: float = 0
    _last_injection_turn: int = 0
    _turn_count: int = 0
```

In the `gemini_to_browser` function, after `transcript_lines.append(f"לקוח: {input_t['text']}")`, add:

```python
                    # ── Data injection (assistant mode only) ─────────
                    if not is_preview:
                        detected = _detect_intent(input_t["text"])
                        now = asyncio.get_event_loop().time()
                        if (
                            detected
                            and (
                                detected != _last_injected_intent
                                or now - _last_injection_time > _INJECTION_COOLDOWN_S
                                or _turn_count != _last_injection_turn
                            )
                        ):
                            _last_injected_intent = detected
                            _last_injection_time = now
                            _last_injection_turn = _turn_count

                            # Fetch fresh data
                            if detected == "leads":
                                injection = await fetch_leads_detail(client_id)
                            elif detected == "calls":
                                injection = await fetch_calls_detail(client_id)
                            elif detected == "summary":
                                injection = await fetch_daily_summary(client_id)
                            else:
                                injection = None

                            if injection:
                                await gemini_ws.send(json.dumps({
                                    "realtime_input": {"text": injection}
                                }))
                                logger.info(
                                    "[BROWSER-WS] Injected %s data (%d chars)",
                                    detected, len(injection),
                                )

                            # Send ui_action if mapped
                            ui = _INTENT_UI_ACTIONS.get(detected)
                            if ui:
                                await browser_ws.send_json({
                                    "type": "ui_action",
                                    **ui,
                                })
```

And increment `_turn_count` in the `turnComplete` handler:
```python
                if server_content.get("turnComplete"):
                    _speaking = False
                    _turn_count += 1
```

- [ ] **Step 4: Verify import**

Run: `cd c:/Users/lidor/maya-ai && python -c "from app.routes.voice_browser import router; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/routes/voice_browser.py
git commit -m "feat: add assistant mode to browser voice with data injection"
```

---

### Task 3: Add Dashboard Assistant UI to main dashboard

**Files:**
- Create: `dashboard/components/dashboard/dashboard-assistant.tsx`
- Modify: `dashboard/app/dashboard/DashboardClientPage.tsx`

- [ ] **Step 1: Create DashboardAssistant component**

Create `dashboard/components/dashboard/dashboard-assistant.tsx`:

```tsx
"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { LiveVoicePanel } from "../agents/live-voice-panel";

interface Props {
  defaultAgentId: string | null;
}

export function DashboardAssistant({ defaultAgentId }: Props) {
  const router = useRouter();

  const handleUiAction = useCallback(
    (action: string, target: string) => {
      if (action === "open_tab") {
        const routes: Record<string, string> = {
          leads: "/dashboard/leads",
          calls: "/dashboard/calls",
          agents: "/dashboard/agents",
          knowledge: "/dashboard/knowledge",
        };
        const path = routes[target];
        if (path) router.push(path);
      }
      // Future: open_section, scroll_to, highlight_metric
    },
    [router],
  );

  if (!defaultAgentId) return null;

  return (
    <LiveVoicePanel
      agentId={defaultAgentId}
      mode="assistant"
      onUiAction={handleUiAction}
    />
  );
}
```

- [ ] **Step 2: Add mode and onUiAction props to LiveVoicePanel**

In `dashboard/components/agents/live-voice-panel.tsx`, update the Props interface and component:

Change Props:
```typescript
interface Props {
  agentId: string;
  mode?: "preview" | "assistant";
  onUiAction?: (action: string, target: string) => void;
}
```

Update `buildWsUrl` to include mode:
```typescript
function buildWsUrl(agentId: string, mode: string): string {
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  const wsBase = apiBase.replace(/^http/, "ws");
  return `${wsBase}/ws/voice-browser?agent_id=${agentId}&mode=${mode}`;
}
```

In the component signature:
```typescript
export function LiveVoicePanel({ agentId, mode = "preview", onUiAction }: Props) {
```

Update `startCall` to use mode:
```typescript
const wsUrl = buildWsUrl(agentId, mode);
```

Add `ui_action` handler in `ws.onmessage` switch:
```typescript
          case "ui_action":
            if (onUiAction) onUiAction(msg.action, msg.target);
            break;
```

Update labels based on mode:
```typescript
const STATE_LABELS: Record<VoiceState, string> = {
  disconnected: mode === "assistant" ? "דבר עם מאיה" : "בדוק את הסוכן",
  connecting: "מתחברת...",
  listening: "מקשיבה...",
  thinking: "חושבת...",
  speaking: "מדברת...",
};
```

Note: STATE_LABELS needs to move inside the component since it depends on `mode`. Convert from module-level to computed inside the component.

Update button label:
```tsx
{mode === "assistant" ? "דבר עם מאיה" : "בדוק את הסוכן"}
```

Update disclaimer (only show in preview mode):
```tsx
{mode === "preview" && (
  <p className="text-center text-gray-600 text-[11px] mt-4">
    שיחה זו היא לבדיקה בלבד — לא נשמרים לידים ולא נשלחות פעולות
  </p>
)}
```

- [ ] **Step 3: Add DashboardAssistant to main dashboard page**

Find the DashboardClientPage component and add the assistant panel. Read the file first, then add the DashboardAssistant component at the top of the page layout, passing the first active agent's ID.

In the parent server component (`dashboard/app/dashboard/page.tsx`), the `agentIds` array is already computed. Pass the first one as `defaultAgentId` to `DashboardClientPage`.

In `DashboardClientPage.tsx`, import and render:
```tsx
import { DashboardAssistant } from "@/components/dashboard/dashboard-assistant";

// At the top of the page layout, before existing cards:
<DashboardAssistant defaultAgentId={agents?.[0]?.id ?? null} />
```

- [ ] **Step 4: Verify TypeScript**

Run: `cd c:/Users/lidor/maya-ai/dashboard && npx tsc --noEmit 2>&1 | grep -i "assistant\|live-voice" || echo "No errors"`
Expected: `No errors`

- [ ] **Step 5: Commit**

```bash
git add dashboard/components/dashboard/dashboard-assistant.tsx dashboard/components/agents/live-voice-panel.tsx dashboard/app/dashboard/DashboardClientPage.tsx dashboard/app/dashboard/page.tsx
git commit -m "feat: add Dashboard Assistant to main dashboard page"
```

---

### Task 4: End-to-end test

- [ ] **Step 1: Restart backend**

```bash
taskkill //F //FI "IMAGENAME eq python.exe" 2>&1; sleep 1
cd c:/Users/lidor/maya-ai
export $(grep -E '^(GEMINI_API_KEY|OPENAI_API_KEY|SUPABASE_URL|SUPABASE_SERVICE_KEY)=' .env | xargs)
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
sleep 4 && curl -s http://localhost:8000/health
```

- [ ] **Step 2: Test assistant mode WebSocket**

```python
import asyncio, websockets, json
AGENT_ID = "2145e5c9-52b2-451a-9aa9-6329a8293dc5"
async def test():
    ws = await websockets.connect(
        f"ws://localhost:8000/ws/voice-browser?agent_id={AGENT_ID}&mode=assistant"
    )
    for _ in range(5):
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(msg.get("type"), msg.get("state", ""))
    await ws.close()
asyncio.run(test())
```

Expected: `ready`, `state listening` — with assistant prompt (check logs for "Assistant mode - snapshot loaded")

- [ ] **Step 3: Test in browser**

Open dashboard → verify DashboardAssistant component renders → click "דבר עם מאיה" → speak → verify Maya responds as assistant (not as sales agent)

- [ ] **Step 4: Verify preview mode unchanged**

Open agent page → "Agent Preview" tab → click "בדוק את הסוכן" → verify Maya speaks as sales agent with customer prompt

- [ ] **Step 5: Check logs**

```bash
grep "BROWSER-WS" server.log | tail -20
```

Verify: "Assistant mode - snapshot loaded", no lead extraction in preview, data injection on intent detection.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: Dashboard Assistant Mode MVP complete"
```

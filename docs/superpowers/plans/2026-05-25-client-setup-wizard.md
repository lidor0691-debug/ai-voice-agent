# Client Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hidden admin route `/admin/client-setup` with a 6-step wizard that creates and configures a Maya agent for a business end-to-end, using existing Supabase tables and API routes.

**Architecture:** A server-component page gates on `isAdmin` and renders one client-component wizard. The wizard holds all state locally, reuses UI primitives extracted from `agent-form.tsx`, generates a clean `system_prompt` via a pure helper, and orchestrates the existing `/api/agents`, `/api/knowledge`, and `/api/clients/{id}/assets` routes. Draft saves persist only the client+agent; knowledge/assets are written only on Publish.

**Tech Stack:** Next.js 16 (App Router), React 18, TypeScript, Tailwind (`surface-*`/`brand-*` tokens), `lucide-react`, Supabase via existing API routes. No new dependencies, no test framework added.

---

## Testing approach (read first)

The dashboard has **no unit-test runner** (`package.json` scripts = `dev`/`build`/`lint` only) and no existing JS tests. To keep this change small and reviewable, this plan does **not** add a test framework. Verification is:

- **Automated:** `npm run build` (Next.js type-checks the whole app) and `npm run lint`.
- **Pure-function confidence:** an optional, dependency-free run of the prompt generator via `npx tsx` (no devDependency added).
- **Behavioral:** the manual walkthrough in the final **Validation Checklist** (no production DB writes during implementation — the user performs live testing).

All commands run from `C:\Users\lidor\maya-ai\dashboard`.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `components/agents/form-primitives.tsx` | Create | Shared `Field`, `Input`, `Textarea`, `Select`, `StepIndicator` (presentational) |
| `components/agents/agent-form.tsx` | Modify | Replace local primitive defs with imports (behavior-preserving) |
| `types/database.ts` | Modify | Add optional `status?` to `AgentConfig` |
| `lib/generate-system-prompt.ts` | Create | Pure fn: wizard inputs → prompt string |
| `lib/client-setup-i18n.ts` | Create | Wizard strings (he/en) — self-contained, avoids editing global dict |
| `components/admin/client-setup-wizard.tsx` | Create | The 6-step stateful wizard + draft/publish orchestration |
| `app/admin/client-setup/page.tsx` | Create | Server gate (`isAdmin`) + render wizard |

> i18n note: rather than editing the shared `lib/i18n.ts` dictionary (larger blast radius), wizard copy lives in a small self-contained `client-setup-i18n.ts` keyed by the current language from `useLanguage()`. This keeps the change isolated and reviewable.

---

## Task 1: Extract shared form primitives

**Files:**
- Create: `components/agents/form-primitives.tsx`
- Modify: `components/agents/agent-form.tsx` (remove local defs, add import)

- [ ] **Step 1: Create the primitives file**

Move the five primitives verbatim out of `agent-form.tsx` into a new file. Exact content:

```tsx
// components/agents/form-primitives.tsx
import { CheckCircle } from "lucide-react";

export function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-200 mb-1.5">
        {required && <span className="text-brand-400 ml-1">*</span>}
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{hint}</p>}
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors"
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors resize-none"
    />
  );
}

export function Select({
  options,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: { value: string; label: string }[];
}) {
  return (
    <select
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-surface-3">
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function StepIndicator({
  currentStep,
  steps,
}: {
  currentStep: number;
  steps: { number: number; label: string }[];
}) {
  return (
    <div className="flex items-start justify-center gap-1 mb-8">
      {steps.map((step, idx) => {
        const done = step.number < currentStep;
        const active = step.number === currentStep;
        return (
          <div key={step.number} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5 w-20">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                  done
                    ? "bg-emerald-500 text-white"
                    : active
                    ? "bg-brand-600 text-white ring-2 ring-brand-400/30"
                    : "bg-surface-3 text-gray-500 border border-border"
                }`}
              >
                {done ? <CheckCircle className="w-4 h-4" /> : step.number}
              </div>
              <span
                className={`text-xs text-center leading-tight ${
                  active ? "text-white font-medium" : "text-gray-600"
                }`}
              >
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={`h-px w-6 mb-5 ${
                  step.number < currentStep ? "bg-emerald-500" : "bg-border"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Update `agent-form.tsx` to import the primitives**

In `components/agents/agent-form.tsx`:
1. Delete the local `function Field(...)`, `function Input(...)`, `function Textarea(...)`, `function Select(...)`, and `function StepIndicator(...)` definitions (lines ~33–142).
2. Add at the top of the imports:

```tsx
import { Field, Input, Textarea, Select, StepIndicator } from "@/components/agents/form-primitives";
```

3. The existing `import { CheckCircle, ChevronRight, ChevronLeft } from "lucide-react";` stays (CheckCircle is still used in the activation/summary JSX). No other change.

- [ ] **Step 3: Verify build + lint (behavior-preserving)**

Run: `npm run build`
Expected: build succeeds, no type errors. The `/dashboard/agents/new` form renders identically (primitives unchanged, just relocated).

Run: `npm run lint`
Expected: no new lint errors.

- [ ] **Step 4: Commit**

```bash
git add components/agents/form-primitives.tsx components/agents/agent-form.tsx
git commit -m "refactor: extract shared form primitives from agent-form"
```

---

## Task 2: Add tolerant `status` typing

**Files:**
- Modify: `types/database.ts` (`AgentConfig` interface)

- [ ] **Step 1: Add optional status to `AgentConfig`**

In `types/database.ts`, inside `export interface AgentConfig { ... }`, add (near `is_active`):

```tsx
  // Onboarding lifecycle. Optional: column may not exist yet (see migration in spec).
  // When the column is absent, treat `live` as `is_active === true`.
  status?: 'draft' | 'ready_for_test' | 'live';
```

- [ ] **Step 2: Verify type-check**

Run: `npm run build`
Expected: success. `status` is optional, so no existing code breaks.

- [ ] **Step 3: Commit**

```bash
git add types/database.ts
git commit -m "feat: add optional status field to AgentConfig type"
```

---

## Task 3: Prompt generator (pure function)

**Files:**
- Create: `lib/generate-system-prompt.ts`

- [ ] **Step 1: Write the generator**

```tsx
// lib/generate-system-prompt.ts

export interface PromptInputs {
  agentName: string;
  businessName?: string;
  language?: string;     // "he" | "en" | ...
  tone?: string;         // "friendly" | "professional" | ...
  services?: { name: string; detail?: string }[];
  pricing?: { name: string; detail?: string }[];
  handoffRules?: string[];      // e.g. ["transfer to human if angry"]
  transferNumber?: string;
  behaviorNotes?: string;       // free text from Step 4
}

const LANG_LABEL: Record<string, string> = {
  he: "Hebrew",
  en: "English",
  es: "Spanish",
  fr: "French",
  de: "German",
};

/**
 * Builds a clean system prompt from wizard inputs. Mirrors the SECTION STRUCTURE of the
 * backend build_supabase_system_prompt() (role / language / tone / services / handoff),
 * but does NOT inline knowledge items — the backend appends those at call time.
 */
export function generateSystemPrompt(input: PromptInputs): string {
  const lang = LANG_LABEL[input.language ?? "he"] ?? input.language ?? "Hebrew";
  const tone = input.tone?.trim() || "friendly";
  const lines: string[] = [];

  lines.push(
    `You are ${input.agentName}, an AI assistant${
      input.businessName ? ` for ${input.businessName}` : ""
    }.`
  );
  lines.push(`Language: ${lang}. Tone: ${tone}.`);
  lines.push("");
  lines.push("━━ ROLE ━━");
  lines.push(
    "You are a helpful, concise conversation partner. Answer questions, qualify the lead, " +
      "and move the conversation toward the business goal. Do not invent facts you were not given."
  );

  if (input.services && input.services.length > 0) {
    lines.push("");
    lines.push("━━ SERVICES ━━");
    for (const s of input.services) {
      lines.push(`- ${s.name}${s.detail ? `: ${s.detail}` : ""}`);
    }
  }

  if (input.pricing && input.pricing.length > 0) {
    lines.push("");
    lines.push("━━ PRICING ━━");
    for (const p of input.pricing) {
      lines.push(`- ${p.name}${p.detail ? `: ${p.detail}` : ""}`);
    }
  }

  if (input.handoffRules && input.handoffRules.length > 0) {
    lines.push("");
    lines.push("━━ HANDOFF RULES ━━");
    for (const r of input.handoffRules) lines.push(`- ${r}`);
    if (input.transferNumber) {
      lines.push(`When handing off, transfer to: ${input.transferNumber}`);
    }
  }

  if (input.behaviorNotes && input.behaviorNotes.trim()) {
    lines.push("");
    lines.push("━━ ADDITIONAL NOTES ━━");
    lines.push(input.behaviorNotes.trim());
  }

  return lines.join("\n");
}
```

- [ ] **Step 2: Optional confidence check (no devDependency added)**

Create a throwaway file `scripts/_check-prompt.mts` (delete after, do not commit):

```tsx
import { generateSystemPrompt } from "../lib/generate-system-prompt";
import assert from "node:assert";

const out = generateSystemPrompt({
  agentName: "Maya",
  businessName: "Acme Motors",
  language: "he",
  tone: "professional",
  services: [{ name: "Test rides", detail: "book online" }],
  pricing: [{ name: "New bike", detail: "from 30,000" }],
  handoffRules: ["transfer if caller asks for a manager"],
  transferNumber: "+972543033010",
  behaviorNotes: "Always confirm the caller's phone before ending.",
});

assert(out.includes("You are Maya, an AI assistant for Acme Motors."));
assert(out.includes("Language: Hebrew. Tone: professional."));
assert(out.includes("━━ SERVICES ━━"));
assert(out.includes("- Test rides: book online"));
assert(out.includes("━━ PRICING ━━"));
assert(out.includes("━━ HANDOFF RULES ━━"));
assert(out.includes("transfer to: +972543033010"));
assert(out.includes("Always confirm the caller's phone"));
console.log("OK\n---\n" + out);
```

Run: `npx tsx scripts/_check-prompt.mts`
Expected: prints `OK` then the prompt. Then delete the file: `Remove-Item scripts/_check-prompt.mts`

> If `npx tsx` is unavailable offline, skip this step — `npm run build` still type-checks the function and the wizard exercises it at runtime.

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add lib/generate-system-prompt.ts
git commit -m "feat: add system prompt generator for client setup wizard"
```

---

## Task 4: Wizard i18n strings

**Files:**
- Create: `lib/client-setup-i18n.ts`

- [ ] **Step 1: Write the strings module**

```tsx
// lib/client-setup-i18n.ts
export type CsLang = "he" | "en";

export interface CsStrings {
  title: string; subtitle: string; cancel: string;
  step_business: string; step_channels: string; step_catalog: string;
  step_behavior: string; step_checklist: string; step_publish: string;
  prev: string; next: string;
  business_name: string; agent_name: string; agent_name_req: string;
  language: string; tone: string;
  channel: string; voice_number: string; whatsapp_enabled: string; whatsapp_number: string;
  lead_method: string; lead_target: string;
  services: string; pricing: string; faqs: string; assets: string;
  faq_q: string; faq_a: string; add: string; remove: string;
  asset_name: string; asset_url: string; asset_type: string;
  handoff_rules: string; transfer_number: string; behavior_notes: string; required_fields: string;
  checklist_intro: string; ck_voice: string; ck_whatsapp: string; ck_followup: string; ck_lead: string;
  checklist_note: string;
  prompt_label: string; prompt_hint: string; regenerate: string;
  status: string; status_draft: string; status_ready: string; status_live: string;
  save_draft: string; publish: string; saving: string; saved: string;
  publish_done: string; save_failed: string; name_required: string; phone_invalid: string;
}

const he: CsStrings = {
  title: "הקמת לקוח חדש", subtitle: "הגדרת סוכן Maya לעסק", cancel: "ביטול",
  step_business: "פרטי העסק", step_channels: "ערוצים", step_catalog: "שירותים ותוכן",
  step_behavior: "התנהגות", step_checklist: "בדיקות", step_publish: "פרסום",
  prev: "הקודם", next: "הבא",
  business_name: "שם העסק", agent_name: "שם הסוכן", agent_name_req: "שם הסוכן הוא שדה חובה",
  language: "שפה", tone: "טון",
  channel: "ערוץ ראשי", voice_number: "מספר טלפון (קולי)", whatsapp_enabled: "הפעלת וואטסאפ", whatsapp_number: "מספר וואטסאפ",
  lead_method: "אופן קבלת פניות", lead_target: "יעד הפניות",
  services: "שירותים", pricing: "מחירים", faqs: "שאלות נפוצות", assets: "קישורים / חוזים / טפסים",
  faq_q: "שאלה", faq_a: "תשובה", add: "הוסף", remove: "הסר",
  asset_name: "שם", asset_url: "קישור / תוכן", asset_type: "סוג",
  handoff_rules: "כללי העברה לנציג", transfer_number: "מספר להעברה", behavior_notes: "הערות התנהגות", required_fields: "שדות חובה לאיסוף",
  checklist_intro: "ודא שכל הערוצים מוכנים לפני הפעלה.", ck_voice: "מספר קולי הוגדר", ck_whatsapp: "מספר וואטסאפ הוגדר", ck_followup: "מעקב וואטסאפ הוגדר", ck_lead: "יעד פניות (CRM) הוגדר",
  checklist_note: "רשימת הבדיקות לתצוגה בלבד ואינה נשמרת.",
  prompt_label: "פקודת מערכת (System Prompt)", prompt_hint: "נוצר אוטומטית — ניתן לערוך. שאלות נפוצות/שירותים מצורפים בנפרד אוטומטית בשיחות.", regenerate: "צור מחדש",
  status: "סטטוס", status_draft: "טיוטה", status_ready: "מוכן לבדיקה", status_live: "פעיל",
  save_draft: "שמור טיוטה", publish: "פרסם סוכן", saving: "שומר…", saved: "נשמר",
  publish_done: "הסוכן פורסם בהצלחה", save_failed: "השמירה נכשלה", name_required: "שם הסוכן הוא שדה חובה", phone_invalid: "מספר טלפון לא תקין",
};

const en: CsStrings = {
  title: "New Client Setup", subtitle: "Configure a Maya agent for a business", cancel: "Cancel",
  step_business: "Business", step_channels: "Channels", step_catalog: "Services & Content",
  step_behavior: "Behavior", step_checklist: "Checklist", step_publish: "Publish",
  prev: "Back", next: "Next",
  business_name: "Business name", agent_name: "Agent name", agent_name_req: "Agent name is required",
  language: "Language", tone: "Tone",
  channel: "Primary channel", voice_number: "Phone number (voice)", whatsapp_enabled: "Enable WhatsApp", whatsapp_number: "WhatsApp number",
  lead_method: "Lead delivery method", lead_target: "Lead delivery target",
  services: "Services", pricing: "Pricing", faqs: "FAQs", assets: "Links / contracts / forms",
  faq_q: "Question", faq_a: "Answer", add: "Add", remove: "Remove",
  asset_name: "Name", asset_url: "Link / content", asset_type: "Type",
  handoff_rules: "Handoff rules", transfer_number: "Transfer number", behavior_notes: "Behavior notes", required_fields: "Required fields to collect",
  checklist_intro: "Confirm channels are ready before going live.", ck_voice: "Voice number set", ck_whatsapp: "WhatsApp number set", ck_followup: "WhatsApp follow-up configured", ck_lead: "Lead delivery (CRM) target set",
  checklist_note: "Checklist is display-only and is not saved.",
  prompt_label: "System prompt", prompt_hint: "Auto-generated — editable. FAQs/services are attached separately and added automatically during calls.", regenerate: "Regenerate",
  status: "Status", status_draft: "Draft", status_ready: "Ready for test", status_live: "Live",
  save_draft: "Save draft", publish: "Publish agent", saving: "Saving…", saved: "Saved",
  publish_done: "Agent published successfully", save_failed: "Save failed", name_required: "Agent name is required", phone_invalid: "Invalid phone number",
};

export function csStrings(lang: string | undefined): CsStrings {
  return lang === "en" ? en : he;
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add lib/client-setup-i18n.ts
git commit -m "feat: add i18n strings for client setup wizard"
```

---

## Task 5: The wizard component

**Files:**
- Create: `components/admin/client-setup-wizard.tsx`

This is the core. It holds all state, renders 6 steps using the shared primitives, and orchestrates Draft/Publish against existing API routes. Knowledge/assets write **only on Publish**. Status writes are **tolerant**.

- [ ] **Step 1: Scaffold — imports, types, state, helpers**

```tsx
// components/admin/client-setup-wizard.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, ChevronRight, ChevronLeft, Plus, Trash2 } from "lucide-react";
import { Field, Input, Textarea, Select, StepIndicator } from "@/components/agents/form-primitives";
import { useLanguage } from "@/context/language-context";
import { csStrings } from "@/lib/client-setup-i18n";
import { generateSystemPrompt } from "@/lib/generate-system-prompt";

function normalizePhone(raw: string): string {
  const t = raw.trim();
  const hasPlus = t.startsWith("+");
  const digits = t.replace(/\D/g, "");
  return hasPlus ? `+${digits}` : digits;
}
function isValidPhone(p: string): boolean {
  return p === "" || /^\+\d{7,15}$/.test(p);
}

interface CatalogItem { name: string; detail: string; }   // services / pricing
interface FaqItem { question: string; answer: string; }
interface AssetItem { name: string; type: "link" | "pdf"; content: string; }

interface WizardState {
  // Step 1
  business_name: string;
  agent_name: string;
  language: string;
  tone: string;
  // Step 2
  channel: "voice" | "whatsapp";
  phone_number: string;
  whatsapp_enabled: boolean;
  whatsapp_number: string;
  lead_delivery_method: string;
  lead_delivery_target: string;
  // Step 3
  services: CatalogItem[];
  pricing: CatalogItem[];
  faqs: FaqItem[];
  assets: AssetItem[];
  // Step 4
  transfer_number: string;
  handoff_rules: string;     // newline-separated -> whatsapp_rules
  required_fields: string;   // newline-separated -> whatsapp_required_fields
  behavior_notes: string;
  // Step 6
  system_prompt: string;
  status: "draft" | "ready_for_test" | "live";
}

const initialState: WizardState = {
  business_name: "", agent_name: "", language: "he", tone: "friendly",
  channel: "voice", phone_number: "", whatsapp_enabled: false, whatsapp_number: "",
  lead_delivery_method: "webhook", lead_delivery_target: "",
  services: [], pricing: [], faqs: [], assets: [],
  transfer_number: "", handoff_rules: "", required_fields: "", behavior_notes: "",
  system_prompt: "", status: "draft",
};

export function ClientSetupWizard() {
  const router = useRouter();
  const { language } = useLanguage();      // existing context exposes current language code
  const t = csStrings(language);

  const [step, setStep] = useState(1);
  const [form, setForm] = useState<WizardState>(initialState);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const set = <K extends keyof WizardState>(k: K, v: WizardState[K]) =>
    setForm((p) => ({ ...p, [k]: v }));

  const steps = [
    { number: 1, label: t.step_business },
    { number: 2, label: t.step_channels },
    { number: 3, label: t.step_catalog },
    { number: 4, label: t.step_behavior },
    { number: 5, label: t.step_checklist },
    { number: 6, label: t.step_publish },
  ];
  // ... continues in Step 2 of this task
```

> `useLanguage()`: confirm it exposes `language` (the code string). If it only exposes `t`, read the current code from `t` or fall back: `const { language } = useLanguage() as { language?: string }`. The wizard only needs the language code to pick he/en.

- [ ] **Step 2: Add the prompt builder, payload builder, and orchestration**

Append inside the component, before `return`:

```tsx
  function buildPromptInputs() {
    return {
      agentName: form.agent_name || "Maya",
      businessName: form.business_name || undefined,
      language: form.language,
      tone: form.tone,
      services: form.services.filter((s) => s.name.trim()).map((s) => ({ name: s.name, detail: s.detail })),
      pricing: form.pricing.filter((p) => p.name.trim()).map((p) => ({ name: p.name, detail: p.detail })),
      handoffRules: form.handoff_rules.split("\n").map((r) => r.trim()).filter(Boolean),
      transferNumber: form.transfer_number || undefined,
      behaviorNotes: form.behavior_notes || undefined,
    };
  }

  function regeneratePrompt() {
    set("system_prompt", generateSystemPrompt(buildPromptInputs()));
  }

  // Builds the agents_config body. Includes `status` ONLY when caller asks (tolerant path
  // handled by saveAgent fallback). `is_active` is always the source of truth.
  function agentBody(opts: { live: boolean; withStatus: boolean }) {
    const requiredFields = form.required_fields.split("\n").map((s) => s.trim()).filter(Boolean);
    const rules = form.handoff_rules.split("\n").map((s) => s.trim()).filter(Boolean);
    const body: Record<string, unknown> = {
      business_name: form.business_name || null,
      agent_name: form.agent_name,
      language: form.language,
      tone: form.tone,
      channel: form.channel,
      phone_number: normalizePhone(form.phone_number),
      whatsapp_enabled: form.whatsapp_enabled,
      whatsapp_number: form.whatsapp_number ? normalizePhone(form.whatsapp_number) : "",
      lead_delivery_method: form.lead_delivery_method,
      lead_delivery_target: form.lead_delivery_target,
      transfer_number: form.transfer_number ? normalizePhone(form.transfer_number) : "",
      whatsapp_required_fields: requiredFields.length ? requiredFields : null,
      whatsapp_rules: rules.length ? rules : null,
      system_prompt: form.system_prompt || null,
      is_active: opts.live,
    };
    if (opts.withStatus) body.status = opts.live ? "live" : form.status;
    return body;
  }

  // Creates (POST) or updates (PATCH) the agent. Tolerant of a missing `status` column:
  // first attempt includes status; on a status-related failure, retry without it.
  async function saveAgent(opts: { live: boolean }): Promise<{ id: string; client_id: string } | null> {
    const attempt = async (withStatus: boolean) => {
      const url = agentId ? `/api/agents/${agentId}` : "/api/agents";
      const method = agentId ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(agentBody({ live: opts.live, withStatus })),
      });
      return res;
    };

    let res = await attempt(true);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      // If the failure mentions the status column, retry without it (column not migrated yet).
      if (typeof data.error === "string" && /status/i.test(data.error)) {
        res = await attempt(false);
      } else {
        throw new Error(data.error ?? t.save_failed);
      }
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error ?? t.save_failed);
    }
    const saved = await res.json();
    if (!agentId) setAgentId(saved.id);
    if (!clientId && saved.client_id) setClientId(saved.client_id);
    return { id: saved.id, client_id: saved.client_id };
  }

  // Writes Step-3 content. Called ONLY on Publish.
  async function writeCatalog(aId: string, cId: string | null) {
    const kn = [
      ...form.services.filter((s) => s.name.trim()).map((s) => ({ category: "service", title: s.name, content: s.detail || s.name })),
      ...form.pricing.filter((p) => p.name.trim()).map((p) => ({ category: "pricing", title: p.name, content: p.detail || p.name })),
      ...form.faqs.filter((f) => f.question.trim()).map((f) => ({ category: "faq", title: f.question, content: f.answer })),
    ];
    for (const item of kn) {
      const res = await fetch("/api/knowledge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: aId, is_active: true, priority: 0, ...item }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error ?? t.save_failed);
      }
    }
    if (cId) {
      let order = 0;
      for (const a of form.assets.filter((x) => x.name.trim() && x.content.trim())) {
        const res = await fetch(`/api/clients/${cId}/assets`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            asset_name: a.name, asset_type: a.type, trigger_key: a.name.toLowerCase().replace(/\s+/g, "_"),
            content: a.content, sort_order: order++, enabled: true,
          }),
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.error ?? t.save_failed);
        }
      }
    }
  }

  async function handleSaveDraft() {
    if (!form.agent_name.trim()) { setError(t.name_required); setStep(1); return; }
    if (!isValidPhone(normalizePhone(form.phone_number))) { setError(t.phone_invalid); setStep(2); return; }
    setSaving(true); setError(null); setDone(null);
    try {
      await saveAgent({ live: false });   // draft: client+agent only, NO knowledge/assets
      setDone(t.saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : t.save_failed);
    } finally { setSaving(false); }
  }

  async function handlePublish() {
    if (!form.agent_name.trim()) { setError(t.name_required); setStep(1); return; }
    if (!isValidPhone(normalizePhone(form.phone_number))) { setError(t.phone_invalid); setStep(2); return; }
    setSaving(true); setError(null); setDone(null);
    try {
      const saved = await saveAgent({ live: true });
      if (!saved) throw new Error(t.save_failed);
      await writeCatalog(saved.id, saved.client_id);   // knowledge + assets ONLY here
      setDone(t.publish_done);
      setTimeout(() => { router.push("/dashboard/agents"); router.refresh(); }, 1400);
    } catch (e) {
      setError(e instanceof Error ? e.message : t.save_failed);
    } finally { setSaving(false); }
  }

  const goNext = () => setStep((s) => Math.min(6, s + 1));
  const goBack = () => setStep((s) => Math.max(1, s - 1));
```

> **Status tolerance** is implemented in `saveAgent`: it sends `status` first; if the API returns an error mentioning "status" (e.g. unknown column), it retries without it. `is_active` is always sent, so `live` ⇔ `is_active = true` regardless of the column's existence. Constraint #5 satisfied.

- [ ] **Step 3: Render — header, indicator, error/done banners, navigation**

```tsx
  return (
    <div className="flex-1 overflow-y-auto" dir={language === "en" ? "ltr" : "rtl"}>
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">{t.title}</h1>
          <p className="text-gray-500 text-sm mt-0.5">{t.subtitle}</p>
        </div>
        <button onClick={() => router.back()} className="text-gray-400 hover:text-white text-sm px-4 py-2 rounded-lg border border-border hover:bg-surface-3 transition-colors">
          {t.cancel}
        </button>
      </div>

      <div className="p-8 max-w-2xl mx-auto">
        {done && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 shrink-0" />{done}
          </div>
        )}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-6">{error}</div>
        )}

        <StepIndicator currentStep={step} steps={steps} />

        {/* STEP PANELS — see Steps 4–9 of this task */}

        <div className="flex justify-between mt-8">
          {step > 1 ? (
            <button onClick={goBack} className="flex items-center gap-2 text-gray-400 hover:text-white text-sm px-5 py-2.5 rounded-lg border border-border hover:bg-surface-3 transition-colors">
              <ChevronRight className="w-4 h-4" />{t.prev}
            </button>
          ) : <div />}
          {step < 6 && (
            <button onClick={goNext} className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-6 py-2.5 rounded-lg transition-colors">
              {t.next}<ChevronLeft className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

> Note: the existing form uses `ChevronRight` for "prev" and `ChevronLeft` for "next" because of RTL. Keep that convention.

- [ ] **Step 4: Step 1 panel — Business details**

Insert where `{/* STEP PANELS */}` is:

```tsx
        {step === 1 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label={t.business_name}>
                <Input value={form.business_name} onChange={(e) => set("business_name", e.target.value)} />
              </Field>
              <Field label={t.agent_name} required>
                <Input value={form.agent_name} onChange={(e) => set("agent_name", e.target.value)} />
              </Field>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label={t.language}>
                <Select value={form.language} onChange={(e) => set("language", e.target.value)}
                  options={[{ value: "he", label: "עברית" }, { value: "en", label: "English" }]} />
              </Field>
              <Field label={t.tone}>
                <Select value={form.tone} onChange={(e) => set("tone", e.target.value)}
                  options={[
                    { value: "friendly", label: "Friendly" },
                    { value: "professional", label: "Professional" },
                    { value: "formal", label: "Formal" },
                    { value: "casual", label: "Casual" },
                  ]} />
              </Field>
            </div>
          </div>
        )}
```

- [ ] **Step 5: Step 2 panel — Communication channels**

```tsx
        {step === 2 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <Field label={t.channel}>
              <Select value={form.channel} onChange={(e) => set("channel", e.target.value as WizardState["channel"])}
                options={[{ value: "voice", label: "Voice" }, { value: "whatsapp", label: "WhatsApp" }]} />
            </Field>
            <Field label={t.voice_number} hint="+9725XXXXXXXX">
              <Input value={form.phone_number} onChange={(e) => set("phone_number", normalizePhone(e.target.value))} placeholder="+972543033010" />
            </Field>
            <div className="flex items-center justify-between py-2 border-t border-border/50">
              <p className="text-sm font-medium text-gray-200">{t.whatsapp_enabled}</p>
              <div onClick={() => set("whatsapp_enabled", !form.whatsapp_enabled)}
                className={`relative shrink-0 w-12 h-6 rounded-full cursor-pointer transition-colors ${form.whatsapp_enabled ? "bg-brand-600" : "bg-surface-4"}`}>
                <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${form.whatsapp_enabled ? "translate-x-7" : "translate-x-1"}`} />
              </div>
            </div>
            {form.whatsapp_enabled && (
              <Field label={t.whatsapp_number}>
                <Input value={form.whatsapp_number} onChange={(e) => set("whatsapp_number", normalizePhone(e.target.value))} placeholder="+972543033010" />
              </Field>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label={t.lead_method}>
                <Select value={form.lead_delivery_method} onChange={(e) => set("lead_delivery_method", e.target.value)}
                  options={[{ value: "webhook", label: "Webhook" }, { value: "whatsapp", label: "WhatsApp" }, { value: "email", label: "Email" }]} />
              </Field>
              <Field label={t.lead_target}>
                <Input value={form.lead_delivery_target} onChange={(e) => set("lead_delivery_target", e.target.value)} />
              </Field>
            </div>
          </div>
        )}
```

- [ ] **Step 6: Step 3 panel — Services / Pricing / FAQs / Assets (repeatable editors)**

Add a small generic list helper inside the component (above `return`):

```tsx
  function addItem<K extends "services" | "pricing">(key: K) {
    set(key, [...form[key], { name: "", detail: "" }] as WizardState[K]);
  }
  function addFaq() { set("faqs", [...form.faqs, { question: "", answer: "" }]); }
  function addAsset() { set("assets", [...form.assets, { name: "", type: "link", content: "" }]); }
  function removeAt<K extends "services" | "pricing" | "faqs" | "assets">(key: K, idx: number) {
    set(key, form[key].filter((_, i) => i !== idx) as WizardState[K]);
  }
```

Panel JSX:

```tsx
        {step === 3 && (
          <div className="space-y-4">
            {(["services", "pricing"] as const).map((key) => (
              <div key={key} className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-white font-semibold text-base">{key === "services" ? t.services : t.pricing}</h2>
                  <button onClick={() => addItem(key)} className="flex items-center gap-1 text-brand-400 text-sm hover:text-brand-300">
                    <Plus className="w-4 h-4" />{t.add}
                  </button>
                </div>
                {form[key].map((item, i) => (
                  <div key={i} className="flex gap-2 items-start">
                    <Input placeholder={t.asset_name} value={item.name}
                      onChange={(e) => { const next = [...form[key]]; next[i] = { ...next[i], name: e.target.value }; set(key, next as WizardState[typeof key]); }} />
                    <Input placeholder={t.faq_a} value={item.detail}
                      onChange={(e) => { const next = [...form[key]]; next[i] = { ...next[i], detail: e.target.value }; set(key, next as WizardState[typeof key]); }} />
                    <button onClick={() => removeAt(key, i)} className="text-gray-500 hover:text-red-400 mt-2"><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
              </div>
            ))}

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-white font-semibold text-base">{t.faqs}</h2>
                <button onClick={addFaq} className="flex items-center gap-1 text-brand-400 text-sm hover:text-brand-300"><Plus className="w-4 h-4" />{t.add}</button>
              </div>
              {form.faqs.map((f, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <Input placeholder={t.faq_q} value={f.question}
                    onChange={(e) => { const next = [...form.faqs]; next[i] = { ...next[i], question: e.target.value }; set("faqs", next); }} />
                  <Input placeholder={t.faq_a} value={f.answer}
                    onChange={(e) => { const next = [...form.faqs]; next[i] = { ...next[i], answer: e.target.value }; set("faqs", next); }} />
                  <button onClick={() => removeAt("faqs", i)} className="text-gray-500 hover:text-red-400 mt-2"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-white font-semibold text-base">{t.assets}</h2>
                <button onClick={addAsset} className="flex items-center gap-1 text-brand-400 text-sm hover:text-brand-300"><Plus className="w-4 h-4" />{t.add}</button>
              </div>
              {form.assets.map((a, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <Input placeholder={t.asset_name} value={a.name}
                    onChange={(e) => { const next = [...form.assets]; next[i] = { ...next[i], name: e.target.value }; set("assets", next); }} />
                  <Select value={a.type} onChange={(e) => { const next = [...form.assets]; next[i] = { ...next[i], type: e.target.value as AssetItem["type"] }; set("assets", next); }}
                    options={[{ value: "link", label: "Link" }, { value: "pdf", label: "PDF" }]} />
                  <Input placeholder={t.asset_url} value={a.content}
                    onChange={(e) => { const next = [...form.assets]; next[i] = { ...next[i], content: e.target.value }; set("assets", next); }} />
                  <button onClick={() => removeAt("assets", i)} className="text-gray-500 hover:text-red-400 mt-2"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          </div>
        )}
```

- [ ] **Step 7: Step 4 panel — Behavior & handoff**

```tsx
        {step === 4 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <Field label={t.transfer_number}>
              <Input value={form.transfer_number} onChange={(e) => set("transfer_number", normalizePhone(e.target.value))} placeholder="+972543033010" />
            </Field>
            <Field label={t.handoff_rules} hint="One rule per line">
              <Textarea rows={4} value={form.handoff_rules} onChange={(e) => set("handoff_rules", e.target.value)} />
            </Field>
            <Field label={t.required_fields} hint="One field per line, e.g. name / phone">
              <Textarea rows={3} value={form.required_fields} onChange={(e) => set("required_fields", e.target.value)} />
            </Field>
            <Field label={t.behavior_notes}>
              <Textarea rows={4} value={form.behavior_notes} onChange={(e) => set("behavior_notes", e.target.value)} />
            </Field>
          </div>
        )}
```

- [ ] **Step 8: Step 5 panel — Test checklist (manual + derived hints, UI-only)**

```tsx
        {step === 5 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
            <p className="text-gray-400 text-sm">{t.checklist_intro}</p>
            {[
              { label: t.ck_voice, ready: Boolean(form.phone_number.trim()) },
              { label: t.ck_whatsapp, ready: form.whatsapp_enabled && Boolean(form.whatsapp_number.trim()) },
              { label: t.ck_followup, ready: form.whatsapp_enabled },
              { label: t.ck_lead, ready: Boolean(form.lead_delivery_target.trim()) },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
                <span className="text-sm text-gray-200">{item.label}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${item.ready ? "bg-emerald-500/15 text-emerald-400" : "bg-surface-3 text-gray-500"}`}>
                  {item.ready ? "✓" : "—"}
                </span>
              </div>
            ))}
            <p className="text-xs text-gray-600">{t.checklist_note}</p>
          </div>
        )}
```

> Checklist is purely derived + display. No persistence (constraint #7). If a `metadata`/json column is later confirmed, persistence can be added then.

- [ ] **Step 9: Step 6 panel — Publish (prompt preview + status + buttons)**

```tsx
        {step === 6 && (
          <div className="space-y-4">
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-white font-semibold text-base">{t.prompt_label}</h2>
                <button onClick={regeneratePrompt} className="text-brand-400 text-sm hover:text-brand-300">{t.regenerate}</button>
              </div>
              <p className="text-xs text-gray-500">{t.prompt_hint}</p>
              <Textarea rows={12} value={form.system_prompt} onChange={(e) => set("system_prompt", e.target.value)} />
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6">
              <Field label={t.status}>
                <Select value={form.status} onChange={(e) => set("status", e.target.value as WizardState["status"])}
                  options={[
                    { value: "draft", label: t.status_draft },
                    { value: "ready_for_test", label: t.status_ready },
                    { value: "live", label: t.status_live },
                  ]} />
              </Field>
            </div>

            <div className="flex gap-3">
              <button onClick={handleSaveDraft} disabled={saving}
                className="flex-1 text-gray-200 font-medium py-3.5 rounded-xl border border-border hover:bg-surface-3 disabled:opacity-50 transition-colors">
                {saving ? t.saving : t.save_draft}
              </button>
              <button onClick={handlePublish} disabled={saving}
                className="flex-1 text-white font-semibold py-3.5 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:opacity-50 transition-colors">
                {saving ? t.saving : t.publish}
              </button>
            </div>
          </div>
        )}
```

> On entering Step 6 the prompt textarea may be empty; the admin clicks **Regenerate** (or edits manually). Optionally auto-generate once when reaching step 6 if `system_prompt` is empty — implementer may add `useEffect(() => { if (step === 6 && !form.system_prompt) regeneratePrompt(); }, [step]);` (kept optional to avoid surprising overwrites).

- [ ] **Step 10: Verify build + lint**

Run: `npm run build`
Expected: success, no type errors.
Run: `npm run lint`
Expected: no new errors.

- [ ] **Step 11: Commit**

```bash
git add components/admin/client-setup-wizard.tsx
git commit -m "feat: add client setup wizard component"
```

---

## Task 6: The hidden admin route

**Files:**
- Create: `app/admin/client-setup/page.tsx`

- [ ] **Step 1: Write the server page**

```tsx
// app/admin/client-setup/page.tsx
import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { ClientSetupWizard } from "@/components/admin/client-setup-wizard";

export const dynamic = "force-dynamic";

export default async function ClientSetupPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx?.isAdmin) redirect("/dashboard/agents");
  return <ClientSetupWizard />;
}
```

> Double gate: `middleware.ts` already blocks `/admin/*` for non-admins; this page redirects as a defense-in-depth fallback, mirroring `agents/new/page.tsx`. No tab is added to `admin/layout.tsx` (constraint #3) — the route is reachable only by direct URL.

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: success; route `/admin/client-setup` appears in the build output.

- [ ] **Step 3: Manual smoke (local dev, no prod writes)**

Run: `npm run dev`
Visit `http://localhost:3000/admin/client-setup` as an admin user.
Expected: wizard renders, all 6 steps navigate, no console errors. **Do not click Publish against production data** unless intentionally testing against a disposable project.

- [ ] **Step 4: Commit**

```bash
git add app/admin/client-setup/page.tsx
git commit -m "feat: add hidden /admin/client-setup route"
```

---

## Validation / Test Checklist

Run all from `dashboard/`. No production DB writes during these checks.

- [ ] `npm run build` succeeds (full type-check) after every task.
- [ ] `npm run lint` reports no new errors.
- [ ] `/dashboard/agents/new` still renders and works identically (Task 1 was behavior-preserving).
- [ ] Prompt generator: `npx tsx scripts/_check-prompt.mts` prints `OK` (optional; then delete the file).
- [ ] Wizard renders at `/admin/client-setup` for an admin; a non-admin is redirected.
- [ ] All 6 steps navigate (Next/Back); RTL for he, LTR for en.
- [ ] Step 3 add/remove works for services, pricing, FAQs, assets.
- [ ] **Save Draft** creates client+agent only — confirm (in a disposable/local Supabase) that NO `knowledge_items` or `client_assets` rows are written on draft.
- [ ] **Publish** writes knowledge_items (service/pricing/faq) + client_assets, and sets the agent active.
- [ ] **Status tolerance:** with no `status` column, Save Draft and Publish still succeed (agent saved via `is_active`); with the column present (after migration), `status` is persisted and `live ⇔ is_active=true`.
- [ ] Generated prompt appears in the Publish textarea, is editable, and the edited text is what gets saved to `system_prompt`.
- [ ] Checklist shows derived ✓/— hints and is not persisted.

---

## Do NOT touch

- `app/admin/layout.tsx` — no new tab yet (constraint #3).
- Any migration / Supabase MCP `apply_migration` — migration is spec-only (constraint #2).
- Production Supabase data — no live writes during implementation (constraint #1).
- Voice runtime (`C:\Users\lidor\maya-ai\app/`, `agent/`, `main.py`), `agent_config.py`.
- Public landing page, billing, analytics, other `/dashboard/*` pages.
- `lib/i18n.ts` global dictionary — wizard uses its own `client-setup-i18n.ts`.
- The step *logic* inside `agent-form.tsx` — only the primitive imports change (Task 1).

---

## Risks & Rollback

| Risk | Mitigation / Rollback |
|---|---|
| Task 1 primitive extraction subtly changes existing form rendering | Primitives are moved verbatim (identical classNames). Verify `/dashboard/agents/new` visually. Rollback: `git revert` the Task 1 commit — it is isolated. |
| `status` column absent causes Publish/Draft to fail | `saveAgent` retries without `status` on a status-related error; `is_active` is always sent. If the API does not surface a column error string, the implementer must confirm `/api/agents` ignores unknown keys, or gate `status` behind a known-migrated flag. |
| `/api/agents` POST rejects unknown body keys (e.g. `channel`, `whatsapp_*`) | These columns exist in `agents_config` per `types/database.ts`. If any insert fails, the error surfaces in the wizard banner; trim the body to known columns. Verify against a disposable project before prod. |
| `useLanguage()` does not expose a `language` code | Fallback: default to Hebrew (`csStrings(undefined)` returns he). Confirm the context shape in Task 5 Step 1. |
| Publish partially writes (agent created, a knowledge POST fails midway) | Agent + earlier rows persist; the wizard shows the error. v1 accepts partial writes (no transaction across REST calls); the admin can re-publish or edit via existing agent pages. Documented limitation, not a blocker. |
| Accidental prod write during testing | All live testing is user-performed against a disposable/local Supabase; this plan performs none. |

---

## Commit sequence summary

1. `refactor: extract shared form primitives from agent-form`
2. `feat: add optional status field to AgentConfig type`
3. `feat: add system prompt generator for client setup wizard`
4. `feat: add i18n strings for client setup wizard`
5. `feat: add client setup wizard component`
6. `feat: add hidden /admin/client-setup route`

# Maya Vertical Intelligence — Architecture

Maya is a **vertical intelligence system for appointment-based premium service businesses**, not a generalist assistant. Every component below answers one question: *"Does this make Maya measurably better at this niche, while keeping each client's data private?"*

Two non-negotiables:

1. **Privacy isolation by construction.** A client's raw messages, lead names, phones, summaries, and successful replies never reach another tenant — even indirectly through "shared learnings."
2. **Evidence-based knowledge only.** Every pattern Maya uses must point to specific events that produced it. Findings without evidence are dropped.

---

## The four-layer learning model

```
┌────────────────────────────────────────────────────────────────────┐
│  L4. ANALYST BRIEFINGS    per-client; generated; reads L1+L2+L3     │
│      facts • findings • recommendations • confidence • evidence     │
├────────────────────────────────────────────────────────────────────┤
│  L3. CURATED EXPERT KNOWLEDGE    global, manually approved          │
│      "clinics: follow-up <4h has 3× the reply rate of next-day"     │
├────────────────────────────────────────────────────────────────────┤
│  L2. VERTICAL SHARED KNOWLEDGE    anonymized, promoted from L1      │
│      "price → competitor objection appears in 41% of WA opens"      │
├────────────────────────────────────────────────────────────────────┤
│  L1. CLIENT-PRIVATE MEMORY    per tenant; raw + extracted           │
│      conversations • leads • outcomes • insights • this client's    │
│      questions, objections, intents                                  │
└────────────────────────────────────────────────────────────────────┘
```

Data flows **strictly upward and abstracted**: L1 → (promotion pipeline) → L2. L3 is curated externally. L4 reads L1+L2+L3 per client and writes only to itself, scoped to one tenant.

### L1 — Client-private memory (existing surfaces)

Lives in the tables already in production:

- `leads`, `call_logs`, `whatsapp_conversations`
- `maya_watch_leads`, `maya_watch_messages`, `maya_watch_actions`
- `lead_intelligence_insights`, `conversion_leak_signals`
- `audit_logs`

**Nothing about L1 changes structurally.** L1 governance: a documented allowlist of fields eligible for promotion, and a redaction map for the rest. Customer phones, names, addresses, free-text bodies, summaries, lead identifiers, and tenant identifiers **never** leave this layer in raw form.

### L2 — `vertical_patterns`

Anonymized, generalized patterns about the niche. No `client_id` column at all — cross-tenant association is structurally impossible.

**Promotion rules:**

1. A private pattern is promotion-eligible only when it has appeared in **≥ 3 distinct tenants** AND aggregate `frequency_count ≥ 20`.
2. `canonical_text` must pass an LLM **paraphrase + redaction** pass that strips: phones, names, addresses, dates with year, business names, agent names, URLs, currency amounts, and anything matching a configurable PII regex.
3. A human curator must approve every candidate before `status = 'approved'`. **Auto-promotion is off by default.**
4. Retirement: a pattern auto-retires after no client surfaces it for >180 days (configurable).

`evidence_digest` is a one-way hash of underlying `(client_id, insight_id, message_id, ts)` tuples — proves provenance without storing the events.

### L3 — `expert_knowledge`

The playbook. Things we know are true about premium appointment-based businesses that don't need data to justify. Versioned per `(vertical, topic)`. Only curators write here.

### L4 — `analyst_briefings` + `analyst_briefing_findings`

Per-client, evidence-bound analyst output. Every finding must cite at least one evidence pointer (L1 source rows, L2 pattern id, or L3 expert entry + version). Findings without citations are dropped post-generation.

---

## Privacy / cross-tenant boundaries

| Rule | How it's enforced |
|---|---|
| L1 raw never leaves a tenant | Admin-client reads with code-side `eq(client_id)` guard; no direct L1→L2 pipe |
| L2 carries no tenant-identifying field | `vertical_patterns` has no `client_id` column |
| Promotion pipeline runs only on aggregated stats | Input to redaction step is `(canonical_text_candidate, support_count, frequency_count)`, never raw bodies |
| Redaction enforced before write | Regex sweep + LLM paraphrase + curator approval — three gates |
| L4 findings reference L2/L3 by id, not text | `evidence` jsonb stores pointers; UI resolves canonical text from the already-anonymized pattern row |
| Admin viewing another tenant's L4 is gated | `analyst_briefings.client_id` + same scoping as `/home/insights` |
| Clients see L4 outputs only, never raw proprietary knowledge | RLS: `vertical_patterns` and `expert_knowledge` are admin/service only. `analyst_briefings` is client-readable only for own `client_id`, only `status='published'`, only `visibility='client'` |

---

## Maya Analyst — discipline rules

Every L4 briefing is produced under these rules. Hallucination is a bug, not a stylistic concern.

1. **Inputs are explicit:**
   - L1: this client's data only, fetched in one pass with `client_id` scope.
   - L2: only `status='approved'` rows for this client's vertical.
   - L3: only `status='approved'` versions, pinned per finding.
2. **Outputs are tiered:**
   - **Facts** (always): pure observations + sample size + window.
   - **Findings** (only when sample size passes the floor): interpretation.
   - **Recommendations** (only when both above qualify): action.
3. **Evidence-bound:** every `analyst_briefing_findings` row carries an `evidence` jsonb pointing at L1/L2/L3 ids. A post-generation verifier drops any finding whose evidence set is empty.
4. **Sample-size floors:** default 20 events / 10 leads per finding. Below the floor → finding tagged low-confidence and the recommendation is suppressed.
5. **Insufficient-data is first-class:** small clients see explicit "we don't have enough conversations yet" rather than a fabricated trend.
6. **Confidence is computed, not narrated:** `confidence ∈ [0,1]` per row. The narrative never says "I'm pretty sure."
7. **No cross-tenant claims:** the analyst job is scoped to one `client_id` at a time. L2/L3 are read separately and merged in the response only by id, not by raw text.
8. **Reproducibility:** `prompt_hash` + `model_version` stored per briefing.

### Recommendation targets

Findings with `recommendation_target` get routed:

- `business_owner` → operator-facing action ("call these 4 leads", "shift appointment window").
- `maya_prompt` → suggest a prompt change for the agent (requires owner approval before applied).
- `faq` → suggest a knowledge_items addition.
- `flow` → suggest a conversion-flow change.

---

## Product rule

**Clients see the output of the intelligence layer. They never see the raw proprietary knowledge layer.**

- `vertical_patterns` and `expert_knowledge` are admin/service only via Supabase REST.
- The only L2/L3 content visible to a client is what an analyst briefing chose to *cite* — already-anonymized canonical text or already-curated playbook entries — surfaced inside an L4 finding for their own tenant.

---

## Where this shows up in product (evolves over future phases)

| Surface | Role |
|---|---|
| `/home/insights` | grouped findings (analyst output) with confidence + sample-size + evidence drilldown |
| `/home/briefings` | one card per published briefing |
| `/home/watch` | hero footer cites L3/L2 when a decision is anchored to a known pattern |
| `/home/agents` | "Maya תלמד" panel — findings with `recommendation_target='maya_prompt'/'faq'`, owner approves to apply |
| admin / curator | manage L2 candidate queue and L3 playbook entries; never reachable by clients |

---

## The intelligence moat — in one line

Maya isn't smarter because the model is bigger. Maya is smarter because every conversation in this niche, redacted and curated, makes the next conversation slightly better — for everyone in the niche, while no client ever sees another client's data.

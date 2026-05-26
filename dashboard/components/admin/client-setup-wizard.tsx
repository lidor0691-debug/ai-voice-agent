"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, ChevronLeft, Plus, Trash2 } from "lucide-react";
import { useLanguage } from "@/context/language-context";
import {
  Field,
  Input,
  Textarea,
  Select,
  StepIndicator,
} from "@/components/agents/form-primitives";
import {
  generateSystemPrompt,
  type PromptInputs,
} from "@/lib/generate-system-prompt";
import { PRESET_TRIGGERS } from "@/components/agents/client-assets-tab";

// ── Phone normalization ────────────────────────────────────────────────────────
function normalizePhone(raw: string): string {
  const trimmed = raw.trim();
  const hasPlus = trimmed.startsWith("+");
  const digits = trimmed.replace(/\D/g, "");
  return hasPlus ? `+${digits}` : digits;
}

function isValidPhone(phone: string): boolean {
  return /^\+\d{7,15}$/.test(phone);
}

// ── Local types ────────────────────────────────────────────────────────────────
interface CatalogItem {
  name: string;
  detail: string;
}

interface FaqItem {
  question: string;
  answer: string;
}

interface AssetItem {
  name: string;
  type: "link" | "pdf";
  content: string;
  trigger_key: string;
  customTrigger: boolean;
}

interface WizardState {
  business_name: string;
  agent_name: string;
  language: string;
  tone: string;
  channel: "voice" | "whatsapp";
  phone_number: string;
  whatsapp_enabled: boolean;
  whatsapp_number: string;
  lead_delivery_method: string;
  lead_delivery_target: string;
  services: CatalogItem[];
  pricing: CatalogItem[];
  faqs: FaqItem[];
  assets: AssetItem[];
  transfer_number: string;
  handoff_rules: string;
  required_fields: string;
  behavior_notes: string;
  system_prompt: string;
  status: "draft" | "ready_for_test" | "live";
}

const initialState: WizardState = {
  business_name: "",
  agent_name: "",
  language: "he",
  tone: "friendly",
  channel: "voice",
  phone_number: "",
  whatsapp_enabled: false,
  whatsapp_number: "",
  lead_delivery_method: "webhook",
  lead_delivery_target: "",
  services: [],
  pricing: [],
  faqs: [],
  assets: [],
  transfer_number: "",
  handoff_rules: "",
  required_fields: "",
  behavior_notes: "",
  system_prompt: "",
  status: "live", // Publish defaults to Live; Save Draft always forces "draft".
};

// ── Inline i18n strings ────────────────────────────────────────────────────────
const STRINGS = {
  he: {
    err_required: "שדה חובה",
    err_phone: "מספר טלפון לא תקין",
    err_prompt_empty: "יש לייצר או להזין הנחיית מערכת",
    err_trigger_required: "יש לבחור טריגר",
    title: "הגדרת לקוח חדש",
    subtitle: "אשף להגדרת סוכן AI עבור לקוח",
    cancel: "ביטול",
    step1: "עסק",
    step2: "ערוצים",
    step3: "תוכן",
    step4: "התנהגות",
    step5: "רשימת בדיקה",
    step6: "פרסום",
    prev: "הקודם",
    next: "הבא",
    business_name: "שם העסק",
    business_name_hint: "שם העסק של הלקוח",
    agent_name: "שם הסוכן",
    agent_name_hint: "שם הסוכן שיוצג למתקשרים",
    language: "שפת שיחה",
    tone: "סגנון",
    tone_friendly: "ידידותי",
    tone_professional: "מקצועי",
    tone_formal: "פורמלי",
    tone_casual: "קז'ואל",
    channel: "ערוץ",
    channel_voice: "שיחה קולית",
    channel_whatsapp: "וואטסאפ",
    phone_number: "מספר טלפון",
    phone_number_hint: "מספר קולי עם קידומת ארצית",
    whatsapp_enabled: "הפעל וואטסאפ",
    whatsapp_enabled_hint: "הפעל מענה וואטסאפ",
    whatsapp_number: "מספר וואטסאפ",
    lead_delivery_method: "אופן מסירת לידים",
    lead_webhook: "Webhook",
    lead_whatsapp: "וואטסאפ",
    lead_email: "אימייל",
    lead_delivery_target: "יעד מסירה",
    lead_delivery_target_hint: "URL, מספר וואטסאפ, או כתובת אימייל",
    services_title: "שירותים",
    services_add: "הוסף שירות",
    pricing_title: "תמחור",
    pricing_add: "הוסף פריט תמחור",
    faqs_title: "שאלות נפוצות",
    faqs_add: "הוסף שאלה",
    assets_title: "קבצים / קישורים",
    assets_add: "הוסף קובץ",
    name_label: "שם",
    detail_label: "פירוט",
    question_label: "שאלה",
    answer_label: "תשובה",
    asset_name: "שם הקובץ",
    asset_type: "סוג",
    asset_type_link: "קישור",
    asset_type_pdf: "PDF",
    asset_content: "URL / תוכן",
    asset_trigger: "טריגר",
    trigger_placeholder: "בחר טריגר",
    trigger_custom: "מותאם אישית",
    transfer_number: "מספר להעברה",
    transfer_number_hint: "מספר להעברת שיחה לנציג",
    handoff_rules: "חוקי העברה",
    handoff_rules_hint: "חוק אחד לכל שורה",
    required_fields: "שדות חובה לאיסוף",
    required_fields_hint: "שדה אחד לכל שורה (שם, טלפון, ...)",
    behavior_notes: "הנחיות נוספות",
    behavior_notes_hint: "הנחיות כלליות להתנהגות הסוכן",
    checklist_title: "רשימת בדיקה",
    checklist_subtitle: "בדוק שכל הנתונים הדרושים הוגדרו",
    checklist_note: "רשימה זו לתצוגה בלבד ואינה נשמרת.",
    check_voice: "מספר קולי הוגדר",
    check_whatsapp: "מספר וואטסאפ הוגדר",
    check_wa_followup: "מעקב וואטסאפ הוגדר",
    check_lead: "יעד מסירת לידים הוגדר",
    publish_title: "פרסום",
    prompt_label: "הנחיית מערכת",
    prompt_hint: "ניתן לערוך את הנחיית המערכת הנוצרת אוטומטית",
    regenerate: "ייצר מחדש",
    prompt_faq_note: "שאלות ותוכן נוסף יצורפו בזמן השיחה.",
    status_label: "סטטוס",
    status_draft: "טיוטה",
    status_ready: "מוכן לבדיקה",
    status_live: "פעיל",
    save_draft: "שמור טיוטה",
    publish: "פרסם",
    wiring_later: "חיבור לוגיקה — משימה עתידית",
    saving: "שומר…",
    draft_saved: "הטיוטה נשמרה",
    save_failed: "שמירת הטיוטה נכשלה",
    publishing: "מפרסם…",
    published: "הסוכן פורסם",
    publish_failed: "הפרסום נכשל",
    publish_partial: "הסוכן פורסם, אך {n} פריטים נכשלו",
  },
  en: {
    err_required: "Required",
    err_phone: "Invalid phone number",
    err_prompt_empty: "Generate or enter a system prompt",
    err_trigger_required: "Trigger is required",
    title: "New Client Setup",
    subtitle: "Wizard to configure an AI agent for a client",
    cancel: "Cancel",
    step1: "Business",
    step2: "Channels",
    step3: "Content",
    step4: "Behavior",
    step5: "Checklist",
    step6: "Publish",
    prev: "Back",
    next: "Next",
    business_name: "Business Name",
    business_name_hint: "The client's business name",
    agent_name: "Agent Name",
    agent_name_hint: "Name presented to callers",
    language: "Language",
    tone: "Tone",
    tone_friendly: "Friendly",
    tone_professional: "Professional",
    tone_formal: "Formal",
    tone_casual: "Casual",
    channel: "Channel",
    channel_voice: "Voice Call",
    channel_whatsapp: "WhatsApp",
    phone_number: "Phone Number",
    phone_number_hint: "Voice number with country code",
    whatsapp_enabled: "Enable WhatsApp",
    whatsapp_enabled_hint: "Enable WhatsApp response channel",
    whatsapp_number: "WhatsApp Number",
    lead_delivery_method: "Lead Delivery Method",
    lead_webhook: "Webhook",
    lead_whatsapp: "WhatsApp",
    lead_email: "Email",
    lead_delivery_target: "Delivery Target",
    lead_delivery_target_hint: "URL, WhatsApp number, or email address",
    services_title: "Services",
    services_add: "Add Service",
    pricing_title: "Pricing",
    pricing_add: "Add Pricing Item",
    faqs_title: "FAQs",
    faqs_add: "Add FAQ",
    assets_title: "Files / Links",
    assets_add: "Add Asset",
    name_label: "Name",
    detail_label: "Detail",
    question_label: "Question",
    answer_label: "Answer",
    asset_name: "Asset Name",
    asset_type: "Type",
    asset_type_link: "Link",
    asset_type_pdf: "PDF",
    asset_content: "URL / Content",
    asset_trigger: "Trigger",
    trigger_placeholder: "Select trigger",
    trigger_custom: "Custom",
    transfer_number: "Transfer Number",
    transfer_number_hint: "Number to transfer calls to a human agent",
    handoff_rules: "Handoff Rules",
    handoff_rules_hint: "One rule per line",
    required_fields: "Required Fields to Collect",
    required_fields_hint: "One field per line (name, phone, ...)",
    behavior_notes: "Additional Notes",
    behavior_notes_hint: "General behavior instructions for the agent",
    checklist_title: "Checklist",
    checklist_subtitle: "Verify all required data is configured",
    checklist_note: "This checklist is display-only and is not saved.",
    check_voice: "Voice number set",
    check_whatsapp: "WhatsApp number set",
    check_wa_followup: "WhatsApp follow-up configured",
    check_lead: "Lead delivery target set",
    publish_title: "Publish",
    prompt_label: "System Prompt",
    prompt_hint: "You can edit the auto-generated system prompt",
    regenerate: "Regenerate",
    prompt_faq_note: "FAQs and other content are attached at call time.",
    status_label: "Status",
    status_draft: "Draft",
    status_ready: "Ready for Test",
    status_live: "Live",
    save_draft: "Save Draft",
    publish: "Publish",
    wiring_later: "Logic wiring — future task",
    saving: "Saving…",
    draft_saved: "Draft saved",
    save_failed: "Failed to save draft",
    publishing: "Publishing…",
    published: "Agent published",
    publish_failed: "Publish failed",
    publish_partial: "Agent published, but {n} item(s) failed to save",
  },
} as const;

type Lang = keyof typeof STRINGS;

// ── Helpers ────────────────────────────────────────────────────────────────────
function buildPromptInputs(form: WizardState): PromptInputs {
  return {
    agentName: form.agent_name.trim() || "Maya",
    businessName: form.business_name.trim() || undefined,
    language: form.language,
    tone: form.tone,
    services: form.services
      .filter((s) => s.name.trim())
      .map((s) => ({ name: s.name.trim(), detail: s.detail.trim() || undefined })),
    pricing: form.pricing
      .filter((p) => p.name.trim())
      .map((p) => ({ name: p.name.trim(), detail: p.detail.trim() || undefined })),
    handoffRules: form.handoff_rules
      .split("\n")
      .map((r) => r.trim())
      .filter(Boolean),
    transferNumber: form.transfer_number.trim() || undefined,
    behaviorNotes: form.behavior_notes.trim() || undefined,
  };
}

// ── Component ──────────────────────────────────────────────────────────────────
export function ClientSetupWizard() {
  const { lang } = useLanguage();
  const uiLang: Lang = lang === "en" ? "en" : "he";
  const s = STRINGS[uiLang];
  const dir = uiLang === "en" ? "ltr" : "rtl";

  const router = useRouter();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<WizardState>(initialState);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedDraft, setSavedDraft] = useState(false);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [published, setPublished] = useState(false);
  const [publishWarning, setPublishWarning] = useState<string | null>(null);

  const set = <K extends keyof WizardState>(key: K, value: WizardState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const steps = [
    { number: 1, label: s.step1 },
    { number: 2, label: s.step2 },
    { number: 3, label: s.step3 },
    { number: 4, label: s.step4 },
    { number: 5, label: s.step5 },
    { number: 6, label: s.step6 },
  ];

  const validateStep = (n: number): boolean => {
    const errs: Record<string, string> = {};
    if (n === 1) {
      if (!form.business_name.trim()) errs.business_name = s.err_required;
      if (!form.agent_name.trim()) errs.agent_name = s.err_required;
    } else if (n === 2) {
      if (form.whatsapp_enabled) {
        if (!form.whatsapp_number.trim()) {
          errs.whatsapp_number = s.err_required;
        } else if (!isValidPhone(form.whatsapp_number)) {
          errs.whatsapp_number = s.err_phone;
        }
        if (form.phone_number.trim() && !isValidPhone(form.phone_number)) {
          errs.phone_number = s.err_phone;
        }
      } else {
        if (!form.phone_number.trim()) {
          errs.phone_number = s.err_required;
        } else if (!isValidPhone(form.phone_number)) {
          errs.phone_number = s.err_phone;
        }
      }
    } else if (n === 6) {
      if (!form.system_prompt.trim()) errs.system_prompt = s.err_prompt_empty;
    }
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return false;
    }
    return true;
  };

  const goNext = () => {
    if (!validateStep(step)) return;
    setErrors({});
    setStep((prev) => Math.min(prev + 1, 6));
  };
  const goBack = () => {
    setErrors({});
    setStep((prev) => Math.max(prev - 1, 1));
  };

  const regeneratePrompt = () => {
    const inputs = buildPromptInputs(form);
    set("system_prompt", generateSystemPrompt(inputs));
  };

  // ── List helpers ────────────────────────────────────────────────────────────
  const addCatalog = (key: "services" | "pricing") =>
    set(key, [...form[key], { name: "", detail: "" }]);
  const removeCatalog = (key: "services" | "pricing", idx: number) =>
    set(key, form[key].filter((_, i) => i !== idx));
  const updateCatalog = (
    key: "services" | "pricing",
    idx: number,
    field: keyof CatalogItem,
    value: string
  ) =>
    set(
      key,
      form[key].map((item, i) => (i === idx ? { ...item, [field]: value } : item))
    );

  const addFaq = () => set("faqs", [...form.faqs, { question: "", answer: "" }]);
  const removeFaq = (idx: number) =>
    set("faqs", form.faqs.filter((_, i) => i !== idx));
  const updateFaq = (idx: number, field: keyof FaqItem, value: string) =>
    set(
      "faqs",
      form.faqs.map((item, i) => (i === idx ? { ...item, [field]: value } : item))
    );

  const addAsset = () =>
    set("assets", [...form.assets, { name: "", type: "link", content: "", trigger_key: "", customTrigger: false }]);
  const removeAsset = (idx: number) =>
    set("assets", form.assets.filter((_, i) => i !== idx));
  const updateAsset = (idx: number, field: keyof AssetItem, value: string) =>
    set(
      "assets",
      form.assets.map((item, i) => (i === idx ? { ...item, [field]: value } : item))
    );

  // ── Agent payload builder ───────────────────────────────────────────────────
  // status drives is_active: live => active; draft / ready_for_test => inactive.
  function buildAgentPayload(status: WizardState["status"]): Record<string, unknown> {
    const requiredFields = form.required_fields.split("\n").map((x) => x.trim()).filter(Boolean);
    const rules = form.handoff_rules.split("\n").map((x) => x.trim()).filter(Boolean);
    return {
      business_name: form.business_name.trim() || null,
      agent_name: form.agent_name.trim(),
      language: form.language,
      tone: form.tone,
      channel: form.channel,
      phone_number: normalizePhone(form.phone_number),
      whatsapp_enabled: form.whatsapp_enabled,
      whatsapp_number: form.whatsapp_number ? normalizePhone(form.whatsapp_number) : "",
      lead_delivery_method: form.lead_delivery_method,
      lead_delivery_target: form.lead_delivery_target.trim(),
      transfer_number: form.transfer_number ? normalizePhone(form.transfer_number) : "",
      whatsapp_required_fields: requiredFields.length ? requiredFields : null,
      whatsapp_rules: rules.length ? rules : null,
      system_prompt: form.system_prompt.trim() || null,
      status,
      is_active: status === "live",
    };
  }

  // POST/PATCH the agent. Tolerant of a DB where the `status` column has not been
  // applied yet: if the write fails citing "status", retry once without it
  // (is_active still conveys live vs non-live).
  async function writeAgentRequest(
    method: "POST" | "PATCH",
    url: string,
    payload: Record<string, unknown>,
    failMsg: string
  ): Promise<{ id?: string; client_id?: string }> {
    const attempt = (body: Record<string, unknown>) =>
      fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let res = await attempt(payload);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (typeof data.error === "string" && /status/i.test(data.error) && "status" in payload) {
        const rest: Record<string, unknown> = { ...payload };
        delete rest.status;
        res = await attempt(rest);
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.error ?? failMsg);
        }
      } else {
        throw new Error(data.error ?? failMsg);
      }
    }
    return res.json();
  }

  // ── Save Draft handler ──────────────────────────────────────────────────────
  async function handleSaveDraft() {
    if (saving || savedDraft || agentId) return; // guard: POST-only, prevent duplicate drafts
    setSaveError(null);
    setErrors({});
    // Draft: validate steps 1 and 2 only; system_prompt may be empty in draft mode.
    // (Step 6 / system_prompt validation is reserved for future Publish.)
    for (const stepN of [1, 2] as const) {
      if (!validateStep(stepN)) {
        setStep(stepN);
        return;
      }
    }
    setErrors({});
    setSaving(true);
    try {
      const saved = await writeAgentRequest("POST", "/api/agents", buildAgentPayload("draft"), s.save_failed);
      setAgentId(saved.id ?? null);
      setSavedDraft(true);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : s.save_failed);
    } finally {
      setSaving(false);
    }
  }

  // ── Publish handler ─────────────────────────────────────────────────────────
  async function handlePublish() {
    if (saving || published) return;
    setSaveError(null);
    setPublishWarning(null);
    setErrors({});
    for (const stepN of [1, 2, 6] as const) {
      if (!validateStep(stepN)) {
        setStep(stepN);
        return;
      }
    }
    // Publish-only: any asset row with a name or content must have a trigger_key.
    const assetErrs: Record<string, string> = {};
    form.assets.forEach((a, idx) => {
      if ((a.name.trim() || a.content.trim()) && !a.trigger_key.trim()) {
        assetErrs[`asset_trigger_${idx}`] = s.err_trigger_required;
      }
    });
    if (Object.keys(assetErrs).length > 0) {
      setErrors(assetErrs);
      setStep(3);
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      let aId = agentId;
      let cId: string | null = null;
      if (aId) {
        const saved = await writeAgentRequest("PATCH", `/api/agents/${aId}`, buildAgentPayload(form.status), s.publish_failed);
        cId = saved.client_id ?? null;
      } else {
        const saved = await writeAgentRequest("POST", "/api/agents", buildAgentPayload(form.status), s.publish_failed);
        aId = saved.id ?? null;
        cId = saved.client_id ?? null;
        setAgentId(aId);
      }

      if (!aId) throw new Error(s.publish_failed);

      let failures = 0;

      const knowledge: { category: string; title: string; content: string }[] = [
        ...form.services.filter((x) => x.name.trim()).map((x) => ({ category: "service", title: x.name.trim(), content: x.detail.trim() || x.name.trim() })),
        ...form.pricing.filter((x) => x.name.trim()).map((x) => ({ category: "pricing", title: x.name.trim(), content: x.detail.trim() || x.name.trim() })),
        ...form.faqs.filter((x) => x.question.trim()).map((x) => ({ category: "faq", title: x.question.trim(), content: x.answer.trim() })),
      ];
      for (const item of knowledge) {
        try {
          const res = await fetch("/api/knowledge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ agent_id: aId, priority: 0, is_active: true, ...item }),
          });
          if (!res.ok) failures++;
        } catch {
          failures++;
        }
      }

      if (cId) {
        let order = 0;
        for (const a of form.assets.filter((x) => x.name.trim() && x.content.trim())) {
          try {
            const res = await fetch(`/api/clients/${cId}/assets`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                asset_name: a.name.trim(),
                asset_type: a.type,
                trigger_key: a.trigger_key.trim(),
                content: a.content.trim(),
                sort_order: order++,
                enabled: true,
              }),
            });
            if (!res.ok) failures++;
          } catch {
            failures++;
          }
        }
      } else {
        if (form.assets.some((x) => x.name.trim() && x.content.trim())) failures++;
      }

      setPublished(true);
      if (failures > 0) {
        setPublishWarning(s.publish_partial.replace("{n}", String(failures)));
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : s.publish_failed);
    } finally {
      setSaving(false);
    }
  }

  // ── Checklist derived items ─────────────────────────────────────────────────
  const checklistItems = [
    { label: s.check_voice, ok: form.phone_number.trim().length > 0 },
    {
      label: s.check_whatsapp,
      ok: form.whatsapp_enabled && form.whatsapp_number.trim().length > 0,
    },
    { label: s.check_wa_followup, ok: form.whatsapp_enabled },
    { label: s.check_lead, ok: form.lead_delivery_target.trim().length > 0 },
  ];

  return (
    <div className="flex-1 overflow-y-auto" dir={dir}>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">{s.title}</h1>
          <p className="text-gray-500 text-sm mt-0.5">{s.subtitle}</p>
        </div>
        <button
          onClick={() => router.back()}
          className="text-gray-400 hover:text-white text-sm px-4 py-2 rounded-lg border border-border hover:bg-surface-3 transition-colors"
        >
          {s.cancel}
        </button>
      </div>

      <div className="p-8 max-w-2xl mx-auto">
        <StepIndicator currentStep={step} steps={steps} />

        {/* ── Step 1: Business ── */}
        {step === 1 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label={s.business_name} hint={s.business_name_hint}>
                <Input
                  placeholder={s.business_name}
                  value={form.business_name}
                  onChange={(e) => set("business_name", e.target.value)}
                />
                {errors.business_name && <p className="text-xs text-red-400 mt-1">{errors.business_name}</p>}
              </Field>
              <Field label={s.agent_name} hint={s.agent_name_hint} required>
                <Input
                  placeholder={s.agent_name}
                  value={form.agent_name}
                  onChange={(e) => set("agent_name", e.target.value)}
                />
                {errors.agent_name && <p className="text-xs text-red-400 mt-1">{errors.agent_name}</p>}
              </Field>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label={s.language}>
                <Select
                  value={form.language}
                  onChange={(e) => set("language", e.target.value)}
                  options={[
                    { value: "he", label: "עברית" },
                    { value: "en", label: "English" },
                  ]}
                />
              </Field>
              <Field label={s.tone}>
                <Select
                  value={form.tone}
                  onChange={(e) => set("tone", e.target.value)}
                  options={[
                    { value: "friendly", label: s.tone_friendly },
                    { value: "professional", label: s.tone_professional },
                    { value: "formal", label: s.tone_formal },
                    { value: "casual", label: s.tone_casual },
                  ]}
                />
              </Field>
            </div>
          </div>
        )}

        {/* ── Step 2: Channels ── */}
        {step === 2 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <Field label={s.channel}>
              <Select
                value={form.channel}
                onChange={(e) => set("channel", e.target.value as "voice" | "whatsapp")}
                options={[
                  { value: "voice", label: s.channel_voice },
                  { value: "whatsapp", label: s.channel_whatsapp },
                ]}
              />
            </Field>

            <Field label={s.phone_number} hint={s.phone_number_hint}>
              <Input
                placeholder="+972501234567"
                value={form.phone_number}
                onChange={(e) => set("phone_number", normalizePhone(e.target.value))}
              />
              {errors.phone_number && <p className="text-xs text-red-400 mt-1">{errors.phone_number}</p>}
            </Field>

            {/* WhatsApp toggle */}
            <div className="flex items-center justify-between py-2 border-t border-border/50">
              <div>
                <p className="text-sm font-medium text-gray-200">{s.whatsapp_enabled}</p>
                <p className="text-xs text-gray-500 mt-0.5">{s.whatsapp_enabled_hint}</p>
              </div>
              <div
                onClick={() => set("whatsapp_enabled", !form.whatsapp_enabled)}
                className={`relative shrink-0 w-12 h-6 rounded-full transition-colors cursor-pointer ${
                  form.whatsapp_enabled ? "bg-brand-600" : "bg-surface-4"
                }`}
              >
                <div
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    form.whatsapp_enabled ? "translate-x-7" : "translate-x-1"
                  }`}
                />
              </div>
            </div>

            {form.whatsapp_enabled && (
              <Field label={s.whatsapp_number}>
                <Input
                  placeholder="+972501234567"
                  value={form.whatsapp_number}
                  onChange={(e) =>
                    set("whatsapp_number", normalizePhone(e.target.value))
                  }
                />
                {errors.whatsapp_number && <p className="text-xs text-red-400 mt-1">{errors.whatsapp_number}</p>}
              </Field>
            )}

            <Field label={s.lead_delivery_method}>
              <Select
                value={form.lead_delivery_method}
                onChange={(e) => set("lead_delivery_method", e.target.value)}
                options={[
                  { value: "webhook", label: s.lead_webhook },
                  { value: "whatsapp", label: s.lead_whatsapp },
                  { value: "email", label: s.lead_email },
                ]}
              />
            </Field>

            <Field label={s.lead_delivery_target} hint={s.lead_delivery_target_hint}>
              <Input
                placeholder="https://..."
                value={form.lead_delivery_target}
                onChange={(e) => set("lead_delivery_target", e.target.value)}
              />
            </Field>
          </div>
        )}

        {/* ── Step 3: Services & Content ── */}
        {step === 3 && (
          <div className="space-y-4">
            {/* Services */}
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
              <h2 className="text-white font-semibold text-base">{s.services_title}</h2>
              {form.services.map((item, idx) => (
                <div key={idx} className="flex gap-2 items-start">
                  <div className="flex-1 grid grid-cols-2 gap-2">
                    <Input
                      placeholder={s.name_label}
                      value={item.name}
                      onChange={(e) => updateCatalog("services", idx, "name", e.target.value)}
                    />
                    <Input
                      placeholder={s.detail_label}
                      value={item.detail}
                      onChange={(e) => updateCatalog("services", idx, "detail", e.target.value)}
                    />
                  </div>
                  <button
                    onClick={() => removeCatalog("services", idx)}
                    className="p-2 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button
                onClick={() => addCatalog("services")}
                className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                {s.services_add}
              </button>
            </div>

            {/* Pricing */}
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
              <h2 className="text-white font-semibold text-base">{s.pricing_title}</h2>
              {form.pricing.map((item, idx) => (
                <div key={idx} className="flex gap-2 items-start">
                  <div className="flex-1 grid grid-cols-2 gap-2">
                    <Input
                      placeholder={s.name_label}
                      value={item.name}
                      onChange={(e) => updateCatalog("pricing", idx, "name", e.target.value)}
                    />
                    <Input
                      placeholder={s.detail_label}
                      value={item.detail}
                      onChange={(e) => updateCatalog("pricing", idx, "detail", e.target.value)}
                    />
                  </div>
                  <button
                    onClick={() => removeCatalog("pricing", idx)}
                    className="p-2 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button
                onClick={() => addCatalog("pricing")}
                className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                {s.pricing_add}
              </button>
            </div>

            {/* FAQs */}
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
              <h2 className="text-white font-semibold text-base">{s.faqs_title}</h2>
              {form.faqs.map((item, idx) => (
                <div key={idx} className="flex gap-2 items-start">
                  <div className="flex-1 grid grid-cols-1 gap-2">
                    <Input
                      placeholder={s.question_label}
                      value={item.question}
                      onChange={(e) => updateFaq(idx, "question", e.target.value)}
                    />
                    <Input
                      placeholder={s.answer_label}
                      value={item.answer}
                      onChange={(e) => updateFaq(idx, "answer", e.target.value)}
                    />
                  </div>
                  <button
                    onClick={() => removeFaq(idx)}
                    className="p-2 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button
                onClick={addFaq}
                className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                {s.faqs_add}
              </button>
            </div>

            {/* Assets */}
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-3">
              <h2 className="text-white font-semibold text-base">{s.assets_title}</h2>
              {form.assets.map((item, idx) => (
                <div key={idx} className="flex gap-2 items-start">
                  <div className="flex-1 grid grid-cols-2 gap-2">
                    <Input
                      placeholder={s.asset_name}
                      value={item.name}
                      onChange={(e) => updateAsset(idx, "name", e.target.value)}
                    />
                    <Select
                      value={item.type}
                      onChange={(e) =>
                        updateAsset(idx, "type", e.target.value as "link" | "pdf")
                      }
                      options={[
                        { value: "link", label: s.asset_type_link },
                        { value: "pdf", label: s.asset_type_pdf },
                      ]}
                    />
                    {!item.customTrigger ? (
                      <Select
                        value={item.trigger_key}
                        onChange={(e) => {
                          const v = e.target.value;
                          set(
                            "assets",
                            form.assets.map((x, i) =>
                              i === idx
                                ? v === "__custom__"
                                  ? { ...x, customTrigger: true, trigger_key: "" }
                                  : { ...x, trigger_key: v }
                                : x
                            )
                          );
                        }}
                        options={[
                          { value: "", label: s.trigger_placeholder },
                          ...PRESET_TRIGGERS.map((tk) => ({ value: tk, label: tk })),
                          { value: "__custom__", label: s.trigger_custom },
                        ]}
                      />
                    ) : (
                      <Input
                        placeholder="trial_booked"
                        value={item.trigger_key}
                        onChange={(e) =>
                          set(
                            "assets",
                            form.assets.map((x, i) =>
                              i === idx
                                ? { ...x, trigger_key: e.target.value.toLowerCase().replace(/\s+/g, "_") }
                                : x
                            )
                          )
                        }
                      />
                    )}
                    <Input
                      placeholder={s.asset_content}
                      value={item.content}
                      onChange={(e) => updateAsset(idx, "content", e.target.value)}
                    />
                    {errors[`asset_trigger_${idx}`] && (
                      <p className="col-span-2 text-xs text-red-400">{errors[`asset_trigger_${idx}`]}</p>
                    )}
                  </div>
                  <button
                    onClick={() => removeAsset(idx)}
                    className="p-2 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button
                onClick={addAsset}
                className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                {s.assets_add}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Behavior ── */}
        {step === 4 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <Field label={s.transfer_number} hint={s.transfer_number_hint}>
              <Input
                placeholder="+972501234567"
                value={form.transfer_number}
                onChange={(e) => set("transfer_number", normalizePhone(e.target.value))}
              />
            </Field>
            <Field label={s.handoff_rules} hint={s.handoff_rules_hint}>
              <Textarea
                rows={4}
                placeholder={s.handoff_rules_hint}
                value={form.handoff_rules}
                onChange={(e) => set("handoff_rules", e.target.value)}
              />
            </Field>
            <Field label={s.required_fields} hint={s.required_fields_hint}>
              <Textarea
                rows={3}
                placeholder={s.required_fields_hint}
                value={form.required_fields}
                onChange={(e) => set("required_fields", e.target.value)}
              />
            </Field>
            <Field label={s.behavior_notes} hint={s.behavior_notes_hint}>
              <Textarea
                rows={4}
                placeholder={s.behavior_notes_hint}
                value={form.behavior_notes}
                onChange={(e) => set("behavior_notes", e.target.value)}
              />
            </Field>
          </div>
        )}

        {/* ── Step 5: Checklist ── */}
        {step === 5 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
            <div>
              <h2 className="text-white font-semibold text-base">{s.checklist_title}</h2>
              <p className="text-gray-500 text-sm mt-1">{s.checklist_subtitle}</p>
            </div>
            <div className="space-y-2">
              {checklistItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0"
                >
                  <span className="text-gray-300 text-sm">{item.label}</span>
                  <span
                    className={`text-sm font-semibold px-2 py-0.5 rounded ${
                      item.ok
                        ? "text-emerald-400 bg-emerald-500/10"
                        : "text-gray-500 bg-surface-3"
                    }`}
                  >
                    {item.ok ? "✓" : "—"}
                  </span>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600 mt-2">{s.checklist_note}</p>
          </div>
        )}

        {/* ── Step 6: Publish ── */}
        {step === 6 && (
          <div className="space-y-4">
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <h2 className="text-white font-semibold text-base">{s.publish_title}</h2>

              <Field label={s.prompt_label} hint={s.prompt_hint}>
                <Textarea
                  rows={12}
                  value={form.system_prompt}
                  onChange={(e) => set("system_prompt", e.target.value)}
                  placeholder="..."
                />
                {errors.system_prompt && <p className="text-xs text-red-400 mt-1">{errors.system_prompt}</p>}
              </Field>

              <div className="flex items-center justify-between">
                <button
                  onClick={regeneratePrompt}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-3 border border-border hover:border-brand-500 text-white text-sm font-medium transition-colors"
                >
                  {s.regenerate}
                </button>
                <p className="text-xs text-gray-600">{s.prompt_faq_note}</p>
              </div>
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <Field
                label={s.status_label}
                hint={uiLang === "he"
                  ? "Live מפעיל את הסוכן; טיוטה / מוכן לבדיקה משאירים אותו כבוי."
                  : "Live activates the agent; draft / ready for test keep it inactive."}
              >
                <Select
                  value={form.status}
                  onChange={(e) => set("status", e.target.value as WizardState["status"])}
                  options={[
                    { value: "draft", label: s.status_draft },
                    { value: "ready_for_test", label: s.status_ready },
                    { value: "live", label: s.status_live },
                  ]}
                />
              </Field>

              {savedDraft && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-lg flex items-center gap-2">
                  {s.draft_saved}
                </div>
              )}
              {saveError && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg">
                  {saveError}
                </div>
              )}
              {published && !publishWarning && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-lg">{s.published}</div>
              )}
              {publishWarning && (
                <div className="bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm px-4 py-3 rounded-lg">{publishWarning}</div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleSaveDraft}
                  disabled={saving || savedDraft}
                  title={savedDraft ? s.draft_saved : undefined}
                  className="flex-1 py-3 rounded-xl border border-border text-gray-200 text-sm font-medium hover:bg-surface-3 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saving ? s.saving : savedDraft ? s.draft_saved : s.save_draft}
                </button>
                <button
                  onClick={handlePublish}
                  disabled={saving || published}
                  className="flex-1 py-3 rounded-xl bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saving ? s.publishing : published ? s.published : s.publish}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Navigation ── */}
        <div className="flex justify-between mt-8">
          {step > 1 ? (
            <button
              onClick={goBack}
              className="flex items-center gap-2 text-gray-400 hover:text-white text-sm px-5 py-2.5 rounded-lg border border-border hover:bg-surface-3 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
              {s.prev}
            </button>
          ) : (
            <div />
          )}
          {step < 6 && (
            <button
              onClick={goNext}
              className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-6 py-2.5 rounded-lg transition-colors"
            >
              {s.next}
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

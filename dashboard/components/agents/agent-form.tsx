"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, ChevronRight, ChevronLeft } from "lucide-react";
import { AgentConfig } from "@/types/database";
import { useLanguage } from "@/context/language-context";

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

type FormData = Omit<AgentConfig, "id" | "created_at" | "updated_at">;

interface Props {
  initial?: Partial<FormData>;
  agentId?: string;
}

// ── Steps (built dynamically inside component from t.*) ───────────────────────

// ── UI primitives ─────────────────────────────────────────────────────────────

function Field({
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

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors"
    />
  );
}

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors resize-none"
    />
  );
}

function Select({
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

// ── Step indicator ────────────────────────────────────────────────────────────

function StepIndicator({
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

// ── Main form ─────────────────────────────────────────────────────────────────

export function AgentForm({ initial, agentId }: Props) {
  // Safety guard: in edit mode, block the form entirely if initial data is missing.
  // This prevents a blank form from overwriting an existing agent row on save.
  const isEditMode = Boolean(agentId);
  const initialLoaded = !isEditMode || (initial != null && Object.keys(initial).length > 0);

  const { t } = useLanguage();
  const steps = [
    { number: 1, label: t.step_business },
    { number: 2, label: t.step_voice },
    { number: 3, label: t.step_calls },
    { number: 4, label: t.step_leads },
    { number: 5, label: t.step_whatsapp },
    { number: 6, label: t.step_activation },
  ];

  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [testCallPhone, setTestCallPhone] = useState("");
  const [testCalling, setTestCalling] = useState(false);
  const [testCallStatus, setTestCallStatus] = useState<string | null>(null);
  const [testCallError, setTestCallError] = useState<string | null>(null);

  const [scheduleText, setScheduleText] = useState<string>(
    initial?.schedule != null ? JSON.stringify(initial.schedule, null, 2) : ""
  );

  const [requiredFieldsText, setRequiredFieldsText] = useState<string>(
    Array.isArray(initial?.whatsapp_required_fields)
      ? (initial.whatsapp_required_fields as string[]).join("\n")
      : ""
  );

  const [rulesText, setRulesText] = useState<string>(
    Array.isArray(initial?.whatsapp_rules)
      ? (initial.whatsapp_rules as string[]).join("\n")
      : ""
  );

  const [form, setForm] = useState<Partial<FormData>>({
    business_name: "",
    agent_name: "",
    phone_number: "",
    is_active: true,
    first_message: "",
    system_prompt: "",
    tone: "friendly",
    language: "he",
    voice_provider: "openai",
    voice_id: "shimmer",
    speaking_rate: 1.0,
    style_prompt: "",
    model_provider: "openai",
    model_name: "gpt-4o",
    temperature: 0.7,
    transfer_number: "",
    post_call_webhook_url: initial?.post_call_webhook_url ?? "",
    lead_delivery_method: "webhook",
    lead_delivery_target: "",
    whatsapp_enabled: false,
    whatsapp_number: "",
    whatsapp_followup_enabled: false,
    whatsapp_followup_type: "none",
    whatsapp_followup_template: "",
    whatsapp_goal: null,
    whatsapp_required_fields: null,
    whatsapp_rules: null,
    ...initial,
  });

  const set = (key: keyof FormData, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleTestCall = async () => {
    if (testCalling || !agentId) return;
    setTestCallError(null);
    setTestCallStatus(null);
    if (!testCallPhone.trim()) {
      setTestCallError(t.af_test_call_error);
      return;
    }
    setTestCalling(true);
    try {
      const res = await fetch("/api/test-call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, to_phone: testCallPhone.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setTestCallError(data.error ?? t.af_test_call_error);
      } else {
        setTestCallStatus(t.af_test_call_success);
      }
    } catch {
      setTestCallError(t.af_test_call_error);
    } finally {
      setTestCalling(false);
    }
  };

  const goNext = () => {
    if (step === 1) {
      if (!form.agent_name?.trim()) {
        setError(t.af_name_required);
        return;
      }
      const normalizedPhone = normalizePhone(form.phone_number ?? "");
      if (!normalizedPhone) {
        setPhoneError(t.af_phone_required);
        return;
      }
      if (!isValidPhone(normalizedPhone)) {
        setPhoneError(t.af_phone_invalid);
        return;
      }
    }
    setError(null);
    setPhoneError(null);
    setStep((s) => Math.min(s + 1, 6));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 1));

  const handleSubmit = async () => {
    if (!initialLoaded) {
      setError(t.af_load_error);
      return;
    }
    const normalizedPhone = normalizePhone(form.phone_number ?? "");
    setSaving(true);
    setError(null);
    try {
      const url = agentId ? `/api/agents/${agentId}` : "/api/agents";
      const method = agentId ? "PATCH" : "POST";

      // For PATCH: only send fields that differ from initial to avoid wiping data
      let payload: Record<string, unknown>;
      if (agentId && initial) {
        payload = {};
        for (const key of Object.keys(form) as Array<keyof FormData>) {
          if (form[key] !== (initial as Partial<FormData>)[key]) {
            payload[key] = form[key];
          }
        }
        payload.phone_number = normalizedPhone;
      } else {
        payload = { ...form, phone_number: normalizedPhone };
      }

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error ?? t.af_save_failed);
      }
      setSaved(true);
      setTimeout(() => {
        router.push("/dashboard/agents");
        router.refresh();
      }, 1200);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t.af_unknown_error);
    } finally {
      setSaving(false);
    }
  };

  const deliveryLabel: Record<string, string> = {
    webhook: t.af_lead_webhook,
    whatsapp: t.af_lead_wa,
    email: t.af_lead_email,
  };

  const speakingRateLabel =
    (form.speaking_rate ?? 1.0) <= 0.8
      ? t.af_speed_slow
      : (form.speaking_rate ?? 1.0) >= 1.2
      ? t.af_speed_fast
      : t.af_speed_normal;

  if (!initialLoaded) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 text-red-400" dir="rtl">
        {t.af_load_error}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" dir="rtl">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">
            {agentId ? t.af_edit_title : t.af_new_title}
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {agentId ? t.af_edit_subtitle : t.af_new_subtitle}
          </p>
        </div>
        <button
          onClick={() => router.back()}
          className="text-gray-400 hover:text-white text-sm px-4 py-2 rounded-lg border border-border hover:bg-surface-3 transition-colors"
        >
          {t.af_cancel}
        </button>
      </div>

      <div className="p-8 max-w-2xl mx-auto">
        {saved && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 shrink-0" />
            {t.af_saved_redirect}
          </div>
        )}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        <StepIndicator currentStep={step} steps={steps} />

        {/* ── שלב 1: פרטי העסק ── */}
        {step === 1 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <h2 className="text-white font-semibold text-base">{t.af_s1_title}</h2>
              <p className="text-gray-500 text-sm mt-1">{t.af_s1_subtitle}</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Field label={t.af_business_name_label} hint={t.af_business_name_hint}>
                <Input
                  placeholder={t.af_business_name_placeholder}
                  value={form.business_name ?? ""}
                  onChange={(e) => set("business_name", e.target.value)}
                />
              </Field>
              <Field
                label={t.af_agent_name_label}
                hint={t.af_agent_name_hint}
                required
              >
                <Input
                  placeholder={t.af_agent_name_placeholder}
                  value={form.agent_name ?? ""}
                  onChange={(e) => set("agent_name", e.target.value)}
                />
              </Field>
            </div>

            <Field
              label={t.af_phone_label}
              hint={t.af_phone_hint}
              required
            >
              <Input
                placeholder={t.af_phone_placeholder}
                value={form.phone_number ?? ""}
                onChange={(e) => {
                  set("phone_number", normalizePhone(e.target.value));
                  setPhoneError(null);
                }}
              />
              {phoneError && (
                <p className="text-xs text-red-400 mt-1">{phoneError}</p>
              )}
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field
                label={t.af_call_language_label}
                hint={t.af_call_language_hint}
              >
                <Select
                  value={form.language ?? "he"}
                  onChange={(e) => set("language", e.target.value)}
                  options={[
                    { value: "he", label: t.af_lang_he },
                    { value: "en", label: t.af_lang_en },
                    { value: "es", label: t.af_lang_es },
                    { value: "fr", label: t.af_lang_fr },
                    { value: "de", label: t.af_lang_de },
                  ]}
                />
              </Field>
              <Field
                label={t.af_tone_label}
                hint={t.af_tone_hint}
              >
                <Select
                  value={form.tone ?? "friendly"}
                  onChange={(e) => set("tone", e.target.value)}
                  options={[
                    { value: "friendly", label: t.af_tone_friendly },
                    { value: "professional", label: t.af_tone_professional },
                    { value: "formal", label: t.af_tone_formal },
                    { value: "casual", label: t.af_tone_casual },
                    { value: "empathetic", label: t.af_tone_empathetic },
                  ]}
                />
              </Field>
            </div>
          </div>
        )}

        {/* ── שלב 2: איך מאיה מדברת ── */}
        {step === 2 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <h2 className="text-white font-semibold text-base">{t.af_s2_title}</h2>
              <p className="text-gray-500 text-sm mt-1">{t.af_s2_subtitle}</p>
            </div>

            <Field
              label={t.af_voice_label}
              hint={t.af_voice_hint}
            >
              <Select
                value={form.voice_id ?? "shimmer"}
                onChange={(e) => set("voice_id", e.target.value)}
                options={[
                  { value: "shimmer", label: t.af_voice_shimmer },
                  { value: "coral", label: t.af_voice_coral },
                  { value: "sage", label: t.af_voice_sage },
                  { value: "alloy", label: t.af_voice_alloy },
                  { value: "echo", label: t.af_voice_echo },
                  { value: "verse", label: t.af_voice_verse },
                ]}
              />
            </Field>

            <Field
              label={t.af_speed_label}
              hint={t.af_speed_hint}
            >
              <div className="space-y-2 pt-1">
                <input
                  type="range"
                  min={0.7}
                  max={1.3}
                  step={0.1}
                  value={form.speaking_rate ?? 1.0}
                  onChange={(e) =>
                    set("speaking_rate", parseFloat(e.target.value))
                  }
                  className="w-full accent-brand-600"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>{t.af_speed_slow}</span>
                  <span className="text-white font-medium">{speakingRateLabel}</span>
                  <span>{t.af_speed_fast}</span>
                </div>
              </div>
            </Field>
            {/* ── Test Call ── */}
            {agentId && (
              <div className="pt-2 border-t border-border space-y-2">
                <label className="block text-sm text-gray-400">{t.af_test_call_label}</label>
                <div className="flex gap-2">
                  <input
                    type="tel"
                    value={testCallPhone}
                    onChange={(e) => setTestCallPhone(e.target.value)}
                    placeholder={t.af_test_call_placeholder}
                    className="flex-1 bg-surface-3 border border-border rounded-lg px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-brand-500"
                  />
                  <button
                    type="button"
                    disabled={testCalling || !testCallPhone.trim()}
                    onClick={handleTestCall}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-3 border border-border hover:border-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
                  >
                    {testCalling ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        {t.af_test_call_loading}
                      </>
                    ) : (
                      <>
                        <span>📞</span>
                        {t.af_test_call_btn}
                      </>
                    )}
                  </button>
                </div>
                {testCallStatus && <p className="text-sm text-green-400">{testCallStatus}</p>}
                {testCallError && <p className="text-sm text-red-400">{testCallError}</p>}
              </div>
            )}
          </div>
        )}

        {/* ── שלב 3: מה קורה בשיחות ── */}
        {step === 3 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <h2 className="text-white font-semibold text-base">{t.af_s3_title}</h2>
              <p className="text-gray-500 text-sm mt-1">{t.af_s3_subtitle}</p>
            </div>

            <Field
              label={t.af_first_message_label}
              hint={t.af_first_message_hint}
            >
              <Textarea
                rows={2}
                placeholder={t.af_first_message_placeholder}
                value={form.first_message ?? ""}
                onChange={(e) => set("first_message", e.target.value)}
              />
            </Field>

            <Field
              label={t.af_system_prompt_label}
              hint={t.af_system_prompt_hint}
            >
              <Textarea
                rows={10}
                placeholder={t.af_system_prompt_placeholder}
                value={form.system_prompt ?? ""}
                onChange={(e) => set("system_prompt", e.target.value)}
              />
            </Field>
          </div>
        )}

        {/* ── שלב 4: קבלת פניות ── */}
        {step === 4 && (
          <div className="space-y-4">
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
              <div>
                <h2 className="text-white font-semibold text-base">{t.af_s4_title}</h2>
                <p className="text-gray-500 text-sm mt-1">{t.af_s4_subtitle}</p>
              </div>

              <Field
                label={t.af_lead_method_label}
                hint={t.af_lead_method_hint}
              >
                <Select
                  value={form.lead_delivery_method ?? "webhook"}
                  onChange={(e) => set("lead_delivery_method", e.target.value)}
                  options={[
                    { value: "whatsapp", label: t.af_lead_wa },
                    { value: "email", label: t.af_lead_email },
                    { value: "webhook", label: t.af_lead_webhook },
                  ]}
                />
              </Field>

              <Field
                label={
                  form.lead_delivery_method === "whatsapp"
                    ? t.af_lead_wa_number_label
                    : form.lead_delivery_method === "email"
                    ? t.af_lead_email_label
                    : t.af_lead_webhook_label
                }
                hint={
                  form.lead_delivery_method === "whatsapp"
                    ? t.af_lead_wa_number_label
                    : form.lead_delivery_method === "email"
                    ? t.af_lead_email_label
                    : t.af_lead_webhook_label
                }
              >
                <Input
                  placeholder={
                    form.lead_delivery_method === "whatsapp"
                      ? t.af_lead_wa_placeholder
                      : form.lead_delivery_method === "email"
                      ? t.af_lead_email_placeholder
                      : t.af_lead_webhook_placeholder
                  }
                  value={form.lead_delivery_target ?? ""}
                  onChange={(e) => set("lead_delivery_target", e.target.value)}
                />
              </Field>
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
              <div>
                <h2 className="text-white font-semibold text-base">{t.af_transfer_label}</h2>
                <p className="text-gray-500 text-sm mt-1">{t.af_transfer_hint}</p>
              </div>

              <Field
                label={t.af_transfer_number_label}
                hint={t.af_transfer_number_hint}
              >
                <Input
                  placeholder="+972543033010"
                  value={form.transfer_number ?? ""}
                  onChange={(e) => set("transfer_number", e.target.value)}
                />
              </Field>
            </div>
          </div>
        )}

        {/* ── שלב 5: וואטסאפ ── */}
        {step === 5 && (
          <div className="space-y-4">
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
              <div>
                <h2 className="text-white font-semibold text-base">{t.af_s5_title}</h2>
                <p className="text-gray-500 text-sm mt-1">{t.af_s5_subtitle}</p>
              </div>

              {/* Enable WhatsApp toggle */}
              <div className="flex items-center justify-between py-2 border-b border-border/50">
                <div>
                  <p className="text-sm font-medium text-gray-200">{t.af_wa_enable_label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{t.af_wa_enable_hint}</p>
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
                <>
                  <Field
                    label={t.af_wa_number_label}
                    hint={t.af_wa_number_hint}
                  >
                    <Input
                      placeholder="+972543033010"
                      value={form.whatsapp_number ?? ""}
                      onChange={(e) => set("whatsapp_number", e.target.value)}
                    />
                  </Field>

                  {/* Follow-up toggle */}
                  <div className="flex items-center justify-between py-2 border-t border-border/50">
                    <div>
                      <p className="text-sm font-medium text-gray-200">{t.af_wa_followup_label}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{t.af_wa_followup_hint}</p>
                    </div>
                    <div
                      onClick={() => set("whatsapp_followup_enabled", !form.whatsapp_followup_enabled)}
                      className={`relative shrink-0 w-12 h-6 rounded-full transition-colors cursor-pointer ${
                        form.whatsapp_followup_enabled ? "bg-brand-600" : "bg-surface-4"
                      }`}
                    >
                      <div
                        className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                          form.whatsapp_followup_enabled ? "translate-x-7" : "translate-x-1"
                        }`}
                      />
                    </div>
                  </div>

                  {form.whatsapp_followup_enabled && (
                    <>
                      <Field
                        label={t.af_wa_template_what_label}
                        hint={t.af_wa_template_what_hint}
                      >
                        <Select
                          value={form.whatsapp_followup_type ?? "none"}
                          onChange={(e) => set("whatsapp_followup_type", e.target.value)}
                          options={[
                            { value: "summary",      label: t.af_wa_template_summary },
                            { value: "appointment",  label: t.af_wa_template_confirm },
                            { value: "next_step",    label: t.af_wa_template_followup },
                            { value: "custom",       label: t.af_wa_template_custom },
                          ]}
                        />
                      </Field>

                      {form.whatsapp_followup_type === "custom" && (
                        <Field
                          label={t.af_wa_template_label}
                          hint={t.af_wa_template_hint}
                        >
                          <Textarea
                            rows={4}
                            placeholder={t.af_wa_template_placeholder}
                            value={form.whatsapp_followup_template ?? ""}
                            onChange={(e) => set("whatsapp_followup_template", e.target.value)}
                          />
                        </Field>
                      )}
                    </>
                  )}
                </>
              )}

              {/* Appointment follow-up toggle */}
              <div className="flex items-center justify-between py-2 border-t border-border/50">
                <div>
                  <p className="text-sm font-medium text-gray-200">{t.af_appt_followup_label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{t.af_appt_followup_hint}</p>
                </div>
                <div
                  onClick={() => set("appointment_followup_enabled", !form.appointment_followup_enabled)}
                  className={`relative shrink-0 w-12 h-6 rounded-full transition-colors cursor-pointer ${
                    form.appointment_followup_enabled ? "bg-brand-600" : "bg-surface-4"
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                      form.appointment_followup_enabled ? "translate-x-7" : "translate-x-1"
                    }`}
                  />
                </div>
              </div>

              {form.appointment_followup_enabled && (
                <Field label={t.af_appt_followup_timing_label}>
                  <Select
                    value={form.appointment_followup_timing ?? "1_day"}
                    onChange={(e) => set("appointment_followup_timing", e.target.value)}
                    options={[
                      { value: "1_day",   label: t.af_appt_followup_timing_1day },
                      { value: "2_hours", label: t.af_appt_followup_timing_2hours },
                      { value: "1_hour",  label: t.af_appt_followup_timing_1hour },
                    ]}
                  />
                </Field>
              )}

              {!form.whatsapp_enabled && (
                <div className="rounded-lg bg-surface-3/50 border border-border/50 px-4 py-3">
                  <p className="text-xs text-gray-600 leading-relaxed">
                    {t.af_wa_disabled_hint}
                  </p>
                </div>
              )}
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <div>
                <h2 className="text-white font-semibold text-base">{t.af_wa_hours_label}</h2>
                <p className="text-gray-500 text-sm mt-1">{t.af_wa_hours_hint}</p>
              </div>
              <Field
                label={t.af_wa_hours_label}
                hint={t.af_wa_hours_hint}
              >
                <Textarea
                  rows={4}
                  placeholder='{"days":["Sun","Mon","Tue","Wed","Thu"],"hours":{"start":"09:00","end":"18:00"}}'
                  value={scheduleText}
                  onChange={(e) => {
                    setScheduleText(e.target.value);
                    try {
                      set("schedule", JSON.parse(e.target.value));
                    } catch {
                      set("schedule", null);
                    }
                  }}
                />
              </Field>
            </div>

            {/* WhatsApp behavior control */}
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <div>
                <h2 className="text-white font-semibold text-base">{t.af_wa_behavior_title}</h2>
                <p className="text-gray-500 text-sm mt-1">{t.af_wa_behavior_subtitle}</p>
              </div>

              <Field
                label={t.af_wa_goal_label}
                hint={t.af_wa_goal_hint}
              >
                <Textarea
                  rows={2}
                  placeholder={t.af_wa_goal_placeholder}
                  value={form.whatsapp_goal ?? ""}
                  onChange={(e) => set("whatsapp_goal", e.target.value || null)}
                />
              </Field>

              <Field
                label={t.af_wa_required_label}
                hint={t.af_wa_required_hint}
              >
                <Textarea
                  rows={4}
                  placeholder={t.af_wa_required_placeholder}
                  value={requiredFieldsText}
                  onChange={(e) => {
                    setRequiredFieldsText(e.target.value);
                    const lines = e.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
                    set("whatsapp_required_fields", lines.length > 0 ? lines : null);
                  }}
                />
              </Field>

              <Field
                label={t.af_wa_rules_label}
                hint={t.af_wa_rules_hint}
              >
                <Textarea
                  rows={4}
                  placeholder={t.af_wa_rules_placeholder}
                  value={rulesText}
                  onChange={(e) => {
                    setRulesText(e.target.value);
                    const lines = e.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
                    set("whatsapp_rules", lines.length > 0 ? lines : null);
                  }}
                />
              </Field>
            </div>
          </div>
        )}

        {/* ── שלב 6: הפעלה ── */}
        {step === 6 && (
          <div className="space-y-4">
            {/* סיכום */}
            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <div>
                <h2 className="text-white font-semibold text-base">{t.af_s6_title}</h2>
                <p className="text-gray-500 text-sm mt-1">{t.af_s6_subtitle}</p>
              </div>

              <div className="space-y-0">
                {[
                  { label: t.af_business_name_label, value: form.business_name || "—" },
                  { label: t.af_agent_name_label, value: form.agent_name || "—" },
                  { label: t.af_phone_label, value: form.phone_number || "—" },
                  {
                    label: t.af_call_language_label,
                    value:
                      form.language === "he"
                        ? t.af_lang_he
                        : form.language === "en"
                        ? t.af_lang_en
                        : (form.language ?? "—"),
                  },
                  {
                    label: t.af_lead_method_label,
                    value:
                      deliveryLabel[form.lead_delivery_method ?? "webhook"] ??
                      form.lead_delivery_method ??
                      "—",
                  },
                  {
                    label: t.af_lead_webhook_label,
                    value: form.lead_delivery_target?.trim()
                      ? t.af_configured
                      : t.af_not_configured,
                    warn: !form.lead_delivery_target?.trim(),
                  },
                  {
                    label: t.af_wa_enable_label,
                    value: form.whatsapp_enabled ? t.af_configured : t.af_not_configured,
                  },
                ].map(({ label, value, warn }) => (
                  <div
                    key={label}
                    className="flex justify-between items-center py-2.5 border-b border-border/50 last:border-0"
                  >
                    <span className="text-gray-500 text-sm">{label}</span>
                    <span
                      className={`text-sm font-medium ${
                        warn ? "text-amber-400" : "text-white"
                      }`}
                    >
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* טוגל הפעלה */}
            <div className="bg-surface-2 border border-border rounded-xl p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-white font-semibold text-base">{t.af_activation_title}</h2>
                  <p className="text-gray-500 text-sm mt-1">
                    {form.is_active ? t.af_active_hint : t.af_inactive_hint}
                  </p>
                </div>
                <div
                  onClick={() => set("is_active", !form.is_active)}
                  className={`relative shrink-0 w-12 h-6 rounded-full transition-colors cursor-pointer ${
                    form.is_active ? "bg-brand-600" : "bg-surface-4"
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                      form.is_active ? "translate-x-7" : "translate-x-1"
                    }`}
                  />
                </div>
              </div>
            </div>

            {/* כפתור שמירה */}
            <button
              onClick={handleSubmit}
              disabled={saving || saved}
              className={`w-full text-white font-semibold py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2 text-base ${
                saved
                  ? "bg-emerald-600 cursor-default"
                  : "bg-brand-600 hover:bg-brand-700 disabled:opacity-50"
              }`}
            >
              {saved ? (
                <>
                  <CheckCircle className="w-5 h-5" />
                  {t.af_saved}
                </>
              ) : saving ? (
                t.af_saving
              ) : agentId ? (
                t.af_save
              ) : (
                t.af_activate
              )}
            </button>
          </div>
        )}

        {/* ניווט */}
        <div className="flex justify-between mt-8">
          {step > 1 ? (
            <button
              onClick={goBack}
              className="flex items-center gap-2 text-gray-400 hover:text-white text-sm px-5 py-2.5 rounded-lg border border-border hover:bg-surface-3 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
              {t.af_prev}
            </button>
          ) : (
            <div />
          )}
          {step < 6 && (
            <button
              onClick={goNext}
              className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-6 py-2.5 rounded-lg transition-colors"
            >
              {t.af_next}
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

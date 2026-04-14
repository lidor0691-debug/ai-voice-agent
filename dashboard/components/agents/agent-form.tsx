"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, ChevronRight, ChevronLeft } from "lucide-react";
import { AgentConfig } from "@/types/database";

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

// ── Steps ─────────────────────────────────────────────────────────────────────

const STEPS = [
  { number: 1, label: "פרטי העסק" },
  { number: 2, label: "איך מאיה מדברת" },
  { number: 3, label: "מה קורה בשיחות" },
  { number: 4, label: "קבלת פניות" },
  { number: 5, label: "וואטסאפ" },
  { number: 6, label: "הפעלה" },
] as const;

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

function StepIndicator({ currentStep }: { currentStep: number }) {
  return (
    <div className="flex items-start justify-center gap-1 mb-8">
      {STEPS.map((step, idx) => {
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
            {idx < STEPS.length - 1 && (
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

  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);

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

  const goNext = () => {
    if (step === 1) {
      if (!form.agent_name?.trim()) {
        setError("יש להזין שם לנציגה");
        return;
      }
      const normalizedPhone = normalizePhone(form.phone_number ?? "");
      if (!normalizedPhone) {
        setPhoneError("יש להזין מספר טלפון");
        return;
      }
      if (!isValidPhone(normalizedPhone)) {
        setPhoneError("פורמט לא תקין — לדוגמה: +972533470757");
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
      setError("לא ניתן לשמור — נתוני הנציגה לא נטענו. רענן את הדף ונסה שנית.");
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
        throw new Error(data.error ?? "שמירה נכשלה");
      }
      setSaved(true);
      setTimeout(() => {
        router.push("/dashboard/agents");
        router.refresh();
      }, 1200);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "שגיאה לא ידועה");
    } finally {
      setSaving(false);
    }
  };

  const deliveryLabel: Record<string, string> = {
    webhook: "מערכת חיצונית",
    whatsapp: "וואטסאפ",
    email: "אימייל",
  };

  const speakingRateLabel =
    (form.speaking_rate ?? 1.0) <= 0.8
      ? "איטי"
      : (form.speaking_rate ?? 1.0) >= 1.2
      ? "מהיר"
      : "רגיל";

  if (!initialLoaded) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 text-red-400" dir="rtl">
        שגיאה בטעינת נתוני הנציגה. רענן את הדף.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" dir="rtl">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">
            {agentId ? "עריכת נציגה" : "הגדרת נציגה חדשה"}
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {agentId
              ? "עדכן את הגדרות הנציגה"
              : "כמה שלבים פשוטים — ומאיה מוכנה לענות לשיחות"}
          </p>
        </div>
        <button
          onClick={() => router.back()}
          className="text-gray-400 hover:text-white text-sm px-4 py-2 rounded-lg border border-border hover:bg-surface-3 transition-colors"
        >
          ביטול
        </button>
      </div>

      <div className="p-8 max-w-2xl mx-auto">
        {saved && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 shrink-0" />
            נשמר — מעביר לרשימה…
          </div>
        )}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        <StepIndicator currentStep={step} />

        {/* ── שלב 1: פרטי העסק ── */}
        {step === 1 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <h2 className="text-white font-semibold text-base">פרטי העסק שלך</h2>
              <p className="text-gray-500 text-sm mt-1">
                המידע הבסיסי שמאיה צריכה כדי לייצג אותך נכון
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Field label="שם העסק" hint="איך הלקוחות מכירים אתכם?">
                <Input
                  placeholder="למשל: סטודיו BPM"
                  value={form.business_name ?? ""}
                  onChange={(e) => set("business_name", e.target.value)}
                />
              </Field>
              <Field
                label="שם הנציגה"
                hint="איך מאיה תציג את עצמה בשיחה?"
                required
              >
                <Input
                  placeholder="למשל: מאיה"
                  value={form.agent_name ?? ""}
                  onChange={(e) => set("agent_name", e.target.value)}
                />
              </Field>
            </div>

            <Field
              label="מספר הטלפון של הנציגה"
              hint="המספר שהלקוחות מתקשרים אליו — הנציגה תענה עליו אוטומטית"
              required
            >
              <Input
                placeholder="+972533470757"
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
                label="שפת השיחות"
                hint="באיזו שפה מאיה תדבר עם הלקוחות?"
              >
                <Select
                  value={form.language ?? "he"}
                  onChange={(e) => set("language", e.target.value)}
                  options={[
                    { value: "he", label: "עברית" },
                    { value: "en", label: "אנגלית" },
                    { value: "es", label: "ספרדית" },
                    { value: "fr", label: "צרפתית" },
                    { value: "de", label: "גרמנית" },
                  ]}
                />
              </Field>
              <Field
                label="סגנון הדיבור"
                hint="איזה אווירה תרצה שתהיה בשיחות?"
              >
                <Select
                  value={form.tone ?? "friendly"}
                  onChange={(e) => set("tone", e.target.value)}
                  options={[
                    { value: "friendly", label: "ידידותי ונעים" },
                    { value: "professional", label: "מקצועי ורציני" },
                    { value: "formal", label: "רשמי" },
                    { value: "casual", label: "קז׳ואל ומשוחרר" },
                    { value: "empathetic", label: "אמפתי ומבין" },
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
              <h2 className="text-white font-semibold text-base">איך מאיה נשמעת</h2>
              <p className="text-gray-500 text-sm mt-1">
                בחר את הקול והקצב שהכי מתאים לעסק שלך
              </p>
            </div>

            <Field
              label="קול הנציגה"
              hint="בחר קול שמתאים לאופי העסק שלך — ניתן לשנות בכל עת"
            >
              <Select
                value={form.voice_id ?? "shimmer"}
                onChange={(e) => set("voice_id", e.target.value)}
                options={[
                  { value: "shimmer", label: "שימר — נשי, חמים ונעים" },
                  { value: "coral", label: "קורל — נשי, מקצועי" },
                  { value: "sage", label: "סייג׳ — נשי, רגוע" },
                  { value: "alloy", label: "אלוי — ניטרלי" },
                  { value: "echo", label: "אקו — גברי" },
                  { value: "verse", label: "ורס — גברי, מקצועי" },
                ]}
              />
            </Field>

            <Field
              label="קצב הדיבור"
              hint="כמה מהר מאיה תדבר — רוב הלקוחות מעדיפים קצב רגיל"
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
                  <span>איטי</span>
                  <span className="text-white font-medium">{speakingRateLabel}</span>
                  <span>מהיר</span>
                </div>
              </div>
            </Field>
          </div>
        )}

        {/* ── שלב 3: מה קורה בשיחות ── */}
        {step === 3 && (
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <h2 className="text-white font-semibold text-base">מה קורה בשיחות</h2>
              <p className="text-gray-500 text-sm mt-1">
                הגדר מה מאיה אומרת ואיך היא מתנהגת עם לקוחות
              </p>
            </div>

            <Field
              label="מה מאיה אומרת כשהיא עונה לשיחה?"
              hint="המשפט הראשון שהלקוח שומע — כתוב אותו בדיוק כפי שתרצה שייאמר"
            >
              <Textarea
                rows={2}
                placeholder="היי! כאן מאיה מסטודיו BPM. איך אפשר לעזור?"
                value={form.first_message ?? ""}
                onChange={(e) => set("first_message", e.target.value)}
              />
            </Field>

            <Field
              label="זהות העסק והוראות הליבה"
              hint="תאר מי מאיה, מה העסק עושה, ואיך היא צריכה להתנהג בכל ערוץ. זהו הבסיס שממנו כל השיחות — גם קוליות וגם וואטסאפ — ייבנו."
            >
              <Textarea
                rows={10}
                placeholder={`אתה מאיה, נציגת שירות של סטודיו BPM. המטרה שלך היא לברך לקוחות, לספר להם על השיעורים, ולקבל את הפרטים שלהם.

שאלי תמיד:
- מה השם המלא שלהם
- מספר הטלפון
- איזה סוג שיעור מעניין אותם

בסוף השיחה — סכמי את הפרטים ושאלי אם הם רוצים שניצור איתם קשר.`}
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
                <h2 className="text-white font-semibold text-base">
                  איך תקבל פניות?
                </h2>
                <p className="text-gray-500 text-sm mt-1">
                  אחרי כל שיחה, מאיה תשלח לך את פרטי הלקוח — לאן תרצה לקבל
                  אותם?
                </p>
              </div>

              <Field
                label="דרך קבלת הפניות"
                hint="בחר את הדרך הנוחה לך ביותר לקבל פרטי לקוחות"
              >
                <Select
                  value={form.lead_delivery_method ?? "webhook"}
                  onChange={(e) => set("lead_delivery_method", e.target.value)}
                  options={[
                    {
                      value: "whatsapp",
                      label: "וואטסאפ — קבל הודעה ישירה לטלפון",
                    },
                    { value: "email", label: "אימייל — קבל מייל עם הפרטים" },
                    {
                      value: "webhook",
                      label: "מערכת חיצונית — שלח ישירות למערכת שלי",
                    },
                  ]}
                />
              </Field>

              <Field
                label={
                  form.lead_delivery_method === "whatsapp"
                    ? "מספר הוואטסאפ שלך"
                    : form.lead_delivery_method === "email"
                    ? "כתובת האימייל שלך"
                    : "כתובת המערכת שלך"
                }
                hint={
                  form.lead_delivery_method === "whatsapp"
                    ? "הפניות יישלחו לוואטסאפ של המספר הזה אחרי כל שיחה"
                    : form.lead_delivery_method === "email"
                    ? "הפניות יישלחו לאימייל הזה אחרי כל שיחה"
                    : "הפניות יישלחו אוטומטית לכתובת הזו בסיום כל שיחה"
                }
              >
                <Input
                  placeholder={
                    form.lead_delivery_method === "whatsapp"
                      ? "+972543033010"
                      : form.lead_delivery_method === "email"
                      ? "leads@yourcompany.com"
                      : "https://your-app.com/webhooks/lead"
                  }
                  value={form.lead_delivery_target ?? ""}
                  onChange={(e) => set("lead_delivery_target", e.target.value)}
                />
              </Field>
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
              <div>
                <h2 className="text-white font-semibold text-base">
                  העברה לאדם אמיתי
                </h2>
                <p className="text-gray-500 text-sm mt-1">
                  אם לקוח מבקש לדבר עם אדם — לאן להעביר אותו?
                </p>
              </div>

              <Field
                label="מספר טלפון להעברה"
                hint="אופציונלי — אם לא מוגדר, מאיה תמשיך את השיחה בעצמה"
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
                <h2 className="text-white font-semibold text-base">ערוץ וואטסאפ</h2>
                <p className="text-gray-500 text-sm mt-1">
                  מאיה יכולה לשלוח הודעת וואטסאפ לאחר כל שיחה — כדי להמשיך את השיחה שם
                </p>
              </div>

              {/* Enable WhatsApp toggle */}
              <div className="flex items-center justify-between py-2 border-b border-border/50">
                <div>
                  <p className="text-sm font-medium text-gray-200">הפעל ערוץ וואטסאפ</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    מאפשר למאיה לשלוח ולקבל הודעות דרך וואטסאפ
                  </p>
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
                    label="מספר הוואטסאפ של העסק"
                    hint="המספר שממנו מאיה תשלח הודעות — חייב להיות מחובר ל-WhatsApp Business"
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
                      <p className="text-sm font-medium text-gray-200">שליחת הודעת מעקב אחרי שיחה</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        מיד בסיום השיחה — מאיה תשלח הודעה לוואטסאפ של הלקוח
                      </p>
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
                        label="מה לשלוח אחרי השיחה?"
                        hint="מאיה תשתמש במידע שנאסף בשיחה כדי להתאים את ההודעה"
                      >
                        <Select
                          value={form.whatsapp_followup_type ?? "none"}
                          onChange={(e) => set("whatsapp_followup_type", e.target.value)}
                          options={[
                            { value: "summary",      label: "סיכום השיחה — מה דיברנו ומה הצעד הבא" },
                            { value: "appointment",  label: "אישור פגישה — תאריך, שעה, פרטים" },
                            { value: "next_step",    label: "הודעת המשך — מה לצפות עכשיו" },
                            { value: "custom",       label: "הודעה מותאמת אישית" },
                          ]}
                        />
                      </Field>

                      {form.whatsapp_followup_type === "custom" && (
                        <Field
                          label="תבנית ההודעה"
                          hint="כתוב את ההודעה שתישלח — ניתן להשתמש ב-{{name}} ו-{{phone}} לפרטי הלקוח"
                        >
                          <Textarea
                            rows={4}
                            placeholder="היי {{name}}! כאן מאיה 😊 תודה שדיברנו. אחזור אליך בקרוב עם פרטים נוספים."
                            value={form.whatsapp_followup_template ?? ""}
                            onChange={(e) => set("whatsapp_followup_template", e.target.value)}
                          />
                        </Field>
                      )}
                    </>
                  )}
                </>
              )}

              {!form.whatsapp_enabled && (
                <div className="rounded-lg bg-surface-3/50 border border-border/50 px-4 py-3">
                  <p className="text-xs text-gray-600 leading-relaxed">
                    כאשר תפעיל את ערוץ הוואטסאפ, מאיה תוכל לשלוח הודעת מעקב לאחר כל שיחה ולהמשיך את השיחה דרך וואטסאפ — כאילו היא אותה נציגה.
                  </p>
                </div>
              )}
            </div>

            <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-4">
              <div>
                <h2 className="text-white font-semibold text-base">שעות פעילות</h2>
                <p className="text-gray-500 text-sm mt-1">
                  באילו ימים ושעות הנציגה זמינה לענות — אופציונלי
                </p>
              </div>
              <Field
                label="שעות פעילות"
                hint='JSON — ימים ושעות שבהן הנציגה פעילה. לדוגמה: {"days":["Sun","Mon","Tue","Wed","Thu"],"hours":{"start":"09:00","end":"18:00"}}'
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
                <h2 className="text-white font-semibold text-base">התנהגות בוואטסאפ</h2>
                <p className="text-gray-500 text-sm mt-1">
                  הגדרות ספציפיות לערוץ הוואטסאפ — אלה יתווספו על גבי זהות הליבה של הנציגה
                </p>
              </div>

              <Field
                label="מטרת השיחה בוואטסאפ"
                hint="במשפט אחד — מה מאיה צריכה להשיג בשיחת הוואטסאפ?"
              >
                <Textarea
                  rows={2}
                  placeholder="לאסוף פרטי לקוח ולקבוע פגישת ייעוץ ראשונית"
                  value={form.whatsapp_goal ?? ""}
                  onChange={(e) => set("whatsapp_goal", e.target.value || null)}
                />
              </Field>

              <Field
                label="פרטים לאיסוף מהלקוח"
                hint="כתוב פרט אחד בכל שורה — מאיה תוודא שאוספת את כולם"
              >
                <Textarea
                  rows={4}
                  placeholder={"שם מלא\nמספר טלפון\nגיל הילד\nתחום עניין"}
                  value={requiredFieldsText}
                  onChange={(e) => {
                    setRequiredFieldsText(e.target.value);
                    const lines = e.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
                    set("whatsapp_required_fields", lines.length > 0 ? lines : null);
                  }}
                />
              </Field>

              <Field
                label="כללי התנהגות"
                hint="כתוב כלל אחד בכל שורה — מאיה תפעל לפיהם לאורך כל השיחה"
              >
                <Textarea
                  rows={4}
                  placeholder={"שאל רק שאלה אחת בכל הודעה\nאל תבטיח מחירים\nסיים תמיד עם הצעד הבא הברור"}
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
                <h2 className="text-white font-semibold text-base">
                  סיכום ההגדרות
                </h2>
                <p className="text-gray-500 text-sm mt-1">
                  בדוק שהכל נכון לפני ההפעלה
                </p>
              </div>

              <div className="space-y-0">
                {[
                  { label: "שם העסק", value: form.business_name || "—" },
                  { label: "שם הנציגה", value: form.agent_name || "—" },
                  { label: "מספר טלפון", value: form.phone_number || "—" },
                  {
                    label: "שפה",
                    value:
                      form.language === "he"
                        ? "עברית"
                        : form.language === "en"
                        ? "אנגלית"
                        : (form.language ?? "—"),
                  },
                  {
                    label: "קבלת פניות",
                    value:
                      deliveryLabel[form.lead_delivery_method ?? "webhook"] ??
                      form.lead_delivery_method ??
                      "—",
                  },
                  {
                    label: "יעד הפניות",
                    value: form.lead_delivery_target?.trim()
                      ? "מוגדר ✓"
                      : "לא הוגדר",
                    warn: !form.lead_delivery_target?.trim(),
                  },
                  {
                    label: "ערוץ וואטסאפ",
                    value: form.whatsapp_enabled ? "מופעל ✓" : "לא מופעל",
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
                  <h2 className="text-white font-semibold text-base">
                    הפעלת הנציגה
                  </h2>
                  <p className="text-gray-500 text-sm mt-1">
                    {form.is_active
                      ? "הנציגה תענה לשיחות מיד לאחר השמירה"
                      : "הנציגה לא תענה לשיחות עד שתפעיל אותה"}
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
                  נשמר!
                </>
              ) : saving ? (
                "שומר…"
              ) : agentId ? (
                "שמור שינויים"
              ) : (
                "הפעל את הנציגה"
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
              הקודם
            </button>
          ) : (
            <div />
          )}
          {step < 6 && (
            <button
              onClick={goNext}
              className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-6 py-2.5 rounded-lg transition-colors"
            >
              הבא
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

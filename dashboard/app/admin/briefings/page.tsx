export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

interface BriefingRow {
  id: string;
  client_id: string;
  agent_id: string | null;
  period_start: string;
  period_end: string;
  generated_at: string;
  status: string;
  visibility: string;
  data_volume: number | null;
  volume_warning: string | null;
  summary_md: string | null;
  model_version: string | null;
  created_by: string | null;
  created_at: string;
}

interface FindingRow {
  id: string;
  briefing_id: string;
  finding_type: string;
  title: string;
  fact: string;
  interpretation: string | null;
  recommendation: string | null;
  recommendation_target: string | null;
  confidence: number | null;
  sample_size: number | null;
  evidence: unknown;
  created_at: string;
}

// ── Hebrew product-language mappings ─────────────────────────────────────

const FINDING_TYPE_HE: Record<string, string> = {
  repeated_question_cluster:     "שאלה שחוזרת",
  faq_candidate:                 "מועמד ל-FAQ",
  followup_gap:                  "פער בפולואפ",
  no_show_risk:                  "סיכון אי-הגעה",
  price_or_uncertainty_friction: "חוסר ודאות סביב מחיר",
  warm_dropoff:                  "התעניינות שננטשה",
  maya_prompt_gap:               "פער בהתנהגות מאיה",
};

const TARGET_HE: Record<string, string> = {
  maya_prompt:    "שיפור מאיה",
  business_owner: "פעולה לבעל העסק",
  faq:            "עדכון FAQ",
  flow:           "שיפור תהליך",
};

// Polarity per finding type: business-language framing.
const POLARITY: Record<string, "בעיה" | "הזדמנות"> = {
  repeated_question_cluster:     "בעיה",
  faq_candidate:                 "הזדמנות",
  followup_gap:                  "בעיה",
  no_show_risk:                  "בעיה",
  price_or_uncertainty_friction: "בעיה",
  warm_dropoff:                  "הזדמנות",
  maya_prompt_gap:               "בעיה",
};

function findingTypeLabel(t: string): string { return FINDING_TYPE_HE[t] ?? t; }
function targetLabel(t: string | null): string | null { return t ? (TARGET_HE[t] ?? t) : null; }
function polarityLabel(t: string): "בעיה" | "הזדמנות" { return POLARITY[t] ?? "בעיה"; }

// ── Playbook: deterministic templates per finding_type ───────────────────
// All strings authored here. No DB writes. No real send. Display-only.
// Placeholders like [מחיר מאושר], [כתובת], [יום/שעה] mean "the operator
// must fill this in for the business" — Maya is forbidden from inventing
// these values.

interface FindingPlaybook {
  action_bullet: string;        // single-line bullet for "הפעולות החשובות עכשיו"
  wa_template:   string;        // ready-to-paste WhatsApp message
  voice_script:  string;        // short script for phone conversations
  when_to_use:   string;        // operator guidance
  dont_say:      string;        // guardrail
  action: {
    action_type:     string;
    permission_mode: string;
    risk_level:      "סיכון נמוך" | "סיכון בינוני" | "סיכון גבוה";
    after_approval:  string;
  };
}

const PLAYBOOK: Record<string, FindingPlaybook> = {
  repeated_question_cluster: {
    action_bullet: "לבנות תשובת מחיר קבועה שמכשירה לפני מחיר",
    wa_template:
      "ברור לגמרי, המחיר תלוי קצת בגיל ובסוג השיעור שמתאים. כדי לא לזרוק לך סתם מספר לא מדויק, בת כמה הילדה ומה המטרה שלכם כרגע? אחרי זה אוכל לכוון אותך בצורה הרבה יותר מדויקת.",
    voice_script:
      "ברור, אני אגיד לך בכיף. רק כדי לא לתת לך מחיר שלא מתאים למקרה שלך, בת כמה הילדה ומה אתם מחפשים כרגע — שיעור ניסיון או מסגרת קבועה?",
    when_to_use:
      "כשלקוח שואל מחיר לפני שהבנו גיל, מטרה או סוג שיעור.",
    dont_say:
      "לא לתת מחיר מיידי לפני שאלה מכשירה, אלא אם העסק הגדיר מחיר מאושר מראש.",
    action: {
      action_type:     "עדכון תשובת מחיר במאיה",
      permission_mode: "דורש אישור לפני ביצוע",
      risk_level:      "סיכון בינוני",
      after_approval:
        "מאיה תוסיף נוסח תשובת מחיר מאושרת לבנק הידע, ותשתמש בו רק אחרי שאלה מכשירה.",
    },
  },
  faq_candidate: {
    action_bullet: "להוסיף תשובת FAQ ברורה על מיקום",
    wa_template:
      "השיעורים מתקיימים ב-[כתובת / אזור מדויק]. אם אתם מגיעים מאזור אחר בצפון, כתבו לי מאיפה ואתאים לכם את האפשרות הכי נוחה.",
    voice_script:
      "הסטודיו נמצא ב-[כתובת / אזור מדויק]. מאיפה אתם מגיעים? כדי שאוכל לוודא שזה נוח לכם מבחינת מרחק וזמנים.",
    when_to_use:
      "כשלקוח שואל איפה השיעורים מתקיימים או האם זה מתאים לו מבחינת מרחק.",
    dont_say:
      "לא להמציא כתובת או זמני פעילות אם הם לא קיימים בבנק הידע.",
    action: {
      action_type:     "הוספת תשובת FAQ",
      permission_mode: "דורש אישור לפני ביצוע",
      risk_level:      "סיכון בינוני",
      after_approval:
        "מאיה תוסיף תשובת מיקום לבנק הידע לאחר שהעסק יאשר כתובת או אזור מדויק.",
    },
  },
  followup_gap: {
    action_bullet: "להפעיל הודעת המשך אחת ללידים שהתעניינו ונעלמו",
    wa_template:
      "היי, רק רציתי לוודא שלא פספסנו אותך. אם עדיין רלוונטי לכם שיעור ניסיון, אשמח לכוון אתכם לזמן שמתאים.",
    voice_script:
      "אני חוזרת אליכם רק לוודא אם זה עדיין רלוונטי. אם כן, אפשר לבדוק יחד זמן שמתאים לשיעור ניסיון.",
    when_to_use:
      "כשלקוח התעניין, קיבל תשובה, ואז לא הגיב.",
    dont_say:
      "לא לשלוח כמה הודעות המשך ברצף בלי איתות חדש מהלקוח.",
    action: {
      action_type:     "שליחת הודעת המשך ללידים שקטים",
      permission_mode: "יכול להיות אוטומטי אם הלקוח מאשר מראש",
      risk_level:      "סיכון נמוך",
      after_approval:
        "מאיה תוכל לשלוח הודעת המשך אחת בלבד ללידים שהתעניינו ונעלמו, לפי חלון הזמן שהוגדר.",
    },
  },
  no_show_risk: {
    action_bullet: "להפעיל אישור פגישה לפני המועד",
    wa_template:
      "היי, מזכירים שיש לכם שיעור/פגישה ב-[יום/שעה]. אפשר לאשר שהכול מתאים?",
    voice_script:
      "רק מתקשרת לאשר שהשיעור/פגישה ב-[יום/שעה] עדיין מתאים לכם.",
    when_to_use:
      "לפני פגישה שנקבעה, במיוחד כשלא תועד אישור מחדש.",
    dont_say:
      "לא להשתמש בטון מאיים או רשמי מדי.",
    action: {
      action_type:     "שליחת אישור פגישה",
      permission_mode: "יכול להיות אוטומטי אם הלקוח מאשר מראש",
      risk_level:      "סיכון נמוך",
      after_approval:
        "מאיה תוכל לשלוח הודעת אישור לפני פגישה ולסמן מי אישר ומי לא.",
    },
  },
  price_or_uncertainty_friction: {
    action_bullet: "להוביל לקוח מתלבט לשיעור ניסיון או לשתי אפשרויות זמן",
    wa_template:
      "מובן לגמרי. הרבה פעמים הכי נכון להתחיל משיעור ניסיון כדי להבין אם זה מתאים לפני שמתחייבים. תרצו שאבדוק לכם שתי אפשרויות לזמן קרוב?",
    voice_script:
      "זה לגמרי בסדר להתלבט. בדרך כלל שיעור ניסיון נותן תמונה הרבה יותר ברורה. אפשר להציע לכם שתי אפשרויות לזמן קרוב?",
    when_to_use:
      "כשלקוח משלב התלבטות עם שאלת מחיר.",
    dont_say:
      "לא לנסות לשכנע בכוח ולא לרוץ ישר למחיר.",
    action: {
      action_type:     "שיפור מענה להתלבטות סביב מחיר",
      permission_mode: "דורש אישור לפני ביצוע",
      risk_level:      "סיכון בינוני",
      after_approval:
        "מאיה תוסיף נוסח שמוביל לשיעור ניסיון או לשתי אפשרויות זמן במקום לרוץ למחיר.",
    },
  },
};

function playbookFor(t: string): FindingPlaybook | null { return PLAYBOOK[t] ?? null; }

function confidenceBucket(c: number | null): { label: string; tone: "high" | "mid" | "low" | "unknown" } {
  if (c == null) return { label: "—", tone: "unknown" };
  if (c >= 0.7)  return { label: "בינונית-גבוהה", tone: "high" };
  if (c >= 0.5)  return { label: "בינונית",       tone: "mid" };
  return            { label: "נמוכה",           tone: "low" };
}

// ── Display-clean: scrub technical tokens from primary copy. Raw text
// still appears verbatim inside the collapsed "פרטים טכניים" sections. ──

const DISPLAY_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\blead_intelligence_insights\b/g, "תובנות"],
  [/\bmaya_watch_messages\b/g,        "הודעות"],
  [/\bmaya_watch_actions\b/g,         "פעולות"],
  [/\bknowledge_items\b/g,            "בנק הידע של מאיה"],
  [/\bfollowup_sent_at\b/g,           "תיעוד הודעת המשך"],
  [/\bfollowup_sent_kind\b/g,         "סוג הודעת המשך"],
  [/\blast_whatsapp_inbound_at\b/g,   "תיעוד הודעת וואטסאפ נכנסת אחרונה"],
  [/\bappointment_at\b/g,             "פגישה שנקבעה"],
  [/\blow_data\b/g,                   "דאטה ראשוני בלבד"],
  [/\bobjection\b/g,                  "התנגדות"],
  [/\bquestion\b/g,                   "שאלה"],
];

function displayClean(text: string | null | undefined): string {
  if (!text) return "";
  let out = text;
  for (const [pattern, replacement] of DISPLAY_REPLACEMENTS) out = out.replace(pattern, replacement);
  return out;
}

// ── Sentence helpers ─────────────────────────────────────────────────────

/** Take the first sentence of a Hebrew string (split on ". ", "—", "; ",
 *  or a paragraph break). Optionally cap length with ellipsis. */
function firstSentence(text: string | null | undefined, maxLen = 140): string {
  if (!text) return "";
  const trimmed = text.trim();
  // Split on the earliest occurrence of "<period><space>", "—", "; ", or "\n\n".
  const match = trimmed.match(/([\s\S]*?)(?:\.\s|—| ;|\n\n)/);
  let first = match ? match[1].trim() : trimmed;
  // Trailing standalone period removed for visual cleanliness.
  first = first.replace(/\.\s*$/, "");
  if (first.length > maxLen) first = first.slice(0, maxLen - 1).trim() + "…";
  return first;
}

/** Crisp action bullet for a finding. Prefers the deterministic playbook
 *  line keyed by finding_type; falls back to the finding's title (which is
 *  already a clean Hebrew headline). Never invents content. */
function actionBullet(f: FindingRow): string {
  const pb = playbookFor(f.finding_type);
  if (pb) return pb.action_bullet;
  return displayClean(f.title);
}

/** Derive a one-line diagnosis from interpretation (or fact as fallback). */
function oneLineDiagnosis(f: FindingRow): string {
  const src = f.interpretation || f.fact || "";
  return displayClean(firstSentence(src, 140));
}

/** Executive top-line diagnosis: list the top N finding titles in
 *  natural Hebrew. Title-only — never invents numbers or claims. */
function executiveDiagnosis(findings: FindingRow[]): string {
  if (findings.length === 0) return "אין עדיין דפוסים מרכזיים בבריפינג זה.";
  const ranked = [...findings]
    .sort((a, b) =>
      (b.confidence ?? 0) - (a.confidence ?? 0) ||
      (b.sample_size ?? 0) - (a.sample_size ?? 0),
    )
    .slice(0, Math.min(3, findings.length));
  const titles = ranked.map(f => displayClean(f.title));
  let list: string;
  if (titles.length === 1) list = titles[0];
  else if (titles.length === 2) list = `${titles[0]} ו${titles[1]}`;
  else list = `${titles.slice(0, -1).join(", ")}, ו${titles[titles.length - 1]}`;
  return `מאיה זיהתה מספר דפוסים מרכזיים בחלון הזה: ${list}.`;
}

/** Top action bullets, derived from top findings via the deterministic
 *  playbook (keyed by finding_type) rather than mechanical text slicing. */
function topActionBullets(findings: FindingRow[], maxItems = 4): string[] {
  return [...findings]
    .sort((a, b) =>
      (b.confidence ?? 0) - (a.confidence ?? 0) ||
      (b.sample_size ?? 0) - (a.sample_size ?? 0),
    )
    .slice(0, maxItems)
    .map(actionBullet)
    .filter(s => s.length > 0);
}

// ── Date / summary helpers ───────────────────────────────────────────────

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Jerusalem" });
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeZone: "Asia/Jerusalem" });
}

function renderSummary(md: string | null): React.ReactNode {
  if (!md) return null;
  const lines = displayClean(md).split("\n");
  const nodes: React.ReactNode[] = [];
  let para: string[] = [];
  const flush = (k: string) => {
    if (para.length === 0) return;
    nodes.push(
      <p key={`p-${k}`} className="text-gray-300 text-[13.5px] leading-relaxed whitespace-pre-wrap">
        {para.join("\n")}
      </p>,
    );
    para = [];
  };
  lines.forEach((line, i) => {
    if (line.startsWith("## ")) {
      flush(`f${i}`);
      nodes.push(
        <h4 key={`h-${i}`} className="text-white text-[13.5px] font-semibold mt-3 mb-1">
          {line.replace(/^##\s+/, "")}
        </h4>,
      );
    } else if (line.trim() === "") flush(`b${i}`);
    else para.push(line);
  });
  flush("end");
  return <div className="space-y-1">{nodes}</div>;
}

// ── Evidence summary: human bullets, no raw JSON ─────────────────────────

interface EvidenceSummary { bullets: string[]; techDetail: string }

function evidenceSummary(ev: unknown): EvidenceSummary {
  const empty: EvidenceSummary = { bullets: [], techDetail: "—" };
  if (!ev || typeof ev !== "object") return empty;
  const e = ev as Record<string, unknown>;
  const bullets: string[] = [];
  const tech: string[] = [];
  if (typeof e.layer === "string" && e.layer === "L1" && typeof e.table === "string") {
    const ids = Array.isArray(e.ids) ? e.ids.length : 0;
    if (ids > 0) {
      const noun = e.table === "leads" ? "לידים" : "תובנות";
      bullets.push(`מבוסס על ${ids} ${noun} מהדאטה של העסק`);
    }
    tech.push(`L1 · ${e.table} × ${ids}`);
  }
  const l3 = e.l3;
  if (Array.isArray(l3) && l3.length > 0) {
    bullets.push("נשען על עיקרון מקצועי מתוך ספר המשחקים של מאיה");
    const topics = l3
      .map(x => {
        if (!x || typeof x !== "object") return null;
        const t = (x as Record<string, unknown>).topic;
        const v = (x as Record<string, unknown>).version;
        if (typeof t !== "string") return null;
        return typeof v === "number" ? `${t} v${v}` : t;
      })
      .filter((s): s is string => !!s);
    if (topics.length > 0) tech.push(`L3 · ${topics.join(", ")}`);
  }
  const l2 = e.l2;
  if (Array.isArray(l2) && l2.length > 0) {
    bullets.push("כולל דפוס מצרפי מהענף");
    tech.push(`L2 × ${l2.length}`);
  }
  if (bullets.length === 0) bullets.push("מבוסס על דאטה פנימית");
  return { bullets, techDetail: tech.length > 0 ? tech.join("  ·  ") : "—" };
}

// ── Page ─────────────────────────────────────────────────────────────────

export default async function AdminBriefingsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const ctx = getUserContext(user);
  if (!ctx?.isAdmin) redirect("/home/watch");

  const { data: briefingsRaw, error: briefingsErr } = await supabase
    .from("analyst_briefings")
    .select(
      "id, client_id, agent_id, period_start, period_end, generated_at, status, visibility, " +
      "data_volume, volume_warning, summary_md, model_version, created_by, created_at",
    )
    .order("generated_at", { ascending: false })
    .limit(50);
  if (briefingsErr) console.error("[admin/briefings] briefings fetch failed:", briefingsErr.message);
  const briefings = (briefingsRaw ?? []) as unknown as BriefingRow[];

  const findingsByBriefing = new Map<string, FindingRow[]>();
  if (briefings.length > 0) {
    const ids = briefings.map(b => b.id);
    const { data: findingsRaw, error: findingsErr } = await supabase
      .from("analyst_briefing_findings")
      .select(
        "id, briefing_id, finding_type, title, fact, interpretation, recommendation, " +
        "recommendation_target, confidence, sample_size, evidence, created_at",
      )
      .in("briefing_id", ids)
      .order("created_at", { ascending: true });
    if (findingsErr) console.error("[admin/briefings] findings fetch failed:", findingsErr.message);
    for (const f of (findingsRaw ?? []) as unknown as FindingRow[]) {
      const list = findingsByBriefing.get(f.briefing_id) ?? [];
      list.push(f);
      findingsByBriefing.set(f.briefing_id, list);
    }
  }

  return (
    <div className="space-y-7 max-w-4xl">
      <header className="flex items-baseline justify-between gap-3" dir="rtl">
        <h1 className="text-white text-xl font-semibold">תובנות מאיה</h1>
        <span className="text-[11px] text-gray-500 tnum" dir="ltr">
          {briefings.length > 0 ? `${briefings.length} briefings` : "—"}
        </span>
      </header>

      {briefings.length === 0 ? (
        <div className="border border-border rounded-lg bg-surface-1 p-10 text-center text-gray-500 text-sm">
          אין עדיין בריפינגים להצגה.
        </div>
      ) : (
        <div className="space-y-8">
          {briefings.map(b => (
            <BriefingCard key={b.id} b={b} findings={findingsByBriefing.get(b.id) ?? []} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Briefing card ────────────────────────────────────────────────────────

function BriefingCard({ b, findings }: { b: BriefingRow; findings: FindingRow[] }) {
  const lowData = b.volume_warning === "low_data";
  const periodLabel = `${fmtDate(b.period_start)} → ${fmtDate(b.period_end)}`;
  const diagnosis = executiveDiagnosis(findings);
  const actions = topActionBullets(findings, 4);

  return (
    <article className="border border-border rounded-xl bg-surface-1 overflow-hidden shadow-[0_2px_20px_-10px_rgba(0,0,0,0.4)]">
      {/* Admin-only banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2 flex items-center justify-between gap-3">
        <span className="text-[11px] text-amber-300 font-medium" dir="rtl">
          תצוגת אדמין בלבד · לא גלוי ללקוח
        </span>
        <span className="text-[10px] text-gray-500 font-mono" dir="ltr">
          {b.status} · {b.visibility}
        </span>
      </div>

      {/* Executive hero: diagnosis + actions */}
      <section className="px-6 pt-6 pb-5" dir="rtl">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <h2 className="text-white text-[20px] font-semibold leading-tight">אבחנה מרכזית</h2>
          <span className="text-[11px] text-gray-500 tnum" dir="ltr">{periodLabel}</span>
          {lowData && <LowDataBadge />}
        </div>
        <p className="text-gray-200 text-[14.5px] leading-relaxed">{diagnosis}</p>

        {actions.length > 0 && (
          <div className="mt-5 border-r-2 border-brand-600/40 pr-4">
            <div className="text-[12px] uppercase tracking-wider text-gray-500 mb-2">
              הפעולות החשובות עכשיו
            </div>
            <ul className="space-y-1.5">
              {actions.map((a, i) => (
                <li key={i} className="text-[13.5px] text-gray-200 flex items-start gap-2 leading-relaxed">
                  <span className="text-brand-400 mt-1 shrink-0">←</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Secondary: full summary_md as "פירוט התדריך" */}
      {b.summary_md && (
        <section className="px-6 py-5 border-t border-border bg-surface-0/30" dir="rtl">
          <h3 className="text-white text-[14px] font-semibold mb-2">פירוט התדריך</h3>
          {renderSummary(b.summary_md)}
        </section>
      )}

      {/* Findings */}
      <section className="px-6 py-6 border-t border-border" dir="rtl">
        <div className="flex items-baseline gap-3 mb-5">
          <h2 className="text-white text-[16px] font-semibold">תובנות מרכזיות</h2>
          <span className="text-[11px] text-gray-500 tnum">{findings.length}</span>
        </div>
        <div className="space-y-5">
          {findings.length === 0 && (
            <div className="text-[12px] text-gray-500">אין תובנות בבריפינג זה.</div>
          )}
          {findings.map(f => <FindingCard key={f.id} f={f} />)}
        </div>
      </section>

      {/* Briefing-level technical details */}
      <details className="px-6 py-3 text-[11px] text-gray-500 group border-t border-border">
        <summary className="cursor-pointer select-none hover:text-gray-300 transition-colors" dir="rtl">
          פרטים טכניים
        </summary>
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-[10.5px] text-gray-500" dir="ltr">
          <TechRow label="client_id" value={b.client_id} />
          <TechRow label="agent_id" value={b.agent_id ?? "—"} />
          <TechRow label="period" value={`${fmtDateTime(b.period_start)} → ${fmtDateTime(b.period_end)}`} />
          <TechRow label="generated_at" value={fmtDateTime(b.generated_at)} />
          <TechRow label="data_volume" value={String(b.data_volume ?? "—")} />
          <TechRow label="volume_warning" value={b.volume_warning ?? "—"} />
          <TechRow label="model_version" value={b.model_version ?? "—"} />
          <TechRow label="created_by" value={b.created_by ?? "—"} />
        </div>
      </details>
    </article>
  );
}

function LowDataBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 text-[10.5px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-full px-2 py-0.5">
      <span className="w-1 h-1 rounded-full bg-amber-300" />
      דאטה ראשוני בלבד
    </span>
  );
}

function TechRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="text-gray-600 shrink-0">{label}:</span>
      <span className="text-gray-400 truncate" title={value}>{value}</span>
    </div>
  );
}

// ── Finding card ─────────────────────────────────────────────────────────

function FindingCard({ f }: { f: FindingRow }) {
  const ev = evidenceSummary(f.evidence);
  const confBucket = confidenceBucket(f.confidence);
  const target = targetLabel(f.recommendation_target);
  const polarity = polarityLabel(f.finding_type);
  const diagnosis = oneLineDiagnosis(f);

  return (
    <div className="border border-border rounded-lg bg-surface-2 px-5 py-4" dir="rtl">
      <h3 className="text-white text-[15px] font-medium leading-snug mb-2">{f.title}</h3>
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <PolarityPill kind={polarity} />
        <Pill kind="type">{findingTypeLabel(f.finding_type)}</Pill>
        {target && <Pill kind="target">{target}</Pill>}
        <ConfidencePill bucket={confBucket} />
      </div>

      {/* One-line diagnosis: short reframe, gives the "what it means" first. */}
      {diagnosis && (
        <p className="text-gray-300 text-[13.5px] italic leading-snug mb-3">{diagnosis}</p>
      )}

      <Section label="מה מאיה ראתה">{displayClean(f.fact)}</Section>
      {f.interpretation && <Section label="מה זה אומר">{displayClean(f.interpretation)}</Section>}
      {f.recommendation && <Section label="מה מומלץ לעשות">{displayClean(f.recommendation)}</Section>}

      <PlaybookSection finding={f} />

      <div className="mt-4 pt-3 border-t border-border/60">
        <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-2">על מה זה מבוסס</div>
        <ul className="space-y-1">
          {ev.bullets.map((b, i) => (
            <li key={i} className="text-[12.5px] text-gray-300 flex items-start gap-2">
              <span className="text-gray-600 mt-1 shrink-0">•</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
        <details className="mt-2 group">
          <summary className="cursor-pointer select-none text-[10.5px] text-gray-600 hover:text-gray-400 transition-colors" dir="rtl">
            פרטים טכניים
          </summary>
          <div className="mt-1.5 text-[10.5px] text-gray-500 font-mono flex flex-wrap gap-x-3 gap-y-1" dir="ltr">
            <span>type: {f.finding_type}</span>
            <span>target: {f.recommendation_target ?? "—"}</span>
            <span>conf: {f.confidence != null ? f.confidence.toFixed(2) : "—"}</span>
            <span>n: {f.sample_size ?? "—"}</span>
            <span>evidence: {ev.techDetail}</span>
          </div>
        </details>
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-2.5">
      <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-1">{label}</div>
      <div className="text-[13.5px] text-gray-200 leading-relaxed whitespace-pre-wrap">{children}</div>
    </div>
  );
}

// ── Playbook section: ready-to-use templates + describe-only "what Maya
//    could execute later". No buttons. No sends. No DB writes. ───────────

function PlaybookSection({ finding }: { finding: FindingRow }) {
  const pb = playbookFor(finding.finding_type);
  if (!pb) return null;

  return (
    <div className="mt-5 space-y-4">
      {/* Templates — approval-gated suggestions for the operator. */}
      <div className="rounded-lg border border-brand-600/30 bg-brand-600/[0.06] p-4">
        <div className="flex items-baseline justify-between gap-2 mb-3 flex-wrap">
          <h4 className="text-white text-[13.5px] font-semibold">מה לעשות בפועל</h4>
          <span className="text-[10.5px] text-brand-300/90 bg-brand-600/15 border border-brand-600/30 rounded-full px-2 py-0.5">
            הצעה לשימוש — דורשת אישור לפני שליחה ללקוחות
          </span>
        </div>
        <div className="space-y-3">
          <TemplateBlock label="הודעת וואטסאפ מוכנה" body={pb.wa_template} multiline />
          <TemplateBlock label="משפט לשיחה"          body={pb.voice_script} multiline />
          <TemplateBlock label="מתי להשתמש"          body={pb.when_to_use} />
          <TemplateBlock label="לא להגיד"            body={pb.dont_say} tone="warn" />
        </div>
      </div>

      {/* Read-only execution descriptor. No buttons. */}
      <div className="rounded-lg border border-border bg-surface-1/60 p-4">
        <div className="flex items-baseline justify-between gap-2 mb-3 flex-wrap">
          <h4 className="text-white text-[13.5px] font-semibold">מה מאיה יכולה לבצע</h4>
          <span className="text-[10.5px] text-gray-400 bg-gray-500/10 border border-gray-500/30 rounded-full px-2 py-0.5">
            תצוגה בלבד — ביצוע יתווסף בשלב הבא
          </span>
        </div>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-2 text-[12.5px]">
          <ExecRow label="פעולה" value={pb.action.action_type} />
          <ExecRow label="מצב הרשאה" value={pb.action.permission_mode} />
          <ExecRow label="רמת סיכון" valueNode={<RiskPill level={pb.action.risk_level} />} />
          <ExecRow label="מה יקרה לאחר אישור" value={pb.action.after_approval} fullWidth />
        </dl>
      </div>
    </div>
  );
}

function TemplateBlock({
  label, body, multiline = false, tone = "default",
}: { label: string; body: string; multiline?: boolean; tone?: "default" | "warn" }) {
  const bodyTone =
    tone === "warn"
      ? "text-amber-200/90 border-amber-500/30"
      : "text-gray-100 border-border";
  return (
    <div>
      <div className="text-[10.5px] uppercase tracking-wider text-gray-500 mb-1">{label}</div>
      <div
        className={`rounded-md border ${bodyTone} bg-surface-2/70 px-3 py-2 text-[13px] leading-relaxed ${
          multiline ? "whitespace-pre-wrap" : ""
        }`}
      >
        {body}
      </div>
    </div>
  );
}

function ExecRow({
  label, value, valueNode, fullWidth = false,
}: { label: string; value?: string; valueNode?: React.ReactNode; fullWidth?: boolean }) {
  return (
    <div className={fullWidth ? "sm:col-span-2" : ""}>
      <dt className="text-[10.5px] uppercase tracking-wider text-gray-500 mb-0.5">{label}</dt>
      <dd className="text-gray-200">{valueNode ?? value ?? "—"}</dd>
    </div>
  );
}

function RiskPill({ level }: { level: "סיכון נמוך" | "סיכון בינוני" | "סיכון גבוה" }) {
  const tone =
    level === "סיכון נמוך"   ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30" :
    level === "סיכון בינוני" ? "text-amber-300 bg-amber-500/10 border-amber-500/30" :
                                "text-rose-300 bg-rose-500/10 border-rose-500/30";
  return (
    <span className={`inline-block text-[11px] px-2 py-0.5 rounded-full border font-medium ${tone}`}>
      {level}
    </span>
  );
}

// ── Pills ────────────────────────────────────────────────────────────────

function PolarityPill({ kind }: { kind: "בעיה" | "הזדמנות" }) {
  const tone = kind === "בעיה"
    ? "text-rose-300 bg-rose-500/10 border-rose-500/30"
    : "text-emerald-300 bg-emerald-500/10 border-emerald-500/30";
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full border font-medium ${tone}`}>
      {kind}
    </span>
  );
}

function Pill({ kind, children }: { kind: "type" | "target"; children: React.ReactNode }) {
  const tone = kind === "type"
    ? "text-brand-300 bg-brand-600/15 border-brand-600/30"
    : "text-gray-300 bg-gray-500/10 border-gray-500/30";
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${tone}`}>
      {children}
    </span>
  );
}

function ConfidencePill({ bucket }: { bucket: { label: string; tone: "high" | "mid" | "low" | "unknown" } }) {
  const tone =
    bucket.tone === "high" ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30" :
    bucket.tone === "mid"  ? "text-sky-300 bg-sky-500/10 border-sky-500/30" :
    bucket.tone === "low"  ? "text-gray-400 bg-gray-500/10 border-gray-500/30" :
                              "text-gray-500 bg-gray-500/10 border-gray-500/30";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-full border ${tone}`}>
      <span className="text-[10px] uppercase tracking-wider opacity-70">רמת ביטחון</span>
      <span className="font-medium">{bucket.label}</span>
    </span>
  );
}

export const metadata = { title: "Admin · Briefings" };

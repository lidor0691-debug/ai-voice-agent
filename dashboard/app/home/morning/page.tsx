export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";

// ── Types ────────────────────────────────────────────────────────────────

interface BriefingRow {
  id: string;
  client_id: string;
  generated_at: string;
  status: string;
  visibility: string;
  volume_warning: string | null;
}

interface FindingRow {
  id: string;
  briefing_id: string;
  finding_type: string;
  confidence: number | null;
}

// ── Action templates (display-only, no DB writes) ────────────────────────
// Keyed by finding_type. Order in ACTION_ORDER is the deterministic
// priority used to pick the top-3 cards.

type FindingType =
  | "repeated_question_cluster"
  | "faq_candidate"
  | "followup_gap"
  | "no_show_risk"
  | "price_or_uncertainty_friction";

interface ActionTemplate {
  title: string;
  why: string;
  wa: string;
  permission: string;
  afterApproval: string;
  reasons: string[];
}

const ACTION_ORDER: FindingType[] = [
  "repeated_question_cluster",
  "faq_candidate",
  "followup_gap",
  "no_show_risk",
  "price_or_uncertainty_friction",
];

const ACTIONS: Record<FindingType, ActionTemplate> = {
  repeated_question_cluster: {
    title: "לאשר תשובת מחיר חדשה",
    why: "לקוחות שואלים מחיר מוקדם מדי, לפני שמאיה הספיקה להבין התאמה.",
    wa: "ברור לגמרי. כדי לכוון אותך למחיר הנכון ולא לזרוק סתם מספר, אשמח להבין רגע: בת כמה הילדה ומה אתם מחפשים כרגע — שיעור ניסיון, חוג קבוע או משהו לקראת אירוע? אחרי זה אוכל להגיד לך מה הכי מתאים ומה הטווח.",
    permission: "דורש אישור לפני שימוש",
    afterApproval: "מאיה תוכל להשתמש בנוסח הזה כשלקוח שואל מחיר לפני שיש מספיק הקשר.",
    reasons: [
      "מאיה זיהתה שזה חזר בשיחות או בלידים.",
      "מבוסס על הדאטה האחרון של העסק.",
      "נבדק מול ספר המשחקים המקצועי של מאיה.",
    ],
  },
  faq_candidate: {
    title: "להוסיף תשובת מיקום קבועה",
    why: "לקוחות שואלים איפה זה מתקיים, וזה מידע שכדאי לתת מוקדם יותר.",
    wa: "השיעורים מתקיימים ב-[כתובת / אזור מדויק]. אם אתם מגיעים מאזור אחר בצפון, כתבו לי מאיפה ואתאים לכם את האפשרות הכי נוחה.",
    permission: "דורש אישור לפני שימוש",
    afterApproval: "מאיה תוכל לענות על שאלות מיקום בצורה עקבית אחרי שהעסק יאשר את הכתובת או האזור.",
    reasons: [
      "מאיה זיהתה שזה חזר בשיחות או בלידים.",
      "מבוסס על הדאטה האחרון של העסק.",
      "נבדק מול ספר המשחקים המקצועי של מאיה.",
    ],
  },
  followup_gap: {
    title: "להפעיל הודעת המשך ללידים שקטים",
    why: "יש לידים שהתעניינו ונעלמו, ומאיה יכולה להחזיר אותם בעדינות לשיחה.",
    wa: "היי, רק רציתי לוודא שלא פספסנו אותך. אם עדיין רלוונטי לכם שיעור ניסיון, אשמח לכוון אתכם לזמן שמתאים.",
    permission: "יכול להיות אוטומטי אם תאשרו מראש",
    afterApproval: "מאיה תוכל לשלוח הודעת המשך אחת בלבד ללידים שהתעניינו ולא חזרו.",
    reasons: [
      "מאיה זיהתה לידים שלא חזרו לשיחה אחרי שהתעניינו.",
      "מבוסס על הדאטה האחרון של העסק.",
      "נבדק מול ספר המשחקים המקצועי של מאיה.",
    ],
  },
  no_show_risk: {
    title: "לאשר הודעת אישור פגישה",
    why: "פגישות שלא מקבלות אישור מחדש עלולות להפוך לאי-הגעה.",
    wa: "היי, מזכירים שיש לכם שיעור/פגישה ב-[יום/שעה]. אפשר לאשר שהכול מתאים?",
    permission: "יכול להיות אוטומטי אם תאשרו מראש",
    afterApproval: "מאיה תוכל לשלוח הודעת אישור לפני פגישה ולסמן מי אישר ומי לא.",
    reasons: [
      "מאיה זיהתה פגישות שעשויות לדרוש אישור מחדש.",
      "מבוסס על הדאטה האחרון של העסק.",
      "נבדק מול ספר המשחקים המקצועי של מאיה.",
    ],
  },
  price_or_uncertainty_friction: {
    title: "להוביל מתלבטים לשיעור ניסיון",
    why: "חלק מהלקוחות לא באמת שואלים רק מחיר, אלא מחפשים ביטחון לפני החלטה.",
    wa: "מובן לגמרי. הרבה פעמים הכי נכון להתחיל משיעור ניסיון כדי להבין אם זה מתאים לפני שמתחייבים. תרצו שאבדוק לכם שתי אפשרויות לזמן קרוב?",
    permission: "דורש אישור לפני שימוש",
    afterApproval: "מאיה תוכל להשתמש בנוסח שמוביל לשיעור ניסיון במקום לרוץ ישר למחיר.",
    reasons: [
      "מאיה זיהתה התלבטות שמופיעה לצד שאלת מחיר.",
      "מבוסס על הדאטה האחרון של העסק.",
      "נבדק מול ספר המשחקים המקצועי של מאיה.",
    ],
  },
};

// Passive "מה מאיה כבר עוקבת אחריו" cards — derived from finding_type
// presence in the briefing. Display-only, no counts.
const WATCH_ITEMS: Array<{ key: FindingType[]; label: string }> = [
  { key: ["repeated_question_cluster", "faq_candidate"], label: "שאלות שחוזרות מלקוחות" },
  { key: ["followup_gap"],                                label: "לידים שלא חזרו לשיחה" },
  { key: ["no_show_risk"],                                label: "פגישות שדורשות אישור" },
  { key: ["price_or_uncertainty_friction"],               label: "פערים בתשובות של מאיה" },
];

function isKnownType(t: string): t is FindingType {
  return (ACTION_ORDER as readonly string[]).includes(t);
}

// Pick top-3 actions. Within finding_type, prefer highest confidence.
// Across types, follow deterministic ACTION_ORDER. Returns mappable count
// total so we can render "יש עוד X פעולות בהמשך".
function rankActions(findings: FindingRow[]): { picked: FindingType[]; totalMappable: number } {
  const bestPerType = new Map<FindingType, number>();
  for (const f of findings) {
    if (!isKnownType(f.finding_type)) continue;
    const prev = bestPerType.get(f.finding_type) ?? -Infinity;
    const c = f.confidence ?? 0;
    if (c > prev) bestPerType.set(f.finding_type, c);
  }
  const ordered = ACTION_ORDER.filter(t => bestPerType.has(t));
  return { picked: ordered.slice(0, 3), totalMappable: ordered.length };
}

// ── Page ─────────────────────────────────────────────────────────────────

export default async function MorningPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const ctx = getUserContext(user);
  if (!ctx) redirect("/login");
  const identity = resolveHomeIdentity(user);

  // Build the briefing query. Admin: latest of any status/visibility (so
  // BPM draft/admin_only is previewable). Non-admin: only client-visible
  // published rows scoped to their client_id; RLS enforces the rest.
  let q = supabase
    .from("analyst_briefings")
    .select("id, client_id, generated_at, status, visibility, volume_warning")
    .order("generated_at", { ascending: false })
    .limit(1);
  if (!ctx.isAdmin) {
    q = q
      .eq("status", "published")
      .eq("visibility", "client")
      .eq("client_id", ctx.clientId);
  }
  const { data: briefingRaw, error: briefingErr } = await q;
  if (briefingErr) console.error("[home/morning] briefing fetch failed:", briefingErr.message);
  const briefing = ((briefingRaw ?? []) as unknown as BriefingRow[])[0] ?? null;

  let findings: FindingRow[] = [];
  if (briefing) {
    const { data: findingsRaw, error: findingsErr } = await supabase
      .from("analyst_briefing_findings")
      .select("id, briefing_id, finding_type, confidence")
      .eq("briefing_id", briefing.id);
    if (findingsErr) console.error("[home/morning] findings fetch failed:", findingsErr.message);
    findings = (findingsRaw ?? []) as unknown as FindingRow[];
  }

  const isAdminPreview =
    !!briefing && ctx.isAdmin &&
    (briefing.status !== "published" || briefing.visibility !== "client");

  const { picked, totalMappable } = briefing
    ? rankActions(findings)
    : { picked: [], totalMappable: 0 };
  const remaining = Math.max(0, totalMappable - picked.length);
  const lowData = briefing?.volume_warning === "low_data";

  const presentTypes = new Set(findings.map(f => f.finding_type));

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="watch" user={identity} />
      <div className="lg:ps-[200px] h-full overflow-y-auto overflow-x-hidden">
        <div className="max-w-3xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8" dir="rtl">
          {/* Admin preview banner */}
          {isAdminPreview && (
            <div className="rounded-lg border border-amber-400/40 bg-amber-50/70 px-4 py-2.5 text-[12px] text-amber-900/90">
              תצוגת אדמין — הלקוח עדיין לא רואה את זה
            </div>
          )}

          {/* Empty state */}
          {!briefing && (
            <section className="rounded-2xl border border-[#0B1714]/10 bg-white/60 px-6 py-10 text-center">
              <div className="maya-section-label mb-2">תדריך הבוקר של מאיה</div>
              <h1 className="text-[20px] font-semibold text-[#0B1714]/85 mb-2">
                עדיין אין תדריך מוכן
              </h1>
              <p className="text-[13.5px] text-[#0B1714]/60 leading-relaxed max-w-md mx-auto">
                מאיה תציג כאן פעולות יומיות אחרי שיצטבר מספיק מידע משיחות, הודעות ולידים.
              </p>
            </section>
          )}

          {/* Hero */}
          {briefing && (
            <header>
              <div className="maya-section-label mb-2">תדריך הבוקר של מאיה</div>
              <div className="flex items-baseline gap-3 flex-wrap">
                <h1 className="text-[26px] sm:text-[28px] font-semibold text-[#0B1714]/90 leading-tight">
                  {picked.length > 0
                    ? `בוקר טוב. יש ${picked.length} ${picked.length === 1 ? "פעולה שממתינה" : "פעולות שממתינות"} לאישור שלך.`
                    : "בוקר טוב. אין פעולות שממתינות לאישור כרגע."}
                </h1>
                {lowData && (
                  <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-800 bg-amber-100/80 border border-amber-300/60 rounded-full px-2 py-0.5">
                    <span className="w-1 h-1 rounded-full bg-amber-600" />
                    דאטה ראשוני בלבד
                  </span>
                )}
              </div>
              {picked.length > 0 && (
                <p className="mt-2.5 text-[13.5px] text-[#0B1714]/60 leading-relaxed max-w-2xl">
                  מאיה כבר הכינה את ההודעות והשלבים הבאים. אפשר לעבור עליהן ולהחליט מה לאשר כשנפעיל ביצוע.
                </p>
              )}
              <div className="mt-3">
                <span className="inline-flex items-center text-[11px] text-[#0B1714]/55 bg-[#0B1714]/[0.04] border border-[#0B1714]/10 rounded-full px-2.5 py-0.5">
                  תצוגה בלבד — אישור וביצוע יתווספו בשלב הבא
                </span>
              </div>
            </header>
          )}

          {/* Actions */}
          {briefing && picked.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-[15px] font-semibold text-[#0B1714]/80">
                מה מחכה לאישור
              </h2>
              <div className="space-y-4">
                {picked.map(t => <ActionCard key={t} t={t} />)}
              </div>
              {remaining > 0 && (
                <p className="text-[12.5px] text-[#0B1714]/50 pr-1">
                  יש עוד {remaining} {remaining === 1 ? "פעולה" : "פעולות"} בהמשך
                </p>
              )}
            </section>
          )}

          {/* Passive watch row */}
          {briefing && (
            <section className="space-y-3">
              <h2 className="text-[15px] font-semibold text-[#0B1714]/80">
                מה מאיה כבר עוקבת אחריה
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {WATCH_ITEMS.map(item => {
                  const active = item.key.some(k => presentTypes.has(k));
                  return (
                    <div
                      key={item.label}
                      className={[
                        "rounded-lg border px-3 py-3 text-[12.5px] leading-snug",
                        active
                          ? "border-[#0B1714]/15 bg-white/70 text-[#0B1714]/80"
                          : "border-[#0B1714]/8 bg-white/30 text-[#0B1714]/40",
                      ].join(" ")}
                    >
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className={[
                            "w-1.5 h-1.5 rounded-full",
                            active ? "bg-emerald-500/70" : "bg-[#0B1714]/20",
                          ].join(" ")}
                        />
                        {item.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      </div>
    </HomeShell>
  );
}

// ── Action card ──────────────────────────────────────────────────────────

function ActionCard({ t }: { t: FindingType }) {
  const a = ACTIONS[t];
  return (
    <article className="rounded-2xl border border-[#0B1714]/10 bg-white/75 px-5 sm:px-6 py-5 shadow-[0_1px_2px_rgba(11,23,20,0.04)]">
      <h3 className="text-[17px] font-semibold text-[#0B1714]/90 leading-snug">{a.title}</h3>
      <p className="mt-1.5 text-[13.5px] text-[#0B1714]/65 leading-relaxed">{a.why}</p>

      {/* WhatsApp preview */}
      <div className="mt-4">
        <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1.5">
          הודעת וואטסאפ מוכנה
        </div>
        <div className="rounded-lg border border-[#0B1714]/10 bg-[#FAF6EE]/80 px-3.5 py-2.5 text-[13.5px] text-[#0B1714]/85 leading-relaxed whitespace-pre-wrap">
          {a.wa}
        </div>
      </div>

      {/* Permission + after-approval */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1">מצב פעולה</div>
          <div className="text-[13px] text-[#0B1714]/75">{a.permission}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1">
            מה יקרה אחרי אישור
          </div>
          <div className="text-[13px] text-[#0B1714]/75">{a.afterApproval}</div>
        </div>
      </div>

      {/* Disabled-look chips — read-only, no onClick */}
      <div className="mt-4 flex flex-wrap gap-2" aria-hidden="true">
        <DisabledChip label="אישור בקרוב" />
        <DisabledChip label="עריכה בקרוב" />
        <DisabledChip label="אוטומציה בהרשאה" />
      </div>

      {/* Collapsed explanation */}
      <details className="mt-4 group">
        <summary className="cursor-pointer select-none text-[12.5px] text-[#0B1714]/55 hover:text-[#0B1714]/80 transition-colors">
          למה מאיה ממליצה על זה?
        </summary>
        <ul className="mt-2 space-y-1.5 pr-1">
          {a.reasons.map((r, i) => (
            <li key={i} className="text-[12.5px] text-[#0B1714]/70 leading-relaxed flex items-start gap-2">
              <span className="text-[#0B1714]/30 mt-1 shrink-0">•</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}

function DisabledChip({ label }: { label: string }) {
  return (
    <span
      aria-disabled="true"
      className="inline-flex items-center text-[11.5px] text-[#0B1714]/45 bg-[#0B1714]/[0.04] border border-[#0B1714]/10 rounded-full px-2.5 py-0.5"
    >
      {label}
    </span>
  );
}

export const metadata = { title: "Maya · תדריך הבוקר" };

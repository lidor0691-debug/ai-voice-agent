"use client";

import { useState, useEffect } from "react";

type Config = {
  businessName: string;
  phoneNumber: string;
  language: "he" | "en";
  twilioFrom: string;
  apiBase: string;
  riskAfterMin: number;
  noResponseAfterHours: number;
  followupTemplate: string;
  webhookConfigured: boolean;
  testBody: string;
};

const HEBREW_TEMPLATE =
  "שלום! שמתי לב שפנית אלינו ועדיין לא קיבלת מענה. איך אפשר לעזור?";
const ENGLISH_TEMPLATE =
  "Hi! I noticed you reached out and haven't heard back yet. How can I help?";

const DEFAULT_CONFIG: Config = {
  businessName: "",
  phoneNumber: "",
  language: "he",
  twilioFrom: "",
  apiBase: "https://ai-voice-agent-production-0a55.up.railway.app",
  riskAfterMin: 5,
  noResponseAfterHours: 24,
  followupTemplate: HEBREW_TEMPLATE,
  webhookConfigured: false,
  testBody: "כמה עולה תור לייעוץ?",
};

const STORAGE_KEY = "maya-watch-operator-config";

export default function MayaWatchOperatorPage() {
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const [lastResult, setLastResult] = useState<string>("");
  const [loading, setLoading] = useState<string | null>(null);
  const [leadCount, setLeadCount] = useState<number | null>(null);
  const [leads, setLeads] = useState<{ phone: string; status: string; booked_at: string | null }[] | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setConfig({ ...DEFAULT_CONFIG, ...JSON.parse(stored) });
    } catch {}
  }, []);

  const save = (updates: Partial<Config>) => {
    const next = { ...config, ...updates };
    setConfig(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const riskConfigured = config.riskAfterMin > 0;
  const followupExists = config.followupTemplate.trim().length > 0;
  const ready = config.webhookConfigured && riskConfigured && followupExists;

  const api = (path: string, opts?: RequestInit) =>
    fetch(`${config.apiBase}${path}`, opts);

  const sendTestInbound = async () => {
    setLoading("inbound");
    try {
      const phone = config.phoneNumber || "+972500000000";
      const body = config.testBody.trim() || (config.language === "he" ? "כמה עולה תור לייעוץ?" : "Hi, I'm interested");
      const res = await api("/maya-watch/inbound", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, body }),
      });
      const data = await res.json();
      setLastResult(JSON.stringify(data, null, 2));
    } catch (e: unknown) {
      setLastResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(null);
  };

  const viewLeads = async () => {
    setLoading("leads");
    try {
      const res = await api("/maya-watch/leads");
      const data = await res.json();
      const arr = data.leads ?? [];
      setLeadCount(arr.length);
      setLeads(arr);
      setLastResult(JSON.stringify(data, null, 2));
    } catch (e: unknown) {
      setLastResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(null);
  };

  const markBooked = async (phone: string) => {
    setLoading(`booked:${phone}`);
    try {
      const res = await api(`/maya-watch/leads/${encodeURIComponent(phone)}/mark-booked`, { method: "POST" });
      const data = await res.json();
      setLastResult(JSON.stringify(data, null, 2));
      // refresh leads
      const r2 = await api("/maya-watch/leads");
      const d2 = await r2.json();
      const arr = d2.leads ?? [];
      setLeadCount(arr.length);
      setLeads(arr);
    } catch (e: unknown) {
      setLastResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(null);
  };

  const runTick = async () => {
    setLoading("tick");
    try {
      const res = await api("/maya-watch/tick", { method: "POST" });
      const data = await res.json();
      setLastResult(JSON.stringify(data, null, 2));
    } catch (e: unknown) {
      setLastResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(null);
  };

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold">Maya Watch — Operator Setup</h1>
        <span className="text-xs bg-surface-3 text-gray-400 px-2 py-0.5 rounded-full border border-border">
          INTERNAL
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left column */}
        <div className="space-y-6">
          <Section title="Business Profile">
            <Row label="Business Name">
              <input
                className="input-base"
                value={config.businessName}
                onChange={(e) => save({ businessName: e.target.value })}
                placeholder="e.g. BPM Finance"
              />
            </Row>
            <Row label="Customer Phone (for test messages)">
              <input
                className="input-base"
                dir="ltr"
                style={{ textAlign: "left" }}
                value={config.phoneNumber}
                onChange={(e) => save({ phoneNumber: e.target.value })}
                placeholder="+972500000000"
              />
            </Row>
            <Row label="Language">
              <select
                className="input-base"
                value={config.language}
                onChange={(e) => {
                  const lang = e.target.value as "he" | "en";
                  save({
                    language: lang,
                    followupTemplate:
                      lang === "he" ? HEBREW_TEMPLATE : ENGLISH_TEMPLATE,
                  });
                }}
              >
                <option value="he">Hebrew (עברית)</option>
                <option value="en">English</option>
              </select>
            </Row>
          </Section>

          <Section title="Channels">
            <Row label="Twilio From Number">
              <input
                className="input-base"
                value={config.twilioFrom}
                onChange={(e) => save({ twilioFrom: e.target.value })}
                placeholder="whatsapp:+14155238886"
              />
            </Row>
            <Row label="API Base URL">
              <input
                className="input-base"
                value={config.apiBase}
                onChange={(e) => save({ apiBase: e.target.value })}
              />
            </Row>
            <Row label="Webhook URL (copy to Twilio Sandbox)">
              <div className="input-base text-gray-400 text-xs truncate cursor-text select-all">
                {config.apiBase}/maya-watch/inbound
              </div>
            </Row>
          </Section>

          <Section title="Maya Watch Settings">
            <Row label="Risk After (minutes)">
              <input
                type="number"
                className="input-base"
                value={config.riskAfterMin}
                min={1}
                onChange={(e) =>
                  save({ riskAfterMin: Number(e.target.value) })
                }
              />
            </Row>
            <Row label="No Response After (hours)">
              <input
                type="number"
                className="input-base"
                value={config.noResponseAfterHours}
                min={1}
                onChange={(e) =>
                  save({ noResponseAfterHours: Number(e.target.value) })
                }
              />
            </Row>
            <Row label="Follow-up Template">
              <textarea
                className="input-base h-20 resize-none"
                value={config.followupTemplate}
                onChange={(e) => save({ followupTemplate: e.target.value })}
                dir={config.language === "he" ? "rtl" : "ltr"}
              />
            </Row>
          </Section>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          <Section title="Readiness Panel">
            <div className="space-y-2">
              <Check
                ok={config.webhookConfigured}
                label="Webhook configured in Twilio Sandbox"
              />
              <Check
                ok={riskConfigured}
                label={`Risk timeout set (${config.riskAfterMin}m)`}
              />
              <Check ok={followupExists} label="Follow-up template defined" />
            </div>
            <div className="mt-4">
              <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded accent-violet-500"
                  checked={config.webhookConfigured}
                  onChange={(e) =>
                    save({ webhookConfigured: e.target.checked })
                  }
                />
                I configured the webhook in Twilio
              </label>
            </div>
            <div
              className={`mt-4 rounded-lg px-4 py-3 text-sm font-semibold border ${
                ready
                  ? "bg-emerald-900/30 text-emerald-400 border-emerald-800"
                  : "bg-surface-2 text-gray-500 border-border"
              }`}
            >
              {ready ? "✓ Maya Watch is READY" : "⚠ Setup incomplete"}
            </div>
          </Section>

          <Section title="Actions">
            <div className="space-y-2">
              <Row label="Test inbound message">
                <input
                  className="input-base"
                  dir="rtl"
                  style={{ textAlign: "right" }}
                  value={config.testBody ?? ""}
                  onChange={(e) => save({ testBody: e.target.value })}
                  placeholder="כמה עולה תור לייעוץ?"
                />
              </Row>
              <button
                className="btn-primary w-full"
                onClick={sendTestInbound}
                disabled={loading !== null}
              >
                {loading === "inbound"
                  ? "Sending..."
                  : "Send Test Inbound Message"}
              </button>
              <button
                className="btn-ghost w-full"
                onClick={viewLeads}
                disabled={loading !== null}
              >
                {loading === "leads" ? "Loading..." : "View All Leads"}
              </button>
              <button
                className="btn-ghost w-full"
                onClick={runTick}
                disabled={loading !== null}
              >
                {loading === "tick" ? "Running..." : "Run Tick (manual scan)"}
              </button>
            </div>
          </Section>

          {lastResult && (
            <Section title="Last Result">
              {leadCount !== null && (
                <div className="text-xs text-gray-500 mb-2">
                  {leadCount} lead(s) in memory
                </div>
              )}
              {leads !== null && leads.length > 0 && (
                <div className="space-y-1 mb-3">
                  {leads.map((lead) => (
                    <div key={lead.phone} className="flex items-center justify-between gap-2 bg-surface-2 rounded-lg px-3 py-2">
                      <div className="min-w-0">
                        <span className="text-xs text-gray-300 font-mono block truncate" dir="ltr">{lead.phone}</span>
                        <span className="text-xs text-gray-500">{lead.status}</span>
                      </div>
                      <button
                        className="btn-ghost text-xs px-2 py-1 flex-shrink-0 disabled:opacity-40"
                        disabled={!!lead.booked_at || loading !== null}
                        onClick={() => markBooked(lead.phone)}
                      >
                        {loading === `booked:${lead.phone}` ? "..." : lead.booked_at ? "Booked ✓" : "Mark Booked"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <pre className="text-xs text-gray-400 bg-surface-2 rounded-lg p-3 overflow-auto max-h-72 whitespace-pre-wrap break-all">
                {lastResult}
              </pre>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-5 space-y-4">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
        {title}
      </h2>
      {children}
    </div>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-500">{label}</label>
      {children}
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={ok ? "text-emerald-400" : "text-gray-600"}>
        {ok ? "✓" : "○"}
      </span>
      <span className={ok ? "text-gray-300" : "text-gray-600"}>{label}</span>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { X, ExternalLink } from "lucide-react";
import { waMeLink } from "@/lib/utils";

export interface LeadRow {
  id: string;
  created_at: string;
  name: string | null;
  phone: string;
  source: string | null;
  status: string | null;
  appointment_at: string | null;
  last_whatsapp_inbound_at: string | null;
  client_id: string | null;
}

interface ConversationMessage {
  role: "user" | "assistant" | string;
  content: string;
  timestamp?: string;
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short" });
}

function fmtTime(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short" });
}

export function LeadsTable({ leads }: { leads: LeadRow[] }) {
  const [selected, setSelected] = useState<LeadRow | null>(null);

  if (leads.length === 0) {
    return (
      <div className="maya-card text-center py-16 text-[#0B1714]/55 text-[14px]">
        אין לידים להצגה כרגע
      </div>
    );
  }

  return (
    <>
      <div className="maya-card overflow-x-auto" style={{ padding: 0 }}>
        <table className="w-full text-[13px] text-right">
          <thead className="text-[11px] uppercase tracking-wider text-[#0B1714]/50 border-b border-[#E6DCCB]/70">
            <tr>
              <th className="px-4 py-3 font-medium">שם</th>
              <th className="px-4 py-3 font-medium">טלפון</th>
              <th className="px-4 py-3 font-medium">סטטוס</th>
              <th className="px-4 py-3 font-medium">מקור</th>
              <th className="px-4 py-3 font-medium">וואטסאפ אחרון</th>
              <th className="px-4 py-3 font-medium">תיאום</th>
              <th className="px-4 py-3 font-medium">נוצר</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((l, i) => (
              <tr
                key={l.id}
                onClick={() => setSelected(l)}
                className={`cursor-pointer hover:bg-[#0B1714]/[0.04] ${
                  i % 2 === 0 ? "" : "bg-[#0B1714]/[0.025]"
                }`}
              >
                <td className="px-4 py-3 text-[#0B1714]/90">{l.name?.trim() || "—"}</td>
                <td className="px-4 py-3">
                  <span dir="ltr" className="tabular-nums [unicode-bidi:isolate] text-[#0B1714]/85">
                    {l.phone}
                  </span>
                </td>
                <td className="px-4 py-3 text-[#0B1714]/85">{l.status?.trim() || "—"}</td>
                <td className="px-4 py-3 text-[#0B1714]/70">{l.source?.trim() || "—"}</td>
                <td className="px-4 py-3 text-[#0B1714]/70 tnum">{fmtDateTime(l.last_whatsapp_inbound_at)}</td>
                <td className="px-4 py-3 text-[#0B1714]/70 tnum">{fmtDateTime(l.appointment_at)}</td>
                <td className="px-4 py-3 text-[#0B1714]/55 tnum">{fmtDateTime(l.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && <LeadDrawer lead={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function LeadDrawer({ lead, onClose }: { lead: LeadRow; onClose: () => void }) {
  const [messages, setMessages] = useState<ConversationMessage[] | null>(null);
  const [loading, setLoading] = useState(true);

  // ESC closes the drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Body scroll-lock while open.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Conversation fetch, cancellable on lead switch / unmount.
  useEffect(() => {
    setLoading(true);
    setMessages(null);
    const ctrl = new AbortController();
    fetch(`/api/whatsapp-history?phone=${encodeURIComponent(lead.phone)}`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : { messages: [] })
      .then((body: { messages?: ConversationMessage[] }) => {
        setMessages(Array.isArray(body.messages) ? body.messages : []);
      })
      .catch(err => {
        if (err?.name !== "AbortError") setMessages([]);
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [lead.id, lead.phone]);

  const wa = waMeLink(lead.phone);
  const recent = (messages ?? []).slice(-50);

  return (
    <div
      className="fixed inset-0 z-[100] maya-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={`פרטי ליד ${lead.name ?? lead.phone}`}
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="סגור"
        onClick={onClose}
        className="absolute inset-0 bg-[#0B1714]/35 backdrop-blur-sm w-full h-full"
      />
      {/* Drawer */}
      <aside
        className="absolute inset-y-0 right-0 w-full sm:w-[440px] max-w-[92vw] bg-[#FFFCF6]/95 backdrop-blur-xl border-l border-[#E6DCCB] flex flex-col maya-hebrew"
        style={{ boxShadow: "-30px 0 80px -20px rgba(20,19,14,0.4)" }}
        dir="rtl"
      >
        {/* Header */}
        <header className="px-5 py-4 border-b border-[#E6DCCB]/70 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[14px] text-[#0B1714]/90 truncate">
              {lead.name?.trim() || "—"}
            </div>
            <div className="text-[11px] text-[#0B1714]/55 mt-0.5 flex items-center gap-2 flex-wrap">
              <span dir="ltr" className="tabular-nums [unicode-bidi:isolate]">{lead.phone}</span>
              <span className="text-[#0B1714]/30">·</span>
              <span>{lead.status?.trim() || "—"}</span>
              <span className="text-[#0B1714]/30">·</span>
              <span>{lead.source?.trim() || "—"}</span>
            </div>
            <div className="text-[10.5px] text-[#0B1714]/45 mt-1 tnum">
              נוצר: {fmtDateTime(lead.created_at)}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="סגור"
            className="w-8 h-8 grid place-items-center rounded-lg text-[#0B1714]/55 hover:bg-[#0B1714]/[0.05] hover:text-[#0B1714]/85 shrink-0"
          >
            <X size={16} />
          </button>
        </header>

        {/* Meta strip */}
        <section className="px-5 py-3 border-b border-[#E6DCCB]/70 text-[11.5px] text-[#0B1714]/75 space-y-1">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[#0B1714]/55">וואטסאפ אחרון</span>
            <span className="tnum">{fmtDateTime(lead.last_whatsapp_inbound_at)}</span>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[#0B1714]/55">תיאום</span>
            <span className="tnum">{fmtDateTime(lead.appointment_at)}</span>
          </div>
        </section>

        {/* Conversation */}
        <section className="flex-1 overflow-y-auto px-5 py-4">
          <div className="maya-section-label mb-3">שיחה</div>
          {loading && (
            <div className="text-[12px] text-[#0B1714]/45">טוען…</div>
          )}
          {!loading && recent.length === 0 && (
            <div className="text-[12px] text-[#0B1714]/45">
              אין עדיין היסטוריית שיחה להצגה
            </div>
          )}
          {!loading && recent.length > 0 && (
            <div className="space-y-2.5">
              {recent.map((m, idx) => {
                const isUser = m.role === "user";
                const prefix = isUser ? "שאל" : "שלחה";
                const prefixClass = isUser ? "text-[#0B1714]/55" : "text-[#A8884B]";
                return (
                  <div key={idx} className="text-[12px] leading-snug">
                    <div className="flex items-baseline gap-1.5">
                      <span className={`font-medium shrink-0 ${prefixClass}`}>{prefix}:</span>
                      <span className="text-[10px] text-[#0B1714]/40 tnum">{fmtTime(m.timestamp)}</span>
                    </div>
                    <div className="text-[#0B1714]/85 whitespace-pre-wrap break-words ms-0.5">
                      {m.content}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Footer */}
        {wa && (
          <footer className="px-5 py-3 border-t border-[#E6DCCB]/70">
            <a
              href={wa}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-[12.5px] text-[#0B1714]/85 hover:text-[#0B1714]"
            >
              <ExternalLink size={14} />
              פתח בוואטסאפ
            </a>
          </footer>
        )}
      </aside>
    </div>
  );
}

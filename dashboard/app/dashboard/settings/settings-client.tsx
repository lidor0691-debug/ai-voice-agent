"use client";

import { useState } from "react";
import { Check, ExternalLink } from "lucide-react";
import { useLanguage } from "@/context/language-context";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <h2 className="text-[11px] text-gray-600 uppercase tracking-wider font-semibold mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm text-gray-300">{label}</label>
      {children}
      {hint && <p className="text-xs text-gray-600">{hint}</p>}
    </div>
  );
}

interface Props {
  isAdmin?: boolean;
}

export function SettingsClient({ isAdmin = false }: Props) {
  const [saved, setSaved] = useState(false);
  const { t } = useLanguage();

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="h-14 border-b border-border flex items-center justify-between px-6 flex-shrink-0 bg-surface-1">
        <div>
          <h1 className="text-white font-semibold text-sm tracking-tight">{t.page_settings_title}</h1>
          <p className="text-gray-600 text-[11px] mt-0.5">{t.page_settings_subtitle}</p>
        </div>
        <button
          onClick={handleSave}
          className="btn-primary flex items-center gap-2"
        >
          {saved ? <Check className="w-3.5 h-3.5" /> : null}
          {saved ? t.saved : t.save_changes}
        </button>
      </div>

      <div className="p-6 max-w-2xl space-y-5 bg-surface-0 min-h-full">
        {/* Platform — visible to all */}
        <Section title={t.section_platform}>
          <div className="space-y-4">
            <Field label={t.workspace_name_label}>
              <input
                defaultValue={t.workspace_name_default}
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors"
              />
            </Field>
            <Field label={t.default_language_label}>
              <select className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors">
                <option value="en" className="bg-surface-3">{t.lang_english}</option>
                <option value="he" className="bg-surface-3">{t.lang_hebrew}</option>
                <option value="es" className="bg-surface-3">{t.lang_spanish}</option>
              </select>
            </Field>
          </div>
        </Section>

        {/* Integrations — admin only */}
        {isAdmin && (
          <Section title={t.section_integrations}>
            <div className="space-y-4">
              <Field label={t.supabase_url_label} hint={t.supabase_url_hint}>
                <div className="w-full bg-surface-3/50 border border-border rounded-lg px-3 py-2 text-sm text-gray-500 font-mono truncate">
                  {t.supabase_configured}
                </div>
              </Field>
              <Field label={t.backend_url_label} hint={t.backend_url_hint}>
                <input
                  defaultValue="http://localhost:8000"
                  className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors"
                />
              </Field>
            </div>
          </Section>
        )}

        {/* Schema — admin only */}
        {isAdmin && (
          <Section title={t.section_schema}>
            <div className="space-y-3">
              <p className="text-gray-500 text-sm">{t.schema_desc}</p>
              <div className="bg-surface-3 rounded-lg p-3">
                <p className="text-gray-400 text-xs font-mono">{t.schema_file}</p>
              </div>
              <a
                href="https://supabase.com/dashboard"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-brand-400 hover:text-brand-300 text-sm transition-colors"
              >
                {t.open_supabase}
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </Section>
        )}

        {/* About — admin only (exposes tech stack) */}
        {isAdmin && (
          <Section title={t.section_about}>
            <div className="space-y-2 text-sm text-gray-500">
              <p>Maya AI Platform — v1.0.0</p>
              <p>Next.js · TypeScript · Supabase · Tailwind CSS</p>
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

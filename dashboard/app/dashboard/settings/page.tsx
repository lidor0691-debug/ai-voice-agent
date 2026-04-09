"use client";

import { useState } from "react";
import { Check, ExternalLink } from "lucide-react";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-2 border border-border rounded-xl p-6">
      <h2 className="text-white font-medium text-sm mb-5">{title}</h2>
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

export default function SettingsPage() {
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">Settings</h1>
          <p className="text-gray-500 text-sm mt-0.5">Platform configuration</p>
        </div>
        <button
          onClick={handleSave}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {saved ? <Check className="w-4 h-4" /> : null}
          {saved ? "Saved!" : "Save Changes"}
        </button>
      </div>

      <div className="p-8 max-w-2xl space-y-6">
        <Section title="Platform">
          <div className="space-y-4">
            <Field label="Workspace Name">
              <input
                defaultValue="My Workspace"
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 transition-colors"
              />
            </Field>
            <Field label="Default Language">
              <select className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600 transition-colors">
                <option value="en" className="bg-surface-3">English</option>
                <option value="he" className="bg-surface-3">Hebrew</option>
                <option value="es" className="bg-surface-3">Spanish</option>
              </select>
            </Field>
          </div>
        </Section>

        <Section title="Integrations">
          <div className="space-y-4">
            <Field
              label="Supabase URL"
              hint="Set via NEXT_PUBLIC_SUPABASE_URL in .env.local"
            >
              <div className="w-full bg-surface-3/50 border border-border rounded-lg px-3 py-2 text-sm text-gray-500 font-mono truncate">
                (configured via environment variable)
              </div>
            </Field>

            <Field
              label="FastAPI Backend URL"
              hint="Used for the Test Agent feature"
            >
              <input
                defaultValue="http://localhost:8000"
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 transition-colors"
              />
            </Field>
          </div>
        </Section>

        <Section title="Database Schema">
          <div className="space-y-3">
            <p className="text-gray-500 text-sm">
              Run the schema migration in your Supabase SQL editor to create the required tables.
            </p>
            <div className="bg-surface-3 rounded-lg p-3">
              <p className="text-gray-400 text-xs font-mono">
                Schema file: <span className="text-gray-200">dashboard/supabase/schema.sql</span>
              </p>
            </div>
            <a
              href="https://supabase.com/dashboard"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-brand-400 hover:text-brand-300 text-sm transition-colors"
            >
              Open Supabase Dashboard
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </Section>

        <Section title="About">
          <div className="space-y-2 text-sm text-gray-500">
            <p>Maya AI Platform — v1.0.0</p>
            <p>Next.js · TypeScript · Supabase · Tailwind CSS</p>
          </div>
        </Section>
      </div>
    </div>
  );
}

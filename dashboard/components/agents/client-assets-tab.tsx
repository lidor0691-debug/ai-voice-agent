"use client";

import { useState, useEffect, useCallback } from "react";
import { ClientAsset } from "@/types/database";
import { useLanguage } from "@/context/language-context";

const ASSET_TYPE_COLORS: Record<ClientAsset["asset_type"], string> = {
  text:  "bg-blue-500/20 text-blue-300",
  link:  "bg-purple-500/20 text-purple-300",
  pdf:   "bg-red-500/20 text-red-300",
  image: "bg-green-500/20 text-green-300",
  video: "bg-orange-500/20 text-orange-300",
};

const PRESET_TRIGGERS = [
  "trial_booked",
  "payment_request",
  "general_followup",
  "lead_qualified",
];

const EMPTY_FORM = {
  asset_name:  "",
  asset_type:  "text" as ClientAsset["asset_type"],
  trigger_key: "",
  content:     "",
  enabled:     true,
};

interface Props {
  clientId: string;
}

export function ClientAssetsTab({ clientId }: Props) {
  const { t } = useLanguage();
  const [assets, setAssets]       = useState<ClientAsset[]>([]);
  const [loading, setLoading]     = useState(true);
  const [showForm, setShowForm]   = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [form, setForm]           = useState(EMPTY_FORM);
  const [customTrigger, setCustomTrigger] = useState(false);

  const ASSET_TYPE_LABELS: Record<ClientAsset["asset_type"], string> = {
    text:  t.ca_type_text,
    link:  t.ca_type_link,
    pdf:   t.ca_type_pdf,
    image: t.ca_type_image,
    video: t.ca_type_video,
  };

  const fetchAssets = useCallback(async () => {
    if (!clientId) { setLoading(false); return; }
    setLoading(true);
    try {
      const res = await fetch(`/api/clients/${clientId}/assets`);
      const data = await res.json();
      setAssets(Array.isArray(data) ? data : []);
    } catch {
      setAssets([]);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const toggleEnabled = async (asset: ClientAsset) => {
    await fetch(`/api/clients/${clientId}/assets/${asset.id}`, {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ enabled: !asset.enabled }),
    });
    setAssets((prev) =>
      prev.map((a) => a.id === asset.id ? { ...a, enabled: !a.enabled } : a)
    );
  };

  const deleteAsset = async (asset: ClientAsset) => {
    if (!confirm(t.ca_delete_confirm(asset.asset_name))) return;
    await fetch(`/api/clients/${clientId}/assets/${asset.id}`, { method: "DELETE" });
    setAssets((prev) => prev.filter((a) => a.id !== asset.id));
  };

  const handleSubmit = async () => {
    if (!form.asset_name.trim()) { setError(t.ca_name_required); return; }
    if (!form.trigger_key.trim()) { setError(t.ca_trigger_required); return; }
    if (!form.content.trim()) { setError(t.ca_content_required); return; }

    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/clients/${clientId}/assets`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(form),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.error ?? t.ca_save_failed);
      }
      const created = await res.json();
      setAssets((prev) => [...prev, created]);
      setForm(EMPTY_FORM);
      setShowForm(false);
      setCustomTrigger(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t.ca_save_failed);
    } finally {
      setSaving(false);
    }
  };

  if (!clientId) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-500 text-sm">{t.ca_agents_only}</p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-2xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-white font-semibold text-base">{t.ca_title}</h2>
          <p className="text-gray-500 text-sm mt-0.5">
            {t.ca_subtitle}
          </p>
        </div>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {t.ca_add_btn}
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Add asset form */}
      {showForm && (
        <div className="bg-surface-2 border border-border rounded-xl p-5 mb-6 space-y-4">
          <h3 className="text-white font-medium text-sm">{t.ca_new_title}</h3>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">{t.ca_name_label}</label>
              <input
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                placeholder={t.ca_name_placeholder}
                value={form.asset_name}
                onChange={(e) => setForm((f) => ({ ...f, asset_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">{t.ca_type_label}</label>
              <select
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600"
                value={form.asset_type}
                onChange={(e) => setForm((f) => ({ ...f, asset_type: e.target.value as ClientAsset["asset_type"] }))}
              >
                <option value="text">{t.ca_type_text}</option>
                <option value="link">{t.ca_type_link}</option>
                <option value="pdf">{t.ca_type_pdf}</option>
                <option value="image">{t.ca_type_image}</option>
                <option value="video">{t.ca_type_video}</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">{t.ca_trigger_label}</label>
            {!customTrigger ? (
              <select
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600"
                value={form.trigger_key}
                onChange={(e) => {
                  if (e.target.value === "__custom__") {
                    setCustomTrigger(true);
                    setForm((f) => ({ ...f, trigger_key: "" }));
                  } else {
                    setForm((f) => ({ ...f, trigger_key: e.target.value }));
                  }
                }}
              >
                <option value="">{t.ca_trigger_placeholder}</option>
                {PRESET_TRIGGERS.map((trigger) => (
                  <option key={trigger} value={trigger}>{trigger}</option>
                ))}
                <option value="__custom__">אחר (הזן ידנית)</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input
                  className="flex-1 bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                  placeholder="trial_booked"
                  value={form.trigger_key}
                  onChange={(e) => setForm((f) => ({ ...f, trigger_key: e.target.value.toLowerCase().replace(/\s+/g, "_") }))}
                />
                <button
                  onClick={() => { setCustomTrigger(false); setForm((f) => ({ ...f, trigger_key: "" })); }}
                  className="px-3 py-2 text-xs text-gray-400 border border-border rounded-lg hover:text-white"
                >
                  חזור
                </button>
              </div>
            )}
            <p className="text-xs text-gray-600 mt-1">
              {t.ca_trigger_hint}
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">
              {form.asset_type === "text" ? t.ca_content_label : t.ca_url_label}
            </label>
            <textarea
              rows={3}
              className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
              placeholder={form.asset_type === "text"
                ? 'היי {{name}}! האימון הראשון שלך אושר.'
                : "https://example.com/file.pdf"}
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            />
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">{t.ca_active_label}</span>
            <div
              onClick={() => setForm((f) => ({ ...f, enabled: !f.enabled }))}
              className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${form.enabled ? "bg-brand-600" : "bg-surface-4"}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {saving ? t.ca_saving : t.ca_save_btn}
            </button>
            <button
              onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setError(null); setCustomTrigger(false); }}
              className="px-4 py-2 text-sm text-gray-400 border border-border rounded-lg hover:text-white hover:bg-surface-3 transition-colors"
            >
              {t.ca_cancel}
            </button>
          </div>
        </div>
      )}

      {/* Asset list */}
      {loading ? (
        <p className="text-gray-600 text-sm text-center py-8">{t.ca_loading}</p>
      ) : assets.length === 0 && !showForm ? (
        /* Empty state */
        <div className="text-center py-12 border border-dashed border-border rounded-xl">
          <p className="text-gray-500 text-sm leading-relaxed">
            {t.ca_empty_title}<br />
            {t.ca_empty_desc}
          </p>
          <button
            onClick={() => setShowForm(true)}
            className="mt-4 px-5 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {t.ca_add_first_btn}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {assets.map((asset) => (
            <div
              key={asset.id}
              className="bg-surface-2 border border-border rounded-lg px-4 py-3 flex items-center gap-3"
            >
              {/* Type badge */}
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${ASSET_TYPE_COLORS[asset.asset_type]}`}>
                {ASSET_TYPE_LABELS[asset.asset_type]}
              </span>

              {/* Name + trigger */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white font-medium truncate">{asset.asset_name}</p>
                <p className="text-xs text-gray-500 mt-0.5 font-mono">{asset.trigger_key}</p>
              </div>

              {/* Enabled toggle */}
              <div
                onClick={() => toggleEnabled(asset)}
                className={`relative shrink-0 w-10 h-5 rounded-full transition-colors cursor-pointer ${asset.enabled ? "bg-brand-600" : "bg-surface-4"}`}
              >
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${asset.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
              </div>

              {/* Delete */}
              <button
                onClick={() => deleteAsset(asset)}
                className="text-gray-600 hover:text-red-400 transition-colors text-xs px-2 py-1 shrink-0"
              >
                {t.ca_delete_btn}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

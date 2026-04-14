"use client";

import { useState } from "react";
import { Plus, Pencil, Trash2, X, Check } from "lucide-react";
import { KnowledgeItem } from "@/types/database";
import { useLanguage } from "@/context/language-context";

interface AgentRef {
  id: string;
  agent_name: string;
}

interface Props {
  agents: AgentRef[];
  initialItems: KnowledgeItem[];
}

type FormState = {
  agent_id: string;
  category: string;
  title: string;
  content: string;
  priority: number;
  is_active: boolean;
};

const EMPTY_FORM: FormState = {
  agent_id: "",
  category: "",
  title: "",
  content: "",
  priority: 5,
  is_active: true,
};

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors"
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
      <option value="" className="bg-surface-3">
        — select —
      </option>
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-surface-3">
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function KnowledgeClient({ agents, initialItems }: Props) {
  const [items, setItems] = useState<KnowledgeItem[]>(initialItems);
  const [filterAgent, setFilterAgent] = useState<string>("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useLanguage();

  const set = (k: keyof FormState, v: unknown) =>
    setForm((p) => ({ ...p, [k]: v }));

  const filtered = filterAgent
    ? items.filter((i) => i.agent_id === filterAgent)
    : items;

  const agentName = (id: string) =>
    agents.find((a) => a.id === id)?.agent_name ?? id.slice(0, 8);

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, agent_id: filterAgent || agents[0]?.id || "" });
    setEditingId(null);
    setShowForm(true);
    setError(null);
  };

  const openEdit = (item: KnowledgeItem) => {
    setForm({
      agent_id: item.agent_id,
      category: item.category ?? "",
      title: item.title,
      content: item.content,
      priority: item.priority ?? 5,
      is_active: item.is_active,
    });
    setEditingId(item.id);
    setShowForm(true);
    setError(null);
  };

  const handleSave = async () => {
    if (!form.agent_id || !form.title.trim() || !form.content.trim()) {
      setError(t.required_fields_error);
      return;
    }
    setSaving(true);
    setError(null);

    try {
      if (editingId) {
        const res = await fetch(`/api/knowledge/${editingId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error((await res.json()).error);
        const updated: KnowledgeItem = await res.json();
        setItems((prev) => prev.map((i) => (i.id === editingId ? updated : i)));
      } else {
        const res = await fetch("/api/knowledge", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error((await res.json()).error);
        const created: KnowledgeItem = await res.json();
        setItems((prev) => [created, ...prev]);
      }
      setShowForm(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t.delete_knowledge_confirm)) return;
    const res = await fetch(`/api/knowledge/${id}`, { method: "DELETE" });
    if (res.ok) setItems((prev) => prev.filter((i) => i.id !== id));
  };

  const handleToggle = async (item: KnowledgeItem) => {
    const res = await fetch(`/api/knowledge/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !item.is_active }),
    });
    if (res.ok) {
      const updated: KnowledgeItem = await res.json();
      setItems((prev) => prev.map((i) => (i.id === item.id ? updated : i)));
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">{t.page_knowledge_title}</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {filtered.length} {filtered.length !== 1 ? t.knowledge_item_plural : t.knowledge_item_singular}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-600"
          >
            <option value="">{t.all_agents_option}</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.agent_name}
              </option>
            ))}
          </select>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t.add_item_btn}
          </button>
        </div>
      </div>

      <div className="p-8">
        {/* Inline form */}
        {showForm && (
          <div className="bg-surface-2 border border-brand-600/30 rounded-xl p-6 mb-6 space-y-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-white font-medium text-sm">
                {editingId ? t.edit_item_title : t.new_item_title}
              </h2>
              <button onClick={() => setShowForm(false)}>
                <X className="w-4 h-4 text-gray-500 hover:text-white" />
              </button>
            </div>

            {error && (
              <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 px-3 py-2 rounded-lg">
                {error}
              </p>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">{t.field_agent}</label>
                <Select
                  value={form.agent_id}
                  onChange={(e) => set("agent_id", e.target.value)}
                  options={agents.map((a) => ({ value: a.id, label: a.agent_name }))}
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">{t.field_category}</label>
                <Input
                  placeholder={t.category_placeholder}
                  value={form.category}
                  onChange={(e) => set("category", e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">{t.field_title}</label>
              <Input
                placeholder={t.title_placeholder}
                value={form.title}
                onChange={(e) => set("title", e.target.value)}
              />
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">{t.field_content}</label>
              <textarea
                rows={4}
                placeholder={t.content_placeholder}
                value={form.content}
                onChange={(e) => set("content", e.target.value)}
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none transition-colors"
              />
            </div>

            <div className="grid grid-cols-2 gap-4 items-end">
              <div>
                <label className="text-xs text-gray-400 block mb-1">
                  {t.field_priority}
                </label>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={form.priority}
                  onChange={(e) => set("priority", parseInt(e.target.value))}
                />
              </div>
              <label className="flex items-center gap-2 cursor-pointer pb-2">
                <div
                  onClick={() => set("is_active", !form.is_active)}
                  className={`relative w-9 h-5 rounded-full transition-colors cursor-pointer ${
                    form.is_active ? "bg-brand-600" : "bg-surface-4"
                  }`}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      form.is_active ? "translate-x-4" : "translate-x-0.5"
                    }`}
                  />
                </div>
                <span className="text-sm text-gray-300">{t.field_active}</span>
              </label>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                <Check className="w-3.5 h-3.5" />
                {saving ? t.saving : t.save}
              </button>
              <button
                onClick={() => setShowForm(false)}
                className="text-gray-400 hover:text-white text-sm px-4 py-2 rounded-lg border border-border hover:bg-surface-3 transition-colors"
              >
                {t.cancel}
              </button>
            </div>
          </div>
        )}

        {/* Empty state */}
        {filtered.length === 0 && !showForm && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <p className="text-white font-medium">{t.no_knowledge_title}</p>
            <p className="text-gray-500 text-sm mt-1 mb-6">
              {t.no_knowledge_desc}
            </p>
            <button
              onClick={openCreate}
              className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {t.add_first_item_btn}
            </button>
          </div>
        )}

        {/* Table */}
        {filtered.length > 0 && (
          <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-xs text-gray-500 font-medium px-5 py-3">{t.col_title}</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">{t.col_agent}</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">{t.field_category}</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">{t.col_priority}</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">{t.col_status}</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-border last:border-0 hover:bg-surface-3 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <p className="text-white text-sm font-medium">{item.title}</p>
                      <p className="text-gray-500 text-xs mt-0.5 line-clamp-1 max-w-xs">
                        {item.content}
                      </p>
                    </td>
                    <td className="px-4 py-3.5 text-gray-400 text-sm">
                      {agentName(item.agent_id)}
                    </td>
                    <td className="px-4 py-3.5">
                      {item.category ? (
                        <span className="bg-surface-4 text-gray-300 text-xs px-2 py-0.5 rounded-full">
                          {item.category}
                        </span>
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-gray-400 text-sm">{item.priority ?? "—"}</td>
                    <td className="px-4 py-3.5">
                      <button onClick={() => handleToggle(item)}>
                        <span
                          className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full cursor-pointer ${
                            item.is_active
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "bg-gray-500/10 text-gray-500"
                          }`}
                        >
                          {item.is_active ? t.status_active_badge : t.status_inactive_badge}
                        </span>
                      </button>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2 justify-end">
                        <button
                          onClick={() => openEdit(item)}
                          className="text-gray-500 hover:text-white transition-colors p-1"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="text-gray-500 hover:text-red-400 transition-colors p-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Pencil, X, ShieldCheck, User, ShieldOff } from "lucide-react";

type UserRow = {
  id: string;
  email: string;
  role: string | null;
  client_id: string | null;
  created_at: string;
  last_sign_in_at: string | null;
  banned: boolean;
};

type ClientRow = { id: string; name: string };

interface Props {
  users: UserRow[];
  clients: ClientRow[];
}

type ModalMode = "create" | "edit" | null;

const EMPTY_FORM = {
  email: "",
  password: "",
  role: "client" as "admin" | "client",
  client_id: "",
};

export function UsersClient({ users, clients }: Props) {
  const router = useRouter();
  const [modal, setModal] = useState<ModalMode>(null);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditing(null);
    setError(null);
    setModal("create");
  };

  const openEdit = (u: UserRow) => {
    setForm({
      email: u.email,
      password: "",
      role: u.role === "admin" ? "admin" : "client",
      client_id: u.client_id ?? "",
    });
    setEditing(u);
    setError(null);
    setModal("edit");
  };

  const closeModal = () => { setModal(null); setEditing(null); setError(null); };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (modal === "create") {
        const res = await fetch("/api/admin/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: form.email,
            password: form.password,
            role: form.role === "admin" ? "admin" : undefined,
            client_id: form.role === "client" ? form.client_id : undefined,
          }),
        });
        if (!res.ok) throw new Error((await res.json()).error);
      } else if (modal === "edit" && editing) {
        const res = await fetch(`/api/admin/users/${editing.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            role: form.role === "admin" ? "admin" : undefined,
            client_id: form.role === "client" ? form.client_id : undefined,
            password: form.password || undefined,
          }),
        });
        if (!res.ok) throw new Error((await res.json()).error);
      }
      closeModal();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleDisabled = async (u: UserRow) => {
    const action = u.banned ? "enable" : "disable";
    if (!confirm(`${action === "disable" ? "Disable" : "Re-enable"} ${u.email}?`)) return;
    setToggling(u.id);
    await fetch(`/api/admin/users/${u.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disabled: !u.banned }),
    });
    setToggling(null);
    router.refresh();
  };

  const clientName = (id: string | null) =>
    clients.find((c) => c.id === id)?.name ?? id?.slice(0, 8) ?? "—";

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-white font-semibold text-lg">Users</h2>
          <p className="text-gray-500 text-sm mt-0.5">{users.length} total</p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New User
        </button>
      </div>

      <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-gray-400 font-medium px-5 py-3">Email</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Role</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Client</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Last login</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={`border-b border-border/50 last:border-0 hover:bg-surface-3/30 transition-colors ${u.banned ? "opacity-60" : ""}`}>
                <td className="px-5 py-3 text-white">
                  <span>{u.email}</span>
                  {u.banned && (
                    <span className="ml-2 text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/20 px-1.5 py-0.5 rounded-full align-middle">disabled</span>
                  )}
                </td>
                <td className="px-5 py-3">
                  {u.role === "admin" ? (
                    <span className="inline-flex items-center gap-1 text-xs bg-brand-600/15 text-brand-400 border border-brand-600/20 px-2 py-0.5 rounded-full">
                      <ShieldCheck className="w-3 h-3" /> Admin
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs bg-gray-500/10 text-gray-400 border border-gray-500/20 px-2 py-0.5 rounded-full">
                      <User className="w-3 h-3" /> Client
                    </span>
                  )}
                </td>
                <td className="px-5 py-3 text-gray-400 text-xs">
                  {u.client_id ? clientName(u.client_id) : "—"}
                </td>
                <td className="px-5 py-3 text-gray-600 text-xs">
                  {u.last_sign_in_at
                    ? new Date(u.last_sign_in_at).toLocaleDateString("he-IL")
                    : "Never"}
                </td>
                <td className="px-5 py-3 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => openEdit(u)}
                      className="p-1.5 text-gray-500 hover:text-white hover:bg-surface-3 rounded-lg transition-colors"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleToggleDisabled(u)}
                      disabled={toggling === u.id}
                      title={u.banned ? "Enable user" : "Disable user"}
                      className={`p-1.5 rounded-lg transition-colors disabled:opacity-40 ${
                        u.banned
                          ? "text-amber-500 hover:text-emerald-400 hover:bg-emerald-500/10"
                          : "text-gray-500 hover:text-amber-400 hover:bg-amber-500/10"
                      }`}
                    >
                      <ShieldOff className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-surface-1 border border-border rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-white font-semibold">
                {modal === "create" ? "New User" : "Edit User"}
              </h3>
              <button onClick={closeModal} className="text-gray-500 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              {modal === "create" && (
                <div>
                  <label className="block text-sm text-gray-400 mb-1.5">Email</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                    placeholder="user@example.com"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm text-gray-400 mb-1.5">
                  {modal === "create" ? "Password" : "New Password (leave blank to keep)"}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                  placeholder="••••••••"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Role</label>
                <div className="flex gap-3">
                  {(["client", "admin"] as const).map((r) => (
                    <button
                      key={r}
                      onClick={() => setForm({ ...form, role: r })}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                        form.role === r
                          ? "bg-brand-600 border-brand-600 text-white"
                          : "bg-surface-3 border-border text-gray-400 hover:text-white"
                      }`}
                    >
                      {r === "admin" ? "Admin" : "Client"}
                    </button>
                  ))}
                </div>
              </div>

              {form.role === "client" && (
                <div>
                  <label className="block text-sm text-gray-400 mb-1.5">Client</label>
                  <select
                    value={form.client_id}
                    onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                    className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600"
                  >
                    <option value="">— Select client —</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {error && (
                <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 px-3 py-2 rounded-lg">
                  {error}
                </p>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={closeModal}
                className="flex-1 py-2.5 rounded-lg border border-border text-gray-400 hover:text-white text-sm transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {saving ? "Saving…" : modal === "create" ? "Create" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

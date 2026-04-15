export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";

type AuditRow = {
  id: string;
  table_name: string;
  record_id: string;
  action: string;
  changed_by: string | null;
  old_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  created_at: string;
};

const ACTION_STYLE: Record<string, string> = {
  INSERT: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  UPDATE: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  DELETE: "bg-red-500/10 text-red-400 border border-red-500/20",
};

function diffSummary(
  old_data: Record<string, unknown> | null,
  new_data: Record<string, unknown> | null
): string {
  if (!old_data || !new_data) return "";
  const SKIP = new Set(["updated_at", "created_at"]);
  const changed: string[] = [];
  for (const key of Object.keys(new_data)) {
    if (SKIP.has(key)) continue;
    if (JSON.stringify(old_data[key]) !== JSON.stringify(new_data[key])) {
      changed.push(key);
    }
  }
  return changed.length > 0 ? changed.join(", ") : "—";
}

export default async function AuditPage() {
  const client = await createSupabaseServerClient();
  const { data, error } = await client
    .from("audit_logs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(200);

  const rows = (data ?? []) as AuditRow[];

  return (
    <div className="space-y-4 max-w-6xl">
      <div>
        <h2 className="text-white font-semibold text-lg">Audit Log</h2>
        <p className="text-gray-500 text-sm mt-0.5">Last {rows.length} events across all tables</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg">
          {error.message}
        </div>
      )}

      <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-gray-400 font-medium px-5 py-3">Time</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Table</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Action</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Record</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">Changed fields</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">By</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-border/50 last:border-0 hover:bg-surface-3/30 transition-colors">
                <td className="px-5 py-3 text-gray-500 text-xs font-mono whitespace-nowrap">
                  {new Date(row.created_at).toLocaleString("he-IL")}
                </td>
                <td className="px-5 py-3 text-gray-400 font-mono text-xs">{row.table_name}</td>
                <td className="px-5 py-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${ACTION_STYLE[row.action] ?? "text-gray-400"}`}>
                    {row.action}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-500 font-mono text-xs">
                  {row.record_id.slice(0, 8)}…
                </td>
                <td className="px-5 py-3 text-gray-400 text-xs max-w-xs truncate">
                  {row.action === "UPDATE"
                    ? diffSummary(row.old_data, row.new_data)
                    : row.action === "INSERT"
                    ? (row.new_data?.["agent_name"] as string | undefined) ?? (row.new_data?.["phone"] as string | undefined) ?? "—"
                    : row.action === "DELETE"
                    ? (row.old_data?.["agent_name"] as string | undefined) ?? "—"
                    : "—"}
                </td>
                <td className="px-5 py-3 text-gray-600 font-mono text-xs">
                  {row.changed_by ? row.changed_by.slice(0, 8) + "…" : "system"}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-12 text-center text-gray-600">
                  No audit events yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

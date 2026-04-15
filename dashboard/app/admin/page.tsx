export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { RestoreAgentButton } from "@/components/admin/restore-agent-button";

type ClientRow = { id: string; name: string; created_at: string };
type AgentRow = { client_id: string };
type LeadRow = { client_id: string; created_at: string };
type ArchivedAgent = { id: string; agent_name: string; phone_number: string | null; client_id: string | null };

export default async function AdminPage() {
  const client = await createSupabaseServerClient();

  const [clientsRes, agentsRes, leadsRes, archivedRes] = await Promise.all([
    client.from("clients").select("id, name, created_at").order("created_at", { ascending: false }),
    client.from("agents_config").select("client_id").eq("is_active", true),
    client.from("leads").select("client_id, created_at").order("created_at", { ascending: false }),
    client.from("agents_config").select("id, agent_name, phone_number, client_id").eq("is_active", false).order("created_at", { ascending: false }),
  ]);

  const clients = (clientsRes.data ?? []) as ClientRow[];
  const agents = (agentsRes.data ?? []) as AgentRow[];
  const leads = (leadsRes.data ?? []) as LeadRow[];
  const archivedAgents = (archivedRes.data ?? []) as ArchivedAgent[];

  const stats = clients.map((client) => {
    const agentCount = agents.filter((a) => a.client_id === client.id).length;
    const clientLeads = leads.filter((l) => l.client_id === client.id);
    const lastLead = clientLeads[0]?.created_at;
    return { ...client, agentCount, leadCount: clientLeads.length, lastLead };
  });

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-white font-semibold text-lg">Clients</h2>
        <p className="text-gray-500 text-sm mt-0.5">{clients.length} total</p>
      </div>

      <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-gray-400 font-medium px-5 py-3">Client</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">ID</th>
              <th className="text-right text-gray-400 font-medium px-5 py-3">Agents</th>
              <th className="text-right text-gray-400 font-medium px-5 py-3">Leads</th>
              <th className="text-right text-gray-400 font-medium px-5 py-3">Last Lead</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((c) => (
              <tr key={c.id} className="border-b border-border/50 last:border-0">
                <td className="px-5 py-3 text-white font-medium">{c.name}</td>
                <td className="px-5 py-3 text-gray-500 font-mono text-xs">{c.id}</td>
                <td className="px-5 py-3 text-right text-gray-300">{c.agentCount}</td>
                <td className="px-5 py-3 text-right text-gray-300">{c.leadCount}</td>
                <td className="px-5 py-3 text-right text-gray-500 text-xs">
                  {c.lastLead ? new Date(c.lastLead).toLocaleDateString("he-IL") : "—"}
                </td>
              </tr>
            ))}
            {stats.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-gray-600">
                  No clients yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {archivedAgents.length > 0 && (
        <div>
          <h2 className="text-white font-semibold text-lg mb-3">Archived Agents</h2>
          <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-gray-400 font-medium px-5 py-3">Agent</th>
                  <th className="text-left text-gray-400 font-medium px-5 py-3">Phone</th>
                  <th className="text-left text-gray-400 font-medium px-5 py-3">Client ID</th>
                  <th className="px-5 py-3" />
                </tr>
              </thead>
              <tbody>
                {archivedAgents.map((a) => (
                  <tr key={a.id} className="border-b border-border/50 last:border-0">
                    <td className="px-5 py-3 text-gray-400">{a.agent_name}</td>
                    <td className="px-5 py-3 text-gray-500 font-mono text-xs">{a.phone_number ?? "—"}</td>
                    <td className="px-5 py-3 text-gray-500 font-mono text-xs">{a.client_id ?? "—"}</td>
                    <td className="px-5 py-3 text-right">
                      <RestoreAgentButton agentId={a.id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-3">
        <h3 className="text-white font-medium text-sm">Reset demo data</h3>
        <p className="text-gray-500 text-xs">
          Run in Supabase SQL Editor. Copy the client ID from the table above.
        </p>
        <pre className="bg-surface-3 rounded-lg p-4 text-xs text-gray-400 font-mono whitespace-pre overflow-x-auto">{
`-- Delete leads for a client
DELETE FROM leads WHERE client_id = '<CLIENT_ID>';

-- Delete call logs for a client's agents
DELETE FROM call_logs
WHERE agent_id IN (
  SELECT id FROM agents_config WHERE client_id = '<CLIENT_ID>'
);`
        }</pre>
      </div>
    </div>
  );
}

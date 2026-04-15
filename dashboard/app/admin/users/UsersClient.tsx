"use client";

interface User {
  id: string;
  email: string;
  role: string | null;
  client_id: string | null;
  created_at: string;
  last_sign_in_at: string | null;
}

interface Client {
  id: string;
  name: string;
}

interface Props {
  users: User[];
  clients: Client[];
}

export function UsersClient({ users, clients }: Props) {
  return (
    <div className="space-y-4">
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-[11px] text-gray-600 font-medium px-5 py-3">Email</th>
              <th className="text-left text-[11px] text-gray-600 font-medium px-5 py-3">Role</th>
              <th className="text-left text-[11px] text-gray-600 font-medium px-5 py-3">Client</th>
              <th className="text-left text-[11px] text-gray-600 font-medium px-5 py-3">Last Sign In</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const clientName = clients.find((c) => c.id === u.client_id)?.name ?? u.client_id ?? "—";
              return (
                <tr key={u.id} className="border-b border-border last:border-0 hover:bg-surface-2 transition-colors">
                  <td className="px-5 py-3.5 text-gray-300 text-[13px]">{u.email}</td>
                  <td className="px-5 py-3.5 text-gray-500 text-[13px]">{u.role ?? "—"}</td>
                  <td className="px-5 py-3.5 text-gray-500 text-[13px]">{clientName}</td>
                  <td className="px-5 py-3.5 text-gray-600 text-[11px]">
                    {u.last_sign_in_at ? new Date(u.last_sign_in_at).toLocaleDateString("he-IL") : "—"}
                  </td>
                </tr>
              );
            })}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-gray-600 text-sm">No users yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

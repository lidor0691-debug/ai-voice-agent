import type { Lead } from "@/types/lead";

const BACKEND_URL =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export interface LeadsResponse {
  leads: Lead[];
  total: number;
}

/**
 * Fetch all leads directly from the FastAPI backend.
 * Called from server components — never runs in the browser.
 *
 * Includes a 5-second timeout so the build/SSR does not hang when
 * the backend is not running. On timeout or any error, the caller
 * should fall back to mock data.
 */
export async function fetchLeads(): Promise<Lead[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);

  try {
    const res = await fetch(`${BACKEND_URL}/leads`, {
      next: { revalidate: 60 },
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`Backend responded with ${res.status} ${res.statusText}`);
    }

    const data: LeadsResponse = await res.json();
    return data.leads ?? [];
  } finally {
    clearTimeout(timer);
  }
}

import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.API_BASE_URL || "http://localhost:8000";

/**
 * GET /api/leads
 * Proxies the FastAPI /leads endpoint.
 * Used by client components that need to fetch leads from the browser.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const params = new URLSearchParams();
  if (searchParams.get("status")) params.set("status", searchParams.get("status")!);
  if (searchParams.get("intent")) params.set("intent", searchParams.get("intent")!);

  const query = params.toString() ? `?${params}` : "";

  try {
    const res = await fetch(`${BACKEND_URL}/leads${query}`, {
      next: { revalidate: 60 },
    });

    if (!res.ok) {
      throw new Error(`Backend responded with ${res.status}`);
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error("[/api/leads] Backend unavailable:", err);
    return NextResponse.json(
      { error: "Backend unavailable", leads: [], total: 0 },
      { status: 503 }
    );
  }
}

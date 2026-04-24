import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const backendUrl = process.env.API_BASE_URL;

  if (!backendUrl && process.env.NODE_ENV === "production") {
    return NextResponse.json(
      { status: "failed", error: "API_BASE_URL is not configured" },
      { status: 503 },
    );
  }

  const resolvedUrl = backendUrl ?? "http://localhost:8000";

  try {
    const res = await fetch(`${resolvedUrl}/api/actions/send-whatsapp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { status: "failed", error: "Failed to reach backend" },
      { status: 502 },
    );
  }
}

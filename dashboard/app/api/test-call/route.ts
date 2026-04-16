import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const backendUrl = process.env.API_BASE_URL;

  if (!backendUrl && process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "API_BASE_URL is not configured on this server" }, { status: 503 });
  }

  const resolvedUrl = backendUrl ?? "http://localhost:8000";

  try {
    const res = await fetch(`${resolvedUrl}/test-call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });

    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Failed to initiate test call" }, { status: 500 });
  }
}

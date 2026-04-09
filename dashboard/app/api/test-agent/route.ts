import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { agent_id, messages, system_prompt } = await req.json();

  const backendUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${backendUrl}/api/test-agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id, messages, system_prompt }),
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Backend returned an error" },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Could not connect to backend" },
      { status: 502 }
    );
  }
}

import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const backendUrl = process.env.API_BASE_URL;
  if (!backendUrl && process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "API_BASE_URL is not configured on this server" }, { status: 503 });
  }
  const resolvedUrl = backendUrl ?? "http://localhost:8000";

  try {
    const res = await fetch(`${resolvedUrl}/voice-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20000),
    });

    if (!res.ok) {
      return NextResponse.json({ error: "TTS generation failed" }, { status: 502 });
    }

    const audioBuffer = await res.arrayBuffer();
    return new NextResponse(audioBuffer, {
      status: 200,
      headers: { "Content-Type": "audio/mpeg", "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}

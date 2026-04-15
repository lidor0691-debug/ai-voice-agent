import type { Lead } from "@/types/lead";

const BACKEND_URL =
  process.env.API_BASE_URL ||
  "http://localhost:8000";

const SHEETS_CSV_URL = process.env.GOOGLE_SHEETS_CSV_URL || "";

export interface LeadsResponse {
  leads: Lead[];
  total: number;
}

// ---------------------------------------------------------------------------
// CSV parser — no external dependency needed
// ---------------------------------------------------------------------------

/** Parse a single CSV line respecting quoted fields. */
function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        field += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      fields.push(field.trim());
      field = "";
    } else {
      field += ch;
    }
  }
  fields.push(field.trim());
  return fields;
}

/** Normalise an ISO-ish datetime string so new Date() parses it correctly. */
function normaliseDateTime(raw: string): string {
  if (!raw) return "";
  // Replace space separator with T so "2026-03-08 11:00:00" → ISO
  return raw.replace(" ", "T");
}

/** Convert a CSV text (exported from Google Sheets) to Lead[]. */
function csvToLeads(csv: string): Lead[] {
  const lines = csv.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];

  const headers = parseCsvLine(lines[0]).map((h) => h.toLowerCase().trim());

  const col = (row: string[], name: string): string => {
    const idx = headers.indexOf(name);
    return idx >= 0 ? (row[idx] ?? "").trim() : "";
  };

  const toBool = (v: string) =>
    v === "true" || v === "1" || v === "כן" || v === "yes";

  return lines.slice(1).map((line, i) => {
    const row = parseCsvLine(line);

    // intents: prefer "intents" column (pipe-separated); fall back to "intent"
    const intentsRaw = col(row, "intents") || col(row, "intent");
    const intents = intentsRaw
      ? intentsRaw.split("|").map((v) => v.trim()).filter(Boolean)
      : [];

    const apptRaw = col(row, "appointment_time");
    const createdRaw = col(row, "created_at");

    return {
      id: col(row, "id") || String(i + 1),
      name: col(row, "name"),
      phone: col(row, "phone"),
      model: col(row, "model"),
      intents,
      mileage: col(row, "mileage"),
      appointment_time: apptRaw ? normaliseDateTime(apptRaw) : null,
      created_at: normaliseDateTime(createdRaw) || new Date().toISOString(),
      status: col(row, "status") || "ליד חדש",
      source: col(row, "source") || "phone_call",
      sms_sent: toBool(col(row, "sms_sent")),
      calendar_booked: toBool(col(row, "calendar_booked")),
    } satisfies Lead;
  }).filter((l) => l.name); // drop empty rows
}

// ---------------------------------------------------------------------------
// Google Sheets — primary data source
// ---------------------------------------------------------------------------

/**
 * Fetch leads from a published Google Sheets CSV export URL.
 * Set GOOGLE_SHEETS_CSV_URL in .env.local:
 *   https://docs.google.com/spreadsheets/d/<ID>/export?format=csv
 *
 * Throws if the URL is not configured or the fetch fails.
 */
export async function fetchLeadsFromSheets(): Promise<Lead[]> {
  if (!SHEETS_CSV_URL) throw new Error("GOOGLE_SHEETS_CSV_URL not configured");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);

  try {
    const res = await fetch(SHEETS_CSV_URL, {
      next: { revalidate: 60 },
      signal: controller.signal,
      headers: { Accept: "text/csv" },
    });

    if (!res.ok) {
      throw new Error(`Google Sheets responded with ${res.status} ${res.statusText}`);
    }

    const text = await res.text();
    return csvToLeads(text);
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// FastAPI backend — secondary data source
// ---------------------------------------------------------------------------

/**
 * Fetch all leads directly from the FastAPI backend.
 * Called from server components — never runs in the browser.
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

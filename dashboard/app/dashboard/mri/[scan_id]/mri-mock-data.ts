// Mock MRI dataset — used while the route is decoupled from the backend.
// Numbers chosen to match the spec brief verbatim. No live API calls.

export type Severity = "low" | "moderate" | "high" | "critical";

export interface MriLeak {
  key: "acceptance" | "booking" | "showup" | "completion";
  label: string;
  amount: number;
}

export interface MriDimension {
  key: "qualification" | "booking" | "warmth";
  label: string;
  score: number;
  max: number;
}

export interface MriDiagnosticSignal {
  key: string;
  label: string;
  status: "active" | "passive";
  state: "ok" | "watch" | "alert";
}

export interface MriMockData {
  scanId: string;
  patient: { name: string; vertical: string };
  scannedAt: string; // ISO
  confidence: number; // 0..1
  score: number; // 0..100
  recoverable: number; // currency units
  currency: string;
  severity: Severity;
  topLeaks: MriLeak[];
  evidence: {
    channel: string;
    timestamp: string;
    quote: string;
    interpretation: string;
    dimensions: MriDimension[];
  };
  narrative: string;
  recommendation: {
    focus: string;
    rationale: string;
  };
  signals: MriDiagnosticSignal[];
  signalSummary: {
    total: number;
    findings: number;
    criticalAlerts: number;
  };
}

export function getMockMri(scanId: string): MriMockData {
  return {
    scanId,
    patient: { name: "Rosenfeld Aesthetics", vertical: "Med-Spa · Tel Aviv" },
    scannedAt: new Date().toISOString(),
    confidence: 0.86,
    score: 59,
    recoverable: 78942,
    currency: "₪",
    severity: "critical",
    topLeaks: [
      { key: "acceptance", label: "Acceptance", amount: 67392 },
      { key: "booking", label: "Booking", amount: 59904 },
      { key: "showup", label: "Show-up", amount: 24192 },
      { key: "completion", label: "Completion", amount: 562 },
    ],
    evidence: {
      channel: "WhatsApp · Inbound Lead",
      timestamp: "Mar 14 · 09:47",
      quote: "Tuesday 10am works.",
      interpretation:
        "Answered, but did not qualify the lead or actively advance toward a committed consultation.",
      dimensions: [
        { key: "qualification", label: "Qualification Quality", score: 2, max: 20 },
        { key: "booking", label: "Booking Conversion", score: 14, max: 20 },
        { key: "warmth", label: "Warmth", score: 3, max: 20 },
      ],
    },
    narrative:
      "Rosenfeld Aesthetics is bleeding revenue at the top of the funnel. " +
      "Inbound interest is high, but acceptance flow is reactive — leads are answered, " +
      "rarely qualified, and almost never advanced toward a committed consultation. " +
      "Show-up and completion are healthy once a booking exists; the leak is upstream. " +
      "Tightening qualification on the first WhatsApp touch is the highest-leverage move available this quarter.",
    recommendation: {
      focus: "Start with the highest leakage category first — Acceptance.",
      rationale: "Recovers an estimated ₪67,392/mo and unblocks every downstream stage.",
    },
    signals: [
      { key: "call_response", label: "Call Response", status: "active", state: "alert" },
      { key: "wa_handling", label: "WhatsApp Lead Handling", status: "active", state: "alert" },
      { key: "booking_conv", label: "Booking Conversion", status: "active", state: "watch" },
      { key: "acceptance", label: "Acceptance Leakage", status: "passive", state: "alert" },
      { key: "showup_risk", label: "Show-Up Risk", status: "passive", state: "watch" },
      { key: "reactivation", label: "Reactivation Opportunity", status: "passive", state: "watch" },
      { key: "referral", label: "Referral Leakage", status: "passive", state: "ok" },
      { key: "drop_off", label: "Conversation Drop-Off Signals", status: "passive", state: "watch" },
    ],
    signalSummary: {
      total: 8,
      findings: 3,
      criticalAlerts: 1,
    },
  };
}

export type LeadStatus = "ליד חדש" | "בטיפול" | "SMS נשלח" | "תור נקבע" | string;

export interface Lead {
  id: string;
  name: string;            // column: name
  phone: string;           // column: phone
  model: string;           // column: model
  intents: string[];       // column: intents (pipe-separated), fallback: intent
  mileage: string;         // column: mileage
  appointment_time: string | null; // column: appointment_time — null → "ממתין לתיאום"
  created_at: string;      // column: created_at
  status: LeadStatus;      // column: status
  source: string;          // column: source
  sms_sent: boolean;       // column: sms_sent
  calendar_booked: boolean;// column: calendar_booked
  notes?: string | null;
  last_call_topic?: string | null;
  last_call_summary?: string | null;
}

export interface LeadStats {
  total: number;
  testRides: number;
  appointments: number;
  newLeads: number;
  thisWeek: number;
}

export interface SupabaseLead {
  id: string;
  created_at: string;
  name: string | null;
  phone: string;
  source: "voice" | "whatsapp";
  service: string | null;
  status: string;
  notes: string | null;
  agent_id: string | null;
  last_call_topic?: string | null;
  last_call_summary?: string | null;
  last_call_at?: string | null;
  appointment_at?: string | null;
}

export interface LeadsApiResponse {
  leads: SupabaseLead[];
  stats: {
    total: number;
    today: number;
    new: number;
    contacted: number;
    voice: number;
    whatsapp: number;
  };
}

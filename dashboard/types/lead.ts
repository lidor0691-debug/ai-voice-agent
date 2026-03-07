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
}

export interface LeadStats {
  total: number;
  testRides: number;
  appointments: number;
  newLeads: number;
  thisWeek: number;
}

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Lead, LeadStats } from "@/types/lead";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function maskPhone(phone: string): string {
  if (!phone || phone.length < 4) return phone ?? "";
  return phone.slice(0, -4).replace(/\d/g, "*") + phone.slice(-4);
}

const PHONE_PLACEHOLDER = "לא זמין";
const PHONE_JUNK_VALUES = new Set(["browser", "unknown", "null", "undefined", ""]);

export function displayPhone(phone: string | null | undefined): string {
  if (!phone) return PHONE_PLACEHOLDER;
  const s = String(phone).trim();
  if (PHONE_JUNK_VALUES.has(s.toLowerCase())) return PHONE_PLACEHOLDER;
  const digits = s.replace(/\D/g, "");
  if (digits.length < 6) return PHONE_PLACEHOLDER;
  return s;
}

export function isValidPhone(phone: string | null | undefined): boolean {
  if (!phone) return false;
  const s = String(phone).trim();
  if (PHONE_JUNK_VALUES.has(s.toLowerCase())) return false;
  return s.replace(/\D/g, "").length >= 6;
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("he-IL", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("he-IL", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function addSeconds(iso: string, seconds: number): string {
  return new Date(new Date(iso).getTime() + seconds * 1000).toISOString();
}

export function computeStats(leads: Lead[]): LeadStats {
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  return {
    total: leads.length,
    testRides: leads.filter((l) => l.intents.includes("נסיעת מבחן")).length,
    appointments: leads.filter((l) => l.calendar_booked).length,
    newLeads: leads.filter((l) => l.status === "ליד חדש" || l.status === "new").length,
    thisWeek: leads.filter((l) => new Date(l.created_at) >= weekAgo).length,
  };
}

export function leadsPerDay(leads: Lead[]): { label: string; count: number }[] {
  const map: Record<string, number> = {};
  leads.forEach((l) => {
    const day = l.created_at.slice(0, 10);
    map[day] = (map[day] ?? 0) + 1;
  });
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-7)
    .map(([label, count]) => ({ label, count }));
}

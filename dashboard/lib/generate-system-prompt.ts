// lib/generate-system-prompt.ts

export interface PromptInputs {
  agentName: string;
  businessName?: string;
  language?: string;     // "he" | "en" | ...
  tone?: string;         // "friendly" | "professional" | ...
  services?: { name: string; detail?: string }[];
  pricing?: { name: string; detail?: string }[];
  handoffRules?: string[];      // e.g. ["transfer to human if angry"]
  transferNumber?: string;
  behaviorNotes?: string;       // free text from Step 4
}

const LANG_LABEL: Record<string, string> = {
  he: "Hebrew",
  en: "English",
  es: "Spanish",
  fr: "French",
  de: "German",
};

/**
 * Builds a clean system prompt from wizard inputs. Mirrors the SECTION STRUCTURE of the
 * backend build_supabase_system_prompt() (role / language / tone / services / handoff),
 * but does NOT inline knowledge items — the backend appends those at call time.
 */
export function generateSystemPrompt(input: PromptInputs): string {
  const lang = LANG_LABEL[input.language ?? "he"] ?? input.language ?? "Hebrew";
  const tone = input.tone?.trim() || "friendly";
  const lines: string[] = [];

  lines.push(
    `You are ${input.agentName}, an AI assistant${
      input.businessName ? ` for ${input.businessName}` : ""
    }.`
  );
  lines.push(`Language: ${lang}. Tone: ${tone}.`);
  lines.push("");
  lines.push("━━ ROLE ━━");
  lines.push(
    "You are a helpful, concise conversation partner. Answer questions, qualify the lead, " +
      "and move the conversation toward the business goal. Do not invent facts you were not given."
  );

  if (input.services && input.services.length > 0) {
    lines.push("");
    lines.push("━━ SERVICES ━━");
    for (const s of input.services) {
      lines.push(`- ${s.name}${s.detail ? `: ${s.detail}` : ""}`);
    }
  }

  if (input.pricing && input.pricing.length > 0) {
    lines.push("");
    lines.push("━━ PRICING ━━");
    for (const p of input.pricing) {
      lines.push(`- ${p.name}${p.detail ? `: ${p.detail}` : ""}`);
    }
  }

  if (input.handoffRules && input.handoffRules.length > 0) {
    lines.push("");
    lines.push("━━ HANDOFF RULES ━━");
    for (const r of input.handoffRules) lines.push(`- ${r}`);
    if (input.transferNumber) {
      lines.push(`When handing off, transfer to: ${input.transferNumber}`);
    }
  }

  if (input.behaviorNotes && input.behaviorNotes.trim()) {
    lines.push("");
    lines.push("━━ ADDITIONAL NOTES ━━");
    lines.push(input.behaviorNotes.trim());
  }

  return lines.join("\n");
}

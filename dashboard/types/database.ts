export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export interface Client {
  id: string;
  name: string;
  metadata: Json | null;
  created_at: string;
}

export interface ClientAsset {
  id: string;
  client_id: string;
  asset_name: string;
  asset_type: 'text' | 'link' | 'pdf' | 'image' | 'video';
  trigger_key: string;
  content: string;
  sort_order: number;
  enabled: boolean;
  created_at: string;
}

export interface AgentConfig {
  id: string;
  business_name: string | null;
  agent_name: string;
  phone_number: string | null;
  is_active: boolean;

  // Conversation
  first_message: string | null;
  system_prompt: string | null;
  tone: string | null;
  language: string | null;

  // Voice
  voice_provider: string | null;
  voice_id: string | null;
  speaking_rate: number | null;
  style_prompt: string | null;

  // Model
  model_provider: string | null;
  model_name: string | null;
  temperature: number | null;

  // Tools
  transfer_number: string | null;
  post_call_webhook_url: string | null;  // legacy

  // Lead delivery
  lead_delivery_method: string | null;
  lead_delivery_target: string | null;

  // WhatsApp channel
  whatsapp_enabled: boolean | null;
  whatsapp_number: string | null;
  whatsapp_followup_enabled: boolean | null;
  whatsapp_followup_type: string | null;          // none | summary | appointment | next_step
  whatsapp_followup_template: string | null;

  // Multi-tenant
  client_id: string | null;
  channel: 'voice' | 'whatsapp' | null;

  created_at: string;
  updated_at: string;
}

export interface KnowledgeItem {
  id: string;
  agent_id: string;
  category: string | null;
  title: string;
  content: string;
  priority: number | null;
  is_active: boolean;
  created_at: string;
}

export interface CallLog {
  id: string;
  agent_id: string | null;
  phone_number: string | null;
  status: string | null;          // completed | missed | failed
  duration: number | null;        // seconds

  // Structured call summary (written by backend after each call)
  lead_data: Json | null;         // raw collected lead args
  summary: string | null;         // human-readable summary
  outcome: string | null;         // lead_collected | no_lead | transferred | failed
  appointment_set: boolean | null;
  followup_needed: boolean | null;
  next_action: string | null;

  created_at: string;
}

export interface Database {
  public: {
    Tables: {
      agents_config: {
        Row: AgentConfig;
        Insert: Omit<AgentConfig, "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Omit<AgentConfig, "id" | "created_at">>;
        Relationships: [];
      };
      knowledge_items: {
        Row: KnowledgeItem;
        Insert: Omit<KnowledgeItem, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Omit<KnowledgeItem, "id" | "created_at">>;
        Relationships: [];
      };
      call_logs: {
        Row: CallLog;
        Insert: Omit<CallLog, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Omit<CallLog, "id" | "created_at">>;
        Relationships: [];
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
}

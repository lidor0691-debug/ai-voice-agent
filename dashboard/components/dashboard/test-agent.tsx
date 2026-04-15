"use client";

import { useState } from "react";
import { Send, Bot, User } from "lucide-react";
import { AgentConfig } from "@/types/database";
import { useLanguage } from "@/context/language-context";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "system_prompt" | "first_message">[];
}

export function TestAgent({ agents }: Props) {
  const [selectedAgent, setSelectedAgent] = useState(agents[0]?.id ?? "");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const { t } = useLanguage();

  const agent = agents.find((a) => a.id === selectedAgent);

  const startConversation = () => {
    if (!agent?.first_message) return;
    setMessages([{ role: "assistant", content: agent.first_message }]);
  };

  const sendMessage = async () => {
    if (!input.trim() || !agent) return;
    const userMsg: Message = { role: "user", content: input.trim() };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/api/test-agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agent.id, messages: next, system_prompt: agent.system_prompt }),
      });
      if (res.ok) {
        const { reply } = await res.json();
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: t.backend_error }]);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: t.connection_error }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div className="bg-surface-2 border border-border rounded-xl flex flex-col h-[420px]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-brand-400" />
          <span className="text-white text-sm font-medium">{t.test_agent_title}</span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedAgent}
            onChange={(e) => { setSelectedAgent(e.target.value); setMessages([]); }}
            className="bg-surface-3 border border-border rounded-lg px-2.5 py-1 text-xs text-gray-300 focus:outline-none"
          >
            {agents.length === 0 && <option value="">{t.no_agents_select}</option>}
            {agents.map((a) => (
              <option key={a.id} value={a.id} className="bg-surface-3">{a.agent_name}</option>
            ))}
          </select>
          {messages.length === 0 && agent?.first_message && (
            <button
              onClick={startConversation}
              className="bg-brand-600/20 hover:bg-brand-600/30 text-brand-400 text-xs px-2.5 py-1 rounded-lg transition-colors border border-brand-600/20"
            >
              {t.start_btn}
            </button>
          )}
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              className="text-gray-600 hover:text-gray-400 text-xs px-2 py-1 rounded-lg transition-colors"
            >
              {t.reset_btn}
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <p className="text-gray-600 text-xs">
              {agents.length === 0 ? t.create_agent_first : t.test_agent_prompt}
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex items-start gap-2.5 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === "user" ? "bg-brand-600/20" : "bg-surface-4"}`}>
              {msg.role === "user" ? <User className="w-3 h-3 text-brand-400" /> : <Bot className="w-3 h-3 text-gray-400" />}
            </div>
            <div className={`max-w-[75%] px-3 py-2 rounded-xl text-sm leading-relaxed ${msg.role === "user" ? "bg-brand-600/20 text-brand-100 rounded-tr-sm" : "bg-surface-3 text-gray-200 rounded-tl-sm"}`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-start gap-2.5">
            <div className="w-6 h-6 rounded-full bg-surface-4 flex items-center justify-center flex-shrink-0">
              <Bot className="w-3 h-3 text-gray-400" />
            </div>
            <div className="bg-surface-3 text-gray-500 px-3 py-2 rounded-xl rounded-tl-sm text-sm">
              <span className="animate-pulse">{t.thinking}</span>
            </div>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={t.type_message_placeholder}
          disabled={!agent || loading}
          className="flex-1 bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 transition-colors disabled:opacity-50"
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || !agent || loading}
          className="w-8 h-8 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-lg flex items-center justify-center transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

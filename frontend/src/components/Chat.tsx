import { useEffect, useRef, useState } from "react";
import { sendChat } from "../api";
import type { UiMessage } from "../types";
import Message from "./Message";
import Composer from "./Composer";

const STARTERS = [
  "What was profit before tax in FY25?",
  "How did the CASA ratio evolve during 2025?",
  "Why did CAR decrease in Q4 2025?",
  "Tell me about the TCBS IPO.",
];

export default function Chat() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(
    () => localStorage.getItem("tcb_session"));
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const res = await sendChat(text, sessionId);
      setSessionId(res.session_id);
      localStorage.setItem("tcb_session", res.session_id);
      setMessages((m) => [...m, { role: "assistant", content: res.reply,
        citations: res.citations, route: res.route, model: res.model }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", error: true,
        content: e instanceof Error ? e.message : "Something went wrong." }]);
    } finally {
      setBusy(false);
    }
  }

  function newChat() {
    localStorage.removeItem("tcb_session");
    setSessionId(null);
    setMessages([]);
  }

  return (
    <main className="flex-1 flex flex-col max-w-3xl w-full mx-auto p-4">
      <div className="flex justify-end mb-2">
        <button onClick={newChat} className="text-sm text-slate-500 hover:text-red-700">
          + New chat
        </button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <div className="grid gap-2 sm:grid-cols-2 mt-8">
            {STARTERS.map((s) => (
              <button key={s} onClick={() => ask(s)}
                className="text-left text-sm bg-white border border-slate-200 rounded-xl p-3 hover:border-red-400 shadow-sm">
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => <Message key={i} msg={m} />)}
        {busy && <div className="text-sm text-slate-400 animate-pulse">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <Composer disabled={busy} onSend={ask} />
    </main>
  );
}

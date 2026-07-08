import { useState } from "react";

export default function Composer({ disabled, onSend }:
  { disabled: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSend(text);
    setText("");
  }
  return (
    <form onSubmit={submit} className="flex gap-2 pt-2 border-t border-slate-200">
      <input value={text} onChange={(e) => setText(e.target.value)} disabled={disabled}
        placeholder="Ask about Techcombank's FY25 results…"
        className="flex-1 rounded-xl border border-slate-300 px-4 py-2 focus:outline-none focus:border-red-500 bg-white" />
      <button disabled={disabled || !text.trim()}
        className="bg-red-700 text-white rounded-xl px-5 py-2 disabled:opacity-40">
        Send
      </button>
    </form>
  );
}

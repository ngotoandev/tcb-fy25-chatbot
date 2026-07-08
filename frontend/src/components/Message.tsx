import { useState } from "react";
import type { UiMessage } from "../types";

export default function Message({ msg }: { msg: UiMessage }) {
  const [open, setOpen] = useState(false);
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-red-700 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%]">
          {msg.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-1 max-w-[85%]">
      <div className={`rounded-2xl rounded-bl-sm px-4 py-2 whitespace-pre-wrap shadow-sm ${
        msg.error ? "bg-amber-50 border border-amber-300 text-amber-900" : "bg-white border border-slate-200"}`}>
        {msg.content}
      </div>
      {(msg.route || msg.citations?.length) ? (
        <div className="flex flex-wrap items-center gap-1 pl-1">
          {msg.route && (
            <span className="text-[10px] uppercase tracking-wide bg-slate-200 text-slate-600 rounded px-1.5 py-0.5">
              {msg.route} · {msg.model}
            </span>
          )}
          {msg.citations?.map((c, i) => (
            <button key={i} onClick={() => setOpen(!open)}
              className="text-[10px] bg-blue-50 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5 hover:bg-blue-100">
              p.{c.page}
            </button>
          ))}
        </div>
      ) : null}
      {open && msg.citations?.length ? (
        <div className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-2 space-y-1">
          {msg.citations.map((c, i) => (
            <p key={i}><span className="font-semibold">p.{c.page}:</span> “{c.snippet}…”</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

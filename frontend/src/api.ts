import type { ChatResponse } from "./types";

export async function sendChat(message: string, sessionId: string | null): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail).catch(() => res.statusText);
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json();
}

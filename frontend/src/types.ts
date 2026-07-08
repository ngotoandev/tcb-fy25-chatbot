export interface Citation { page: number; snippet: string }
export interface ChatResponse {
  session_id: string; reply: string; citations: Citation[];
  route: string; model: string; latency_ms: number;
}
export interface UiMessage {
  role: "user" | "assistant"; content: string;
  citations?: Citation[]; route?: string; model?: string; error?: boolean;
}

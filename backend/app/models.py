from typing import Literal
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)

class Citation(BaseModel):
    page: int
    snippet: str

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    citations: list[Citation] = []
    route: str
    model: str
    latency_ms: int

class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

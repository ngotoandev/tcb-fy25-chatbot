from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.chat import router as chat_router
from app.config import get_settings
from app.services.pipeline import ChatPipeline

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TCB FY25 Chatbot")
    app.state.pipeline = ChatPipeline(settings)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "chunks": len(app.state.pipeline.retriever.chunks),
                "mock": settings.mock_llm}

    app.include_router(chat_router)
    static = Path(settings.static_dir)
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="spa")
    return app

app = create_app()

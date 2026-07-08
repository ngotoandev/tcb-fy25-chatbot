from app.config import Settings
from app.stores.base import SessionStore
from app.stores.memory import MemorySessionStore

def make_store(settings: Settings) -> SessionStore:
    if settings.session_store == "dynamo":
        from app.stores.dynamo import DynamoSessionStore
        return DynamoSessionStore(settings.sessions_table, settings.session_ttl_hours,
                                  settings.bedrock_region)
    return MemorySessionStore()

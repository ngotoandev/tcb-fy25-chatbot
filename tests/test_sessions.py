from app.models import Turn
from app.stores.memory import MemorySessionStore

def test_memory_store_roundtrip():
    s = MemorySessionStore()
    assert s.get("a") == []
    s.append("a", Turn(role="user", content="hi"))
    s.append("a", Turn(role="assistant", content="hello"))
    turns = s.get("a")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert s.get("b") == []

from collections import defaultdict
from app.models import Turn

class MemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, list[Turn]] = defaultdict(list)

    def get(self, session_id: str) -> list[Turn]:
        return list(self._data.get(session_id, []))

    def append(self, session_id: str, turn: Turn) -> None:
        self._data[session_id].append(turn)

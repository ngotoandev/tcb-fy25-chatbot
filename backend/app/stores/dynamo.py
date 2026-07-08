import time
import boto3
from app.models import Turn

class DynamoSessionStore:
    """One item per session: {session_id, turns: [{role, content}], expires_at}."""

    def __init__(self, table_name: str, ttl_hours: int = 24, region: str = "us-east-1") -> None:
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._ttl_hours = ttl_hours

    def get(self, session_id: str) -> list[Turn]:
        item = self._table.get_item(Key={"session_id": session_id}).get("Item")
        return [Turn(**t) for t in item["turns"]] if item else []

    def append(self, session_id: str, turn: Turn) -> None:
        expires = int(time.time()) + self._ttl_hours * 3600
        self._table.update_item(
            Key={"session_id": session_id},
            UpdateExpression=("SET turns = list_append(if_not_exists(turns, :empty), :t), "
                              "expires_at = :exp"),
            ExpressionAttributeValues={":t": [turn.model_dump()], ":empty": [], ":exp": expires},
        )

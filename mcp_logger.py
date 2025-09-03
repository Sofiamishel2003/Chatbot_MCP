
import json, datetime, pathlib

class MCPLogger:
    def __init__(self, path="logs/mcp_log.jsonl"):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, payload: dict):
        rec = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "event": event_type,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

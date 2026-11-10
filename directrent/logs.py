"""One JSON object per log line on stdout."""
import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "level": record.levelname,
                 "logger": record.name}
        msg = record.getMessage()
        try:
            parsed = json.loads(msg)
            entry.update(parsed if isinstance(parsed, dict) else {"msg": msg})
        except ValueError:
            entry["msg"] = msg
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for noisy in ("telethon", "aiogram.event", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

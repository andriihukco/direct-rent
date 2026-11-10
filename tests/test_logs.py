import json
import logging

from directrent.logs import JsonFormatter


def _fmt(msg):
    return json.loads(JsonFormatter().format(logging.LogRecord("x", logging.INFO, "f", 1, msg, None, None)))


def test_json_message_is_merged():
    out = _fmt('{"event": "verdict", "stage": "rules"}')
    assert out["event"] == "verdict" and out["level"] == "INFO" and out["logger"] == "x"


def test_plain_message_kept():
    assert _fmt("hello")["msg"] == "hello"

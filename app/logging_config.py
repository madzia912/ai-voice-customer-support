"""Structured logging setup with contextual job/request IDs."""

from __future__ import annotations

import logging
import sys
from typing import Any, MutableMapping


class ContextFormatter(logging.Formatter):
    """Formatter that appends contextual key=value pairs from ``extra``."""

    _RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()) | {
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        ctx_pairs = [
            f"{k}={v}"
            for k, v in record.__dict__.items()
            if k not in self._RESERVED and not k.startswith("_")
        ]
        return f"{base} | {' '.join(ctx_pairs)}" if ctx_pairs else base


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ContextFormatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Tame noisy third-party loggers.
    for noisy in ("aio_pika", "aiormq", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def bind(logger: logging.Logger, **context: Any) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that injects ``context`` into every record."""

    class _Adapter(logging.LoggerAdapter):
        def process(
            self, msg: str, kwargs: MutableMapping[str, Any]
        ) -> tuple[str, MutableMapping[str, Any]]:
            extra = dict(self.extra or {})
            extra.update(kwargs.get("extra") or {})
            kwargs["extra"] = extra
            return msg, kwargs

    return _Adapter(logger, context)

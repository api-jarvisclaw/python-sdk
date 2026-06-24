"""
jarvisclaw.observability — Langfuse callback hook for Python SDK agents.

Provides an ObservabilityCallback that automatically traces agent tool calls
to Langfuse. Attach to any JarvisClaw Agent for per-request cost/latency tracking.

Usage:
    from jarvisclaw.observability import LangfuseCallback
    from jarvisclaw import Agent

    agent = Agent(api_key="...", callbacks=[LangfuseCallback()])
"""

import os
import time
import uuid
import random
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class LangfuseConfig:
    """Configuration for the Langfuse exporter."""
    host: str = ""
    public_key: str = ""
    secret_key: str = ""
    enabled: bool = False
    sample_rate: float = 1.0
    flush_interval: float = 5.0  # seconds
    batch_size: int = 50

    @classmethod
    def from_env(cls) -> "LangfuseConfig":
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        rate_str = os.getenv("LANGFUSE_SAMPLE_RATE", "1.0")
        try:
            rate = float(rate_str)
            if rate <= 0 or rate > 1.0:
                rate = 1.0
        except ValueError:
            rate = 1.0

        return cls(
            host=host,
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            enabled=os.getenv("LANGFUSE_ENABLED", "").lower() == "true",
            sample_rate=rate,
            flush_interval=float(os.getenv("LANGFUSE_FLUSH_MS", "5000")) / 1000.0,
            batch_size=int(os.getenv("LANGFUSE_BATCH_SIZE", "50")),
        )


class LangfuseCallback:
    """
    Observability callback that sends trace/generation events to Langfuse.
    
    Implements the JarvisClaw callback protocol:
      - on_tool_start(tool_name, input_data, metadata)
      - on_tool_end(tool_name, output_data, metadata, error)
      - flush()
    """

    def __init__(self, config: Optional[LangfuseConfig] = None):
        self.config = config or LangfuseConfig.from_env()
        self._buffer: List[Dict[str, Any]] = []
        self._session = requests.Session()
        if self.config.public_key and self.config.secret_key:
            self._session.auth = (self.config.public_key, self.config.secret_key)
        # Track active spans by tool invocation
        self._active_spans: Dict[str, Dict[str, Any]] = {}

    @property
    def is_enabled(self) -> bool:
        return self.config.enabled and bool(self.config.public_key)

    def _should_sample(self) -> bool:
        if self.config.sample_rate >= 1.0:
            return True
        return random.random() < self.config.sample_rate

    def on_tool_start(self, tool_name: str, input_data: Any = None, metadata: Optional[Dict] = None) -> Optional[str]:
        """Called before a tool executes. Returns a span_id for correlation."""
        if not self.is_enabled or not self._should_sample():
            return None

        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        now = time.time()

        self._active_spans[span_id] = {
            "trace_id": trace_id,
            "span_id": span_id,
            "tool_name": tool_name,
            "start_time": now,
            "input_data": input_data,
            "metadata": metadata or {},
        }

        # Emit trace-create event
        self._enqueue({
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": self._iso(now),
            "body": {
                "id": trace_id,
                "name": f"mcp.tool.{tool_name}",
                "userId": metadata.get("user_id", "") if metadata else "",
                "metadata": metadata or {},
            },
        })

        return span_id

    def on_tool_end(
        self,
        span_id: Optional[str],
        output_data: Any = None,
        error: Optional[str] = None,
        usage: Optional[Dict] = None,
        cost_usd: float = 0.0,
    ):
        """Called after a tool completes. Emits a generation event."""
        if not span_id or span_id not in self._active_spans:
            return

        span = self._active_spans.pop(span_id)
        end_time = time.time()
        duration_ms = (end_time - span["start_time"]) * 1000

        level = "ERROR" if error else "DEFAULT"
        status_msg = error or "ok"

        self._enqueue({
            "id": str(uuid.uuid4()),
            "type": "generation-create",
            "timestamp": self._iso(span["start_time"]),
            "body": {
                "id": span["span_id"],
                "traceId": span["trace_id"],
                "name": span["tool_name"],
                "startTime": self._iso(span["start_time"]),
                "endTime": self._iso(end_time),
                "level": level,
                "statusMessage": status_msg,
                "input": span.get("input_data"),
                "output": output_data,
                "usage": usage or {},
                "metadata": {
                    **span.get("metadata", {}),
                    "costUSD": cost_usd,
                    "durationMs": round(duration_ms, 2),
                },
            },
        })

        # Auto-flush when buffer is full
        if len(self._buffer) >= self.config.batch_size:
            self.flush()

    def flush(self):
        """Send all buffered events to Langfuse."""
        if not self._buffer or not self.is_enabled:
            return

        batch = self._buffer[:]
        self._buffer.clear()

        payload = {"batch": batch, "metadata": {"sdk": "jarvisclaw-python", "version": "1.0.0"}}

        try:
            resp = self._session.post(
                f"{self.config.host}/api/public/ingestion",
                json=payload,
                timeout=15,
            )
            if resp.status_code >= 400:
                logger.warning(f"[langfuse] flush error: status={resp.status_code}, batch_size={len(batch)}")
        except requests.RequestException as e:
            logger.warning(f"[langfuse] flush network error: {e}, batch_size={len(batch)}")
            # Best-effort re-enqueue (cap at 3x batch_size)
            if len(self._buffer) + len(batch) <= self.config.batch_size * 3:
                self._buffer = batch + self._buffer

    def _enqueue(self, event: Dict[str, Any]):
        self._buffer.append(event)

    @staticmethod
    def _iso(ts: float) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def __del__(self):
        try:
            self.flush()
        except Exception:
            pass

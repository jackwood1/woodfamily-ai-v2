"""In-memory span buffer for dashboard display."""

import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor


class SpanBufferProcessor(SpanProcessor):
    """Stores the last N spans in memory for API access."""

    def __init__(self, max_spans: int = 100) -> None:
        self._max_spans = max_spans
        self._spans: Deque[Dict[str, Any]] = deque(maxlen=max_spans)
        self._lock = threading.Lock()

    def on_start(
        self,
        span: "ReadableSpan",
        parent_context: Optional[Any] = None,
    ) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        attrs = dict(span.attributes) if span.attributes else {}
        # Convert non-JSON-serializable values
        safe_attrs = {}
        for k, v in attrs.items():
            try:
                if hasattr(v, "__str__") and not isinstance(v, (str, int, float, bool, type(None))):
                    safe_attrs[str(k)] = str(v)
                else:
                    safe_attrs[str(k)] = v
            except Exception:
                safe_attrs[str(k)] = str(v)

        status = span.status
        status_str = str(status.status_code) if status else "UNSET"

        entry = {
            "name": span.name,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "duration_ms": (span.end_time - span.start_time) / 1_000_000 if span.end_time and span.start_time else None,
            "status": status_str,
            "attributes": safe_attrs,
        }
        with self._lock:
            self._spans.append(entry)

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return True

    def shutdown(self) -> None:
        pass

    def get_spans(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            spans = list(self._spans)
        spans.reverse()  # newest first
        if limit:
            spans = spans[:limit]
        return spans


# Global buffer instance for dashboard
_span_buffer: Optional[SpanBufferProcessor] = None


def get_span_buffer() -> Optional[SpanBufferProcessor]:
    return _span_buffer


def set_span_buffer(processor: SpanBufferProcessor) -> None:
    global _span_buffer
    _span_buffer = processor

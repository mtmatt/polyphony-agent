import logging
import os
import sys
import structlog
from typing import Optional, Any, Dict, List
from datetime import datetime

# OpenTelemetry imports (optional/best-effort)
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import RESOURCE_ATTRIBUTES, Resource
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

class _PolyphonyConsoleRenderer:
    """
    Clean single-line structured log renderer.

    Format:  HH:MM:SS  LEVEL    event_name  key=val  key=val  file:line

    All key-value pairs stay on a single line — no mid-word wrapping.
    """

    _LEVEL_STYLES: Dict[str, str] = {
        "debug":    "\033[36m",       # cyan
        "info":     "\033[32m",       # green
        "warning":  "\033[33m",       # yellow
        "error":    "\033[31;1m",     # bold red
        "critical": "\033[97;41;1m",  # bold white on red bg
    }
    _RST  = "\033[0m"
    _DIM  = "\033[2m"
    _BOLD = "\033[1m"
    _KEY  = "\033[36m"   # cyan  for keys
    _VAL  = "\033[35m"   # magenta for values

    def __call__(self, logger: Any, method: str, event_dict: Dict[str, Any]) -> str:
        # Grab stdlib record BEFORE meta removal so we can read file/lineno.
        record = event_dict.pop("_record", None)
        event_dict.pop("_from_structlog", None)

        level     = event_dict.pop("level", method).lower()
        event     = str(event_dict.pop("event", ""))
        timestamp = event_dict.pop("timestamp", "")
        event_dict.pop("logger", None)
        event_dict.pop("logger_name", None)
        exc_info  = event_dict.pop("exc_info", None)

        # HH:MM:SS from ISO timestamp
        ts = timestamp[11:19] if len(timestamp) >= 19 else timestamp

        # Source location from the stdlib LogRecord
        source = ""
        if record is not None:
            source = f"{record.filename}:{record.lineno}"

        level_color = self._LEVEL_STYLES.get(level, "")
        level_label = level.upper()

        # Build key=value pairs — repr only for strings, bare otherwise
        kv_parts = []
        for k, v in event_dict.items():
            v_str = repr(v) if isinstance(v, str) else str(v)
            kv_parts.append(
                f"{self._KEY}{k}{self._RST}={self._VAL}{v_str}{self._RST}"
            )

        # Assemble the line
        parts: List[str] = []
        if ts:
            parts.append(f"{self._DIM}{ts}{self._RST}")
        parts.append(f"{level_color}{level_label:<8}{self._RST}")
        parts.append(f"{self._BOLD}{event}{self._RST}")
        if kv_parts:
            parts.append("  ".join(kv_parts))
        if source:
            parts.append(f"{self._DIM}{source}{self._RST}")

        line = "  ".join(parts)

        # Append exception traceback on following lines if present
        if exc_info:
            import traceback
            tb = "".join(traceback.format_exception(*exc_info)).rstrip()
            line = line + "\n" + tb

        return line


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    console_format: str = "rich",  # rich, json, text
):
    """
    Sets up structured logging using structlog with stdlib integration.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    handlers: List[logging.Handler] = []

    # 1. Console handler — plain StreamHandler so *we* control every byte.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    handlers.append(console_handler)

    # 2. File handler
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    # 3. Standard library logging configuration
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)

    # 4. structlog configuration
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 5. Shared pre-chain (runs before the per-handler renderer)
    foreign_pre_chain = [
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.add_log_level,
    ]

    # Console formatter
    if console_format == "rich":
        console_processors = [
            # NOTE: do NOT call remove_processors_meta here —
            # _PolyphonyConsoleRenderer extracts _record itself.
            _PolyphonyConsoleRenderer(),
        ]
    elif console_format == "json":
        console_processors = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        console_processors = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.LogfmtRenderer(),
        ]

    console_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processors=console_processors,
        foreign_pre_chain=foreign_pre_chain,
    ))

    # File formatter (always JSON for structured logs)
    if log_file:
        file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.TimeStamper(fmt="iso", utc=False),
                structlog.processors.add_log_level,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=foreign_pre_chain,
        ))

    return structlog.get_logger()

def setup_tracing(service_name: str = "polyphony-agent"):
    """
    Sets up basic OpenTelemetry tracing.
    """
    if not HAS_OTEL:
        return None

    resource = Resource(attributes={
        "service.name": service_name
    })
    
    provider = TracerProvider(resource=resource)
    # Console exporter for now, can be swapped for Jaeger/OTLP later
    # processor = BatchSpanProcessor(ConsoleSpanExporter())
    # provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

# Default logger
logger = structlog.get_logger()

def get_logger(name: Optional[str] = None):
    return structlog.get_logger(name) if name else logger

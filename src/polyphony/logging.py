import logging
import os
import sys
import structlog
from typing import Optional, Any, Dict, List
from rich.logging import RichHandler
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

    # 1. Console handler
    if console_format == "rich":
        console_handler = RichHandler(rich_tracebacks=True, markup=True)
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        
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
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 5. Formatter for handlers
    # We want different formatting for console vs file
    # For simplicity, we use ProcessorFormatter
    
    # Define shared processors for the actual formatting
    formatter_processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    ]

    # Console formatter (pretty or JSON)
    if console_format == "rich":
        console_processors = formatter_processors + [structlog.dev.ConsoleRenderer(colors=True)]
    elif console_format == "json":
        console_processors = formatter_processors + [structlog.processors.JSONRenderer()]
    else:
        console_processors = formatter_processors + [structlog.processors.LogfmtRenderer()]

    console_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processors=console_processors
    ))

    # File formatter (always JSON for structured logs)
    if log_file:
        file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processors=formatter_processors + [structlog.processors.JSONRenderer()]
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

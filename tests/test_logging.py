import os
import json
import logging
import structlog
from polyphony.logging import setup_logging

def test_setup_logging_console(capsys):
    """Test that logging to console works."""
    setup_logging(log_level="INFO", console_format="text")
    logger = structlog.get_logger("test_console")
    logger.info("hello console", key="value")
    
    captured = capsys.readouterr()
    print(f"Captured out: {captured.out!r}")
    print(f"Captured err: {captured.err!r}")
    # Depending on how structlog is configured, it might go to stderr or stdout
    output = captured.out + captured.err
    assert "hello console" in output
    assert "key='value'" in output or '"key": "value"' in output or "key: 'value'" in output or "key: value" in output or "key=value" in output

def test_setup_logging_file(tmp_path):
    """Test that logging to file works and produces JSON."""
    log_file = tmp_path / "test.log"
    setup_logging(log_level="DEBUG", log_file=str(log_file), console_format="text")
    
    logger = structlog.get_logger("test_file")
    logger.debug("hello file", foo="bar")
    
    assert log_file.exists()
    content = log_file.read_text()
    print(f"File content: {content!r}")
    
    # Check if it's valid JSON
    data = json.loads(content)
    assert data["event"] == "hello file"
    assert data["foo"] == "bar"
    assert data["level"] == "debug"
    assert "timestamp" in data

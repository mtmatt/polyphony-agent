#!/usr/bin/env python3
"""
Reproduction script for malformed log output issue.
This script demonstrates ANSI escape codes appearing in log output.
"""

import tempfile
import os

# Initialize logging with both console and file output
from polyphony.logging import setup_logging

# Create a temporary log file
log_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log')
log_file.close()
log_path = log_file.name

print(f"=" * 60)
print("REPRODUCTION: Malformed Log Output with ANSI Codes")
print(f"=" * 60)
print(f"Log file will be written to: {log_path}")
print(f"=" * 60)
print()

# Set up logging with file output
logger = setup_logging(
    log_level="DEBUG",
    log_file=log_path,
    console_format="rich"
)

# Emit log messages at different levels
print("Emitting log messages...")
print()

logger.debug("This is a DEBUG message - should appear in file")
logger.info("This is an INFO message - should appear in file")
logger.warning("This is a WARNING message - should appear in file")
logger.error("This is an ERROR message - should appear in file")

try:
    raise ValueError("Sample exception for error logging")
except Exception as e:
    logger.exception("This is an EXCEPTION message with traceback")

print()
print(f"=" * 60)
print("Checking log file contents for ANSI escape codes...")
print(f"=" * 60)

# Read the log file and check for ANSI codes
with open(log_path, 'r') as f:
    log_content = f.read()

ansi_escape_found = False
lines_with_ansi = []

for line_num, line in enumerate(log_content.split('\n'), 1):
    # Check for ANSI escape codes (ESC[ is the pattern)
    if '\x1b[' in line or '\033[' in line:
        lines_with_ansi.append((line_num, line))
        ansi_escape_found = True

if ansi_escape_found:
    print(f"\n❌ ISSUE REPRODUCED: {len(lines_with_ansi)} lines contain ANSI escape codes!")
    print(f"\nFirst few affected lines:")
    for ln, line in lines_with_ansi[:3]:
        # Show the line with ANSI codes escaped for visibility
        escaped = repr(line)
        print(f"  Line {ln}: {escaped[:150]}...")
else:
    print(f"\n✅ No ANSI escape codes found in log file.")

print(f"\nFull log file path: {log_path}")
print(f"Log file size: {len(log_content)} bytes")

# Cleanup
if not ansi_escape_found:
    os.unlink(log_path)

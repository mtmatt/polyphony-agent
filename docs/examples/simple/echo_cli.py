#!/usr/bin/env python3
"""A simple echo CLI with optional color output."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Echo a message with optional color.")
    parser.add_argument("message", help="The message to echo")
    parser.add_argument(
        "--color",
        choices=["red", "green", "blue", "yellow"],
        help="Output the message in the specified color",
    )
    args = parser.parse_args()

    color_codes = {
        "red": "\033[91m",
        "green": "\033[92m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
    }
    reset = "\033[0m"

    if args.color:
        print(f"{color_codes[args.color]}{args.message}{reset}")
    else:
        print(args.message)


if __name__ == "__main__":
    main()

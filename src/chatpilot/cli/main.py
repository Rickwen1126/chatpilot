"""CLI entry point for chatpilot — talks to running server."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

DEFAULT_BASE_URL = "http://localhost:2999"


def chat(base_url: str, message: str, user_id: str = "cli-user") -> None:
    """Send a message through the full server pipeline."""
    url = f"{base_url}/cli/chat"
    data = json.dumps({"message": message, "user_id": user_id}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            print(result.get("response", "(no response)"))
    except urllib.error.URLError as e:
        print(f"Error: {e}. Is the server running?", file=sys.stderr)
        sys.exit(1)


def list_chatbots(base_url: str) -> None:
    """List available chatbots via /chatbot command."""
    chat(base_url, "/chatbot list")


def switch_chatbot(base_url: str, name: str) -> None:
    """Switch chatbot via /chatbot command."""
    chat(base_url, f"/chatbot {name}")


def switch_model(base_url: str, model: str) -> None:
    """Switch model via /model command."""
    chat(base_url, f"/model {model}")


def health(base_url: str) -> None:
    """Check server health."""
    url = f"{base_url}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            print(json.dumps(result, indent=2))
    except urllib.error.URLError as e:
        print(f"Server not reachable: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatPilot CLI")
    parser.add_argument(
        "--url", default=DEFAULT_BASE_URL, help="Server URL"
    )
    sub = parser.add_subparsers(dest="command")

    chat_p = sub.add_parser("chat", help="Send a message")
    chat_p.add_argument("message", help="Message text")
    chat_p.add_argument("--user", default="cli-user", help="User ID")

    sub.add_parser("list", help="List chatbots")
    sub.add_parser("health", help="Server health check")
    sub.add_parser("reload", help="Reload config")

    switch_p = sub.add_parser("switch", help="Switch chatbot")
    switch_p.add_argument("name", help="Chatbot name")

    model_p = sub.add_parser("model", help="Switch model")
    model_p.add_argument("name", help="Model ID")

    args = parser.parse_args()
    if args.command == "chat":
        chat(args.url, args.message, args.user)
    elif args.command == "list":
        chat(args.url, "/chatbot list")
    elif args.command == "switch":
        switch_chatbot(args.url, args.name)
    elif args.command == "model":
        switch_model(args.url, args.name)
    elif args.command == "health":
        health(args.url)
    elif args.command == "reload":
        url = f"{args.url}/cli/reload"
        req = urllib.request.Request(
            url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(json.loads(resp.read().decode()).get("status", "done"))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

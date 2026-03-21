# chatpilot Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-03

## Active Technologies
- Python 3.11+ + FastAPI, Pydantic v2, github-copilot-sdk, line-bot-sdk, watchdog, pyyaml, uvicorn (002-new-mvp)
- In-memory（MVP）；SQLite（task history）；disk JSON（context buffer cold layer） (002-new-mvp)

- Python 3.11+ / FastAPI / uv (001-agent-gateway-mvp)

## Project Structure

```text
src/chatpilot/
tests/
config/
```

## Commands

uv run pytest && uv run ruff check src/

## Code Style

Python 3.11+: Pydantic v2 models, Protocol for interfaces, async/await, ruff formatting

## Recent Changes
- 002-new-mvp: Added Python 3.11+ + FastAPI, Pydantic v2, github-copilot-sdk, line-bot-sdk, watchdog, pyyaml, uvicorn

- 001-agent-gateway-mvp: Switched from TypeScript to Python 3.11+ / FastAPI / uv

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

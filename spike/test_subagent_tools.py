"""
Spike: Can Copilot SDK custom_agents (sub-agents) access session-level tools?

Detection: Tool handler writes a file from OUR Python process.
If file exists → tool was called. Agent can't fake this with bash.
"""

import asyncio
import json
import logging
import os
import time
import traceback
from pathlib import Path

from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("spike")

SPIKE_DIR = Path(__file__).parent
EVIDENCE_DIR = SPIKE_DIR / "evidence"
MODEL = "gpt-4.1"


# ── Tool definition ─────────────────────────────────────────────


class WriteEvidenceParams(BaseModel):
    label: str = Field(description="A label to identify which test called this tool")


def make_tool(test_name: str):
    from copilot import define_tool

    @define_tool(
        name="write_evidence",
        description=(
            "Writes a proof-of-access marker file. "
            "You MUST call this tool with label='hello'."
        ),
    )
    def write_evidence(params: WriteEvidenceParams) -> str:
        try:
            evidence_file = EVIDENCE_DIR / f"evidence_{test_name}.txt"
            payload = {
                "test": test_name,
                "label": params.label,
                "timestamp": time.time(),
            }
            evidence_file.write_text(json.dumps(payload, indent=2))
            logger.info(">>> TOOL HANDLER EXECUTED [%s] label=%s", test_name, params.label)
            return f"Evidence written successfully for {test_name}."
        except Exception as e:
            logger.error(">>> TOOL HANDLER ERROR: %s", traceback.format_exc())
            return f"Error: {e}"

    return write_evidence


# ── Helpers ──────────────────────────────────────────────────────


async def send_and_wait(session, prompt: str, timeout: float = 45.0) -> str:
    done = asyncio.Event()
    result_text = ""

    def handler(event):
        nonlocal result_text
        try:
            etype = event.type.value if hasattr(event.type, "value") else str(event.type)
        except Exception:
            etype = str(getattr(event, "type", "unknown"))

        # Log everything (defensive)
        data_preview = ""
        try:
            if hasattr(event, "data") and event.data is not None:
                if hasattr(event.data, "content") and event.data.content:
                    data_preview = str(event.data.content)[:150]
                elif hasattr(event.data, "name"):
                    data_preview = f"name={event.data.name}"
                else:
                    data_preview = str(event.data)[:100]
        except Exception:
            pass
        logger.info("  [EVENT] %s %s", etype, data_preview)

        try:
            if etype == "assistant.message" and hasattr(event, "data") and event.data is not None:
                content = getattr(event.data, "content", None)
                if content:
                    result_text = content
            elif etype == "session.idle":
                done.set()
        except Exception as e:
            logger.debug("  [EVENT handler error] %s", e)

    session.on(handler)
    await session.send({"prompt": prompt})
    await asyncio.wait_for(done.wait(), timeout=timeout)
    return result_text


# ── Test A: Main agent (control) ────────────────────────────────


async def test_main_agent():
    test_name = "main_agent"
    logger.info("=" * 60)
    logger.info("TEST A: Main agent + session-level tool")
    logger.info("=" * 60)

    from copilot import CopilotClient, PermissionHandler

    tool = make_tool(test_name)
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            {
                "session_id": f"spike-a-{int(time.time())}",
                "model": MODEL,
                "tools": [tool],
                "on_permission_request": PermissionHandler.approve_all,
            }
        )

        result = await send_and_wait(
            session,
            "Call the write_evidence tool with label='main_test'. Do NOT use bash.",
        )

        evidence = EVIDENCE_DIR / f"evidence_{test_name}.txt"
        passed = evidence.exists()
        logger.info("TEST A: %s", "PASS" if passed else "FAIL")
        if passed:
            logger.info("  Evidence: %s", evidence.read_text()[:200])
        logger.info("  Response: %s", result[:200])
        return passed
    finally:
        await client.stop()


# ── Test B: Sub-agent with tools=["write_evidence"] ─────────────


async def test_subagent_explicit():
    test_name = "subagent_explicit"
    logger.info("=" * 60)
    logger.info("TEST B: Sub-agent with tools=['write_evidence']")
    logger.info("=" * 60)

    from copilot import CopilotClient, PermissionHandler

    tool = make_tool(test_name)
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            {
                "session_id": f"spike-b-{int(time.time())}",
                "model": MODEL,
                "tools": [tool],
                "custom_agents": [
                    {
                        "name": "evidence_writer",
                        "description": "Writes evidence by calling write_evidence tool.",
                        "prompt": (
                            "You are evidence_writer. Your ONLY job: "
                            "call write_evidence tool with label='subagent_explicit_test'. "
                            "Do NOT use bash. Do NOT explain. Just call the tool."
                        ),
                        "tools": ["write_evidence"],
                        "infer": True,
                    }
                ],
                "on_permission_request": PermissionHandler.approve_all,
            }
        )

        result = await send_and_wait(
            session,
            "Use the evidence_writer agent to write evidence now.",
            timeout=60,
        )

        evidence = EVIDENCE_DIR / f"evidence_{test_name}.txt"
        passed = evidence.exists()
        logger.info("TEST B: %s", "PASS" if passed else "FAIL")
        if passed:
            logger.info("  Evidence: %s", evidence.read_text()[:200])
        logger.info("  Response: %s", result[:200])
        return passed
    finally:
        await client.stop()


# ── Test C: Sub-agent with tools omitted (inherit all) ──────────


async def test_subagent_inherit():
    test_name = "subagent_inherit"
    logger.info("=" * 60)
    logger.info("TEST C: Sub-agent with tools=None (inherit all)")
    logger.info("=" * 60)

    from copilot import CopilotClient, PermissionHandler

    tool = make_tool(test_name)
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            {
                "session_id": f"spike-c-{int(time.time())}",
                "model": MODEL,
                "tools": [tool],
                "custom_agents": [
                    {
                        "name": "writer_v2",
                        "description": "Writes evidence by calling write_evidence tool.",
                        "prompt": (
                            "You are writer_v2. Your ONLY job: "
                            "call write_evidence tool with label='inherit_test'. "
                            "Do NOT use bash. Do NOT explain. Just call the tool."
                        ),
                        # tools omitted → should inherit all per docs
                        "infer": True,
                    }
                ],
                "on_permission_request": PermissionHandler.approve_all,
            }
        )

        result = await send_and_wait(
            session,
            "Use the writer_v2 agent to write evidence now.",
            timeout=60,
        )

        evidence = EVIDENCE_DIR / f"evidence_{test_name}.txt"
        passed = evidence.exists()
        logger.info("TEST C: %s", "PASS" if passed else "FAIL")
        if passed:
            logger.info("  Evidence: %s", evidence.read_text()[:200])
        logger.info("  Response: %s", result[:200])
        return passed
    finally:
        await client.stop()


# ── Main ─────────────────────────────────────────────────────────


async def main():
    EVIDENCE_DIR.mkdir(exist_ok=True)
    for f in EVIDENCE_DIR.iterdir():
        f.unlink()

    results = {}

    try:
        results["A_main_agent"] = await test_main_agent()
    except Exception as e:
        logger.error("TEST A crashed: %s", e)
        results["A_main_agent"] = False

    try:
        results["B_subagent_explicit"] = await test_subagent_explicit()
    except Exception as e:
        logger.error("TEST B crashed: %s", e)
        results["B_subagent_explicit"] = False

    try:
        results["C_subagent_inherit"] = await test_subagent_inherit()
    except Exception as e:
        logger.error("TEST C crashed: %s", e)
        results["C_subagent_inherit"] = False

    logger.info("=" * 60)
    logger.info("FINAL RESULTS")
    logger.info("=" * 60)
    for name, passed in results.items():
        logger.info("  %s %s", "PASS" if passed else "FAIL", name)

    # Write summary
    summary_file = EVIDENCE_DIR / "summary.json"
    summary_file.write_text(json.dumps(results, indent=2))
    logger.info("Summary written to %s", summary_file)


if __name__ == "__main__":
    asyncio.run(main())

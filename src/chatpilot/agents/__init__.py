"""Agent registry — module-level registry for all agents."""

from __future__ import annotations

from chatpilot.agents.base import AgentRegistry, BaseAgent

agent_registry: AgentRegistry = {}


def register_agent(agent: BaseAgent) -> None:
    agent_registry[agent.name] = agent


def get_agent(name: str) -> BaseAgent | None:
    return agent_registry.get(name)


def list_agents() -> list[str]:
    return list(agent_registry.keys())

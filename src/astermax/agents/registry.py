from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    role: str
    raw: dict[str, Any]


class AgentRegistry:
    def __init__(self, definitions: dict[str, AgentDefinition]) -> None:
        self._definitions = definitions

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentRegistry":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("Unsupported agent registry version.")

        definitions: dict[str, AgentDefinition] = {}
        for raw in payload.get("agents", []):
            agent_id = raw["id"]
            if agent_id in definitions:
                raise ValueError(f"Duplicate agent id: {agent_id}")
            definitions[agent_id] = AgentDefinition(
                agent_id=agent_id,
                name=raw["name"],
                role=raw["role"],
                raw=raw,
            )

        expected = {f"A{i}" for i in range(13)}
        missing = expected.difference(definitions)
        if missing:
            raise ValueError(f"Missing required agents: {sorted(missing)}")
        return cls(definitions)

    def get(self, agent_id: str) -> AgentDefinition:
        return self._definitions[agent_id]

    def all(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from astermax.solver.contracts import SolverCapabilityV1, SolverRequestV1, SolverRunManifestV1


class SolverAdapter(Protocol):
    """Backend boundary. Implementations execute solver work; agents do not."""

    def capability(self) -> SolverCapabilityV1:
        ...

    def execute(self, request: SolverRequestV1, run_directory: Path) -> SolverRunManifestV1:
        ...

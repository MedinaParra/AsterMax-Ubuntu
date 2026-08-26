from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from astermax.solver.contracts import ArtifactDigestV1, SolverRunManifestV1, SolverTermination


def artifact(path: str = "output/result.vtu") -> ArtifactDigestV1:
    return ArtifactDigestV1(relative_path=path, sha256="a" * 64, byte_size=10)


def test_success_manifest_requires_output_artifact() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        SolverRunManifestV1(
            run_id="run-1",
            request_id="req-1",
            backend_id="code_aster_wsl2",
            backend_version="x",
            worker_id="wsl2:aster",
            started_at=now,
            finished_at=now,
            termination=SolverTermination.SUCCEEDED,
        )


def test_manifest_rejects_time_reversal() -> None:
    with pytest.raises(ValidationError):
        SolverRunManifestV1(
            run_id="run-1",
            request_id="req-1",
            backend_id="code_aster_wsl2",
            backend_version="x",
            worker_id="wsl2:aster",
            started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            termination=SolverTermination.FAILED,
        )

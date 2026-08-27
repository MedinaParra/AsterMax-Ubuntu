from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .fea.selections import SurfaceSignature


class AsterMaxProjectError(RuntimeError):
    pass


@dataclass(frozen=True)
class AsterMaxProject:
    schema: str
    geometry_step: str
    length_unit: str
    mesh_family: str
    mesh_size_mm: float
    young_modulus_mpa: float
    poisson_ratio: float
    support: SurfaceSignature
    load_surface: SurfaceSignature
    resultant_n: tuple[float, float, float]
    geometry_sha256: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["support"] = self.support.to_dict()
        data["load_surface"] = self.load_surface.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AsterMaxProject":
        if data.get("schema") != "AsterMaxProjectV1":
            raise AsterMaxProjectError("unsupported .astermax project schema")
        project = cls(
            schema="AsterMaxProjectV1",
            geometry_step=str(data["geometry_step"]),
            length_unit=str(data["length_unit"]),
            mesh_family=str(data["mesh_family"]),
            mesh_size_mm=float(data["mesh_size_mm"]),
            young_modulus_mpa=float(data["young_modulus_mpa"]),
            poisson_ratio=float(data["poisson_ratio"]),
            support=SurfaceSignature.from_dict(data["support"]),
            load_surface=SurfaceSignature.from_dict(data["load_surface"]),
            resultant_n=tuple(float(v) for v in data["resultant_n"]),
            geometry_sha256=str(data["geometry_sha256"]),
        )
        project.validate()
        return project

    def validate(self) -> None:
        if self.length_unit != "mm":
            raise AsterMaxProjectError("PMV project length_unit must be mm")
        if self.mesh_family != "TET10":
            raise AsterMaxProjectError("PMV project mesh_family must be TET10")
        if not np.isfinite(self.mesh_size_mm) or self.mesh_size_mm <= 0.0:
            raise AsterMaxProjectError("mesh_size_mm must be finite and positive")
        if not np.isfinite(self.young_modulus_mpa) or self.young_modulus_mpa <= 0.0:
            raise AsterMaxProjectError("young_modulus_mpa must be finite and positive")
        if not np.isfinite(self.poisson_ratio) or not (-1.0 < self.poisson_ratio < 0.5):
            raise AsterMaxProjectError("poisson_ratio must satisfy -1 < nu < 0.5")
        load = np.asarray(self.resultant_n, dtype=float)
        if load.shape != (3,) or not np.all(np.isfinite(load)) or float(np.linalg.norm(load)) == 0.0:
            raise AsterMaxProjectError("resultant_n must contain three finite values and be non-zero")
        if self.support.fingerprint_sha256 == self.load_surface.fingerprint_sha256:
            raise AsterMaxProjectError("support and load surface must be distinct")
        if len(self.geometry_sha256) != 64:
            raise AsterMaxProjectError("geometry_sha256 must be a SHA-256 hex digest")


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    digest = hashlib.sha256()
    with p.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_project(path: str | Path, project: AsterMaxProject) -> Path:
    project.validate()
    output = Path(path)
    if output.suffix.lower() != ".astermax":
        raise AsterMaxProjectError("project files must use the .astermax extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(project.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def read_project(path: str | Path) -> AsterMaxProject:
    p = Path(path)
    if p.suffix.lower() != ".astermax" or not p.is_file():
        raise AsterMaxProjectError("project path must be an existing .astermax file")
    return AsterMaxProject.from_dict(json.loads(p.read_text(encoding="utf-8")))


def resolve_project_geometry(project_path: str | Path, project: AsterMaxProject) -> Path:
    base = Path(project_path).resolve().parent
    geometry = (base / project.geometry_step).resolve()
    if not geometry.is_file():
        raise AsterMaxProjectError(f"project STEP geometry not found: {geometry}")
    if geometry.suffix.lower() not in {".step", ".stp"}:
        raise AsterMaxProjectError("project geometry must be STEP/STP")
    actual = sha256_file(geometry)
    if actual != project.geometry_sha256:
        raise AsterMaxProjectError("STEP geometry hash does not match .astermax project provenance")
    return geometry

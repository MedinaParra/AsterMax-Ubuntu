from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from astermax.credibility import canonical_sha256
from .credibility_visualization import validate_c3_2_payload


class NativeCredibilityError(ValueError):
    pass


@dataclass(frozen=True)
class NativeRefinementRow:
    mesh_size_mm: float
    rms_relative_error: float
    maximum_relative_error: float


@dataclass(frozen=True)
class NativeCredibilitySnapshot:
    schema: str
    source_schema: str
    step_sha256: str
    section_sha256: str
    witness_sha256: str
    area_mm2: float
    analytical_sigma_mpa: float
    refinement_rows: tuple[NativeRefinementRow, ...]
    fixture_convergence_claim: bool
    arbitrary_model_convergence: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_boundary: str
    snapshot_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("snapshot_sha256")
        return payload


def build_native_credibility_snapshot(payload: dict[str, Any]) -> NativeCredibilitySnapshot:
    """Map C3.2 evidence into a native-display contract without widening claims."""
    validate_c3_2_payload(payload)
    provenance = payload["provenance"]
    witness = payload["cad_analytical_witness"]
    claims = payload["claims"]
    analytical_sigma = float(witness["analytical_sigma_mpa"])
    if analytical_sigma == 0.0:
        raise NativeCredibilityError("analytical_sigma_mpa must be non-zero")

    rows: list[NativeRefinementRow] = []
    for item in payload["levels"]:
        level = item["level"]
        rows.append(
            NativeRefinementRow(
                mesh_size_mm=float(level["mesh_size_mm"]),
                rms_relative_error=abs(float(level["rms_error_mpa"])) / abs(analytical_sigma),
                maximum_relative_error=float(level["maximum_relative_error"]),
            )
        )
    if len(rows) != 3 or not (rows[0].mesh_size_mm > rows[1].mesh_size_mm > rows[2].mesh_size_mm > 0.0):
        raise NativeCredibilityError("native snapshot requires three coarse-to-fine levels")

    values = [row.rms_relative_error for row in rows] + [row.maximum_relative_error for row in rows]
    if any(value < 0.0 for value in values):
        raise NativeCredibilityError("relative errors must be non-negative")

    core = {
        "schema": "AsterMaxNativeCredibilitySnapshotV1",
        "source_schema": payload["schema"],
        "step_sha256": provenance["source_sha256"],
        "section_sha256": provenance["section_sha256"],
        "witness_sha256": witness["witness_sha256"],
        "area_mm2": float(witness["area_mm2"]),
        "analytical_sigma_mpa": analytical_sigma,
        "refinement_rows": [asdict(row) for row in rows],
        "fixture_convergence_claim": bool(claims["stress_convergence_for_this_axial_fixture"]),
        "arbitrary_model_convergence": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
        "evidence_boundary": "AXIAL_VERIFICATION_FIXTURE_ONLY_NOT_ARBITRARY_MODEL_CONVERGENCE_NOT_INDUSTRIAL_VALIDATION_NOT_ANSYS_EQUIVALENCE",
    }
    digest = canonical_sha256(core)
    return NativeCredibilitySnapshot(
        schema=core["schema"],
        source_schema=core["source_schema"],
        step_sha256=core["step_sha256"],
        section_sha256=core["section_sha256"],
        witness_sha256=core["witness_sha256"],
        area_mm2=core["area_mm2"],
        analytical_sigma_mpa=core["analytical_sigma_mpa"],
        refinement_rows=tuple(rows),
        fixture_convergence_claim=core["fixture_convergence_claim"],
        arbitrary_model_convergence=False,
        industrial_validation=False,
        ansys_equivalence=False,
        evidence_boundary=core["evidence_boundary"],
        snapshot_sha256=digest,
    )


def load_native_credibility_snapshot(path: str | Path) -> NativeCredibilitySnapshot:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NativeCredibilityError("credibility evidence root must be a JSON object")
    return build_native_credibility_snapshot(payload)


def install_native_credibility_tab(notebook: Any) -> Any:
    """Install a Tk/ttk Evidence tab that renders only validated C3.2 evidence."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    panel = ttk.Frame(notebook, padding=18)
    notebook.add(panel, text="Credibility")
    panel.columnconfigure(0, weight=1)

    title = ttk.Label(panel, text="Evidence Chain", font=("Segoe UI", 16, "bold"))
    title.grid(row=0, column=0, sticky="w")
    ttk.Label(
        panel,
        text="Load a C3.2 evidence JSON. This tab never upgrades fixture evidence to arbitrary-model, industrial, or ANSYS-equivalence claims.",
        wraplength=780,
    ).grid(row=1, column=0, sticky="ew", pady=(2, 12))

    identity_var = tk.StringVar(value="No verified evidence loaded.")
    analytical_var = tk.StringVar(value="CAD analytical witness: —")
    claim_var = tk.StringVar(value="Fixture claim: —")
    boundary_var = tk.StringVar(value="Boundary: no evidence loaded")
    ttk.Label(panel, textvariable=identity_var, wraplength=780).grid(row=2, column=0, sticky="w", pady=4)
    ttk.Label(panel, textvariable=analytical_var).grid(row=3, column=0, sticky="w", pady=4)
    ttk.Label(panel, textvariable=claim_var, font=("Segoe UI", 11, "bold")).grid(row=4, column=0, sticky="w", pady=4)

    tree = ttk.Treeview(panel, columns=("mesh", "rms", "max"), show="headings", height=4)
    for key, label, width in (("mesh", "Mesh [mm]", 120), ("rms", "RMS error", 140), ("max", "Max error", 140)):
        tree.heading(key, text=label)
        tree.column(key, width=width, anchor="center")
    tree.grid(row=5, column=0, sticky="ew", pady=(10, 8))
    ttk.Label(panel, textvariable=boundary_var, wraplength=780).grid(row=6, column=0, sticky="ew", pady=4)

    def load_evidence() -> None:
        path = filedialog.askopenfilename(filetypes=[("C3.2 evidence JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            snapshot = load_native_credibility_snapshot(path)
        except Exception as exc:
            messagebox.showerror("AsterMax credibility evidence", str(exc))
            return
        identity_var.set(
            f"STEP {snapshot.step_sha256[:16]}…  |  OCC section {snapshot.section_sha256[:16]}…  |  witness {snapshot.witness_sha256[:16]}…"
        )
        analytical_var.set(f"CAD section {snapshot.area_mm2:.6g} mm²  |  analytical σ = F/A = {snapshot.analytical_sigma_mpa:.6g} MPa")
        claim_var.set("Fixture stress convergence: " + ("PERMITTED" if snapshot.fixture_convergence_claim else "BLOCKED"))
        boundary_var.set("Boundary: arbitrary-model convergence = false · industrial validation = false · ANSYS equivalence = false")
        for item in tree.get_children():
            tree.delete(item)
        for row in snapshot.refinement_rows:
            tree.insert("", "end", values=(f"{row.mesh_size_mm:g}", f"{100*row.rms_relative_error:.4f}%", f"{100*row.maximum_relative_error:.4f}%"))

    ttk.Button(panel, text="Load verified C3.2 evidence", command=load_evidence).grid(row=7, column=0, sticky="ew", pady=(14, 0))
    return panel

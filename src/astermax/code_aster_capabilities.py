from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class CapabilityStatus(str, Enum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    SCHEMA_ONLY = "SCHEMA_ONLY"
    IMPLEMENTED_UNVERIFIED = "IMPLEMENTED_UNVERIFIED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True)
class VariableSpec:
    id: str
    engineering_name: str
    ui_path: str
    operator: str
    keyword: str
    value_type: str
    unit: str | None = None
    default: object | None = None
    required: bool = False
    constraints: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()
    doc_ref: str = ""
    verification_case: str = ""


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    label: str
    category: str
    gui_path: str
    roadmap_phase: str
    status: CapabilityStatus
    operators: tuple[str, ...]
    variables: tuple[VariableSpec, ...] = ()
    verification_gate: str = ""
    notes: str = ""

    @property
    def gui_selectable(self) -> bool:
        return self.status in {CapabilityStatus.IMPLEMENTED_UNVERIFIED, CapabilityStatus.VERIFIED}

    @property
    def solver_claim_allowed(self) -> bool:
        return self.status is CapabilityStatus.VERIFIED


def _v(
    id: str,
    name: str,
    ui: str,
    operator: str,
    keyword: str,
    value_type: str,
    *,
    unit: str | None = None,
    default: object | None = None,
    required: bool = False,
    constraints: tuple[str, ...] = (),
    dependencies: tuple[str, ...] = (),
    incompatible_with: tuple[str, ...] = (),
    doc_ref: str = "",
    verification_case: str = "",
) -> VariableSpec:
    return VariableSpec(
        id=id,
        engineering_name=name,
        ui_path=ui,
        operator=operator,
        keyword=keyword,
        value_type=value_type,
        unit=unit,
        default=default,
        required=required,
        constraints=constraints,
        dependencies=dependencies,
        incompatible_with=incompatible_with,
        doc_ref=doc_ref,
        verification_case=verification_case,
    )


CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        id="structural.linear_static_3d",
        label="Static Structural · Linear 3D",
        category="Structural",
        gui_path="Analysis/Static Structural/Linear",
        roadmap_phase="C8-C11",
        status=CapabilityStatus.IMPLEMENTED_UNVERIFIED,
        operators=("LIRE_MAILLAGE", "AFFE_MODELE", "DEFI_MATERIAU", "AFFE_MATERIAU", "AFFE_CHAR_MECA", "MECA_STATIQUE", "CALC_CHAMP", "IMPR_RESU"),
        variables=(
            _v("material.E", "Young's modulus", "Model/Materials/Elastic/E", "DEFI_MATERIAU", "ELAS/E", "float", unit="MPa", required=True, constraints=("E > 0",), doc_ref="U4.43.01", verification_case="uniaxial_prism"),
            _v("material.nu", "Poisson ratio", "Model/Materials/Elastic/nu", "DEFI_MATERIAU", "ELAS/NU", "float", required=True, constraints=("-1 < nu < 0.5",), doc_ref="U4.43.01", verification_case="uniaxial_prism"),
            _v("bc.displacement.dx", "Imposed displacement X", "Loads/Displacement/DX", "AFFE_CHAR_MECA", "DDL_IMPO/DX", "float", unit="mm", doc_ref="U4.44.01"),
            _v("bc.displacement.dy", "Imposed displacement Y", "Loads/Displacement/DY", "AFFE_CHAR_MECA", "DDL_IMPO/DY", "float", unit="mm", doc_ref="U4.44.01"),
            _v("bc.displacement.dz", "Imposed displacement Z", "Loads/Displacement/DZ", "AFFE_CHAR_MECA", "DDL_IMPO/DZ", "float", unit="mm", doc_ref="U4.44.01"),
            _v("load.traction.fx", "Surface traction X", "Loads/Surface Traction/FX", "AFFE_CHAR_MECA", "FORCE_FACE/FX", "float", unit="N/mm^2", doc_ref="U4.44.01", verification_case="uniaxial_prism"),
            _v("load.traction.fy", "Surface traction Y", "Loads/Surface Traction/FY", "AFFE_CHAR_MECA", "FORCE_FACE/FY", "float", unit="N/mm^2", doc_ref="U4.44.01"),
            _v("load.traction.fz", "Surface traction Z", "Loads/Surface Traction/FZ", "AFFE_CHAR_MECA", "FORCE_FACE/FZ", "float", unit="N/mm^2", doc_ref="U4.44.01"),
            _v("solver.memory_mb", "Memory limit", "Solution/Solver/Memory", "run_aster", "memory_limit", "int", unit="MB", default=2048, constraints=("128 <= value <= 1048576",), doc_ref="run_aster/export"),
            _v("solver.time_limit_s", "Time limit", "Solution/Solver/Time", "run_aster", "time_limit", "int", unit="s", default=300, constraints=("1 <= value <= 86400",), doc_ref="run_aster/export"),
        ),
        verification_gate="Real Code_Aster solve + displacement + reaction equilibrium + analytical stress",
        notes="Command generation and MED semantics exist. Genuine native Code_Aster numerical verification is not yet complete.",
    ),
    CapabilitySpec(
        id="structural.modal",
        label="Modal Analysis",
        category="Structural Dynamics",
        gui_path="Analysis/Modal",
        roadmap_phase="C13",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("ASSE_MATRICE", "CALC_MODES"),
        variables=(
            _v("material.rho", "Density", "Model/Materials/Density", "DEFI_MATERIAU", "ELAS/RHO", "float", unit="kg/mm^3", required=True, constraints=("rho > 0",), doc_ref="U4.43.01"),
            _v("modal.fmin", "Minimum frequency", "Analysis/Modal/Frequency Min", "CALC_MODES", "CALC_FREQ/FREQ_MIN", "float", unit="Hz", default=0.0, constraints=("value >= 0",)),
            _v("modal.fmax", "Maximum frequency", "Analysis/Modal/Frequency Max", "CALC_MODES", "CALC_FREQ/FREQ_MAX", "float", unit="Hz", constraints=("value > fmin",)),
            _v("modal.n_modes", "Number of modes", "Analysis/Modal/Mode Count", "CALC_MODES", "CALC_FREQ/NMAX_FREQ", "int", default=10, constraints=("value >= 1",)),
        ),
        verification_gate="Beam/cantilever analytical eigenfrequency benchmark",
    ),
    CapabilitySpec(
        id="structural.buckling",
        label="Linear Buckling / Stability",
        category="Structural",
        gui_path="Analysis/Buckling",
        roadmap_phase="C14",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("MECA_STATIQUE", "CALC_MATR_ELEM", "CALC_MODES"),
        variables=(
            _v("buckling.n_modes", "Buckling mode count", "Analysis/Buckling/Mode Count", "CALC_MODES", "CALC_CHAR_CRIT/NMAX_CHAR_CRIT", "int", default=5, constraints=("value >= 1",)),
        ),
        verification_gate="Euler column critical load benchmark",
    ),
    CapabilitySpec(
        id="structural.nonlinear_static",
        label="Nonlinear Static Structural",
        category="Structural",
        gui_path="Analysis/Static Structural/Nonlinear",
        roadmap_phase="C15-C16",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("STAT_NON_LINE",),
        variables=(
            _v("nonlinear.geom", "Geometric nonlinearity", "Analysis/Nonlinear/Large Deformation", "STAT_NON_LINE", "COMPORTEMENT/DEFORMATION", "enum", default="PETIT"),
            _v("nonlinear.max_iter", "Maximum Newton iterations", "Analysis/Nonlinear/Max Iterations", "STAT_NON_LINE", "NEWTON/ITER_GLOB_MAXI", "int", default=20, constraints=("value >= 1",)),
            _v("nonlinear.residual", "Global residual tolerance", "Analysis/Nonlinear/Residual", "STAT_NON_LINE", "CONVERGENCE/RESI_GLOB_RELA", "float", default=1.0e-6, constraints=("0 < value < 1",)),
            _v("nonlinear.initial_steps", "Initial load steps", "Analysis/Nonlinear/Steps", "DEFI_LIST_REEL", "INTERVALLE/NOMBRE", "int", default=10, constraints=("value >= 1",)),
        ),
        verification_gate="Material point + large-displacement structural benchmarks",
    ),
    CapabilitySpec(
        id="structural.contact",
        label="Contact",
        category="Connections",
        gui_path="Model/Connections/Contact",
        roadmap_phase="C17",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("DEFI_CONTACT", "STAT_NON_LINE"),
        variables=(
            _v("contact.type", "Contact type", "Connections/Contact/Type", "DEFI_CONTACT", "ZONE/CONTACT", "enum", default="OUI"),
            _v("contact.friction", "Friction enabled", "Connections/Contact/Friction", "DEFI_CONTACT", "ZONE/FROTTEMENT", "bool", default=False),
            _v("contact.mu", "Friction coefficient", "Connections/Contact/Friction Coefficient", "DEFI_CONTACT", "ZONE/COULOMB", "float", default=0.2, constraints=("value >= 0",), dependencies=("contact.friction",)),
        ),
        verification_gate="Patch contact + sliding Coulomb benchmarks",
    ),
    CapabilitySpec(
        id="dynamic.harmonic",
        label="Harmonic Response",
        category="Structural Dynamics",
        gui_path="Analysis/Harmonic",
        roadmap_phase="C19",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("DYNA_VIBRA",),
        variables=(
            _v("harmonic.fmin", "Start frequency", "Analysis/Harmonic/Start Frequency", "DYNA_VIBRA", "FREQ", "float", unit="Hz", required=True, constraints=("value >= 0",)),
            _v("harmonic.fmax", "End frequency", "Analysis/Harmonic/End Frequency", "DYNA_VIBRA", "FREQ", "float", unit="Hz", required=True, constraints=("value > harmonic.fmin",)),
            _v("harmonic.points", "Frequency points", "Analysis/Harmonic/Points", "DEFI_LIST_REEL", "NOMBRE", "int", default=100, constraints=("value >= 2",)),
        ),
        verification_gate="SDOF analytical frequency response",
    ),
    CapabilitySpec(
        id="dynamic.transient",
        label="Transient Structural Dynamics",
        category="Structural Dynamics",
        gui_path="Analysis/Transient Dynamic",
        roadmap_phase="C18",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("DYNA_LINE", "DYNA_NON_LINE"),
        variables=(
            _v("time.dt", "Time step", "Analysis/Transient/Time Step", "DEFI_LIST_REEL", "PAS", "float", unit="s", required=True, constraints=("value > 0",)),
            _v("time.t_end", "End time", "Analysis/Transient/End Time", "DEFI_LIST_REEL", "JUSQU_A", "float", unit="s", required=True, constraints=("value > 0",)),
            _v("damping.alpha", "Rayleigh alpha", "Analysis/Transient/Damping Alpha", "COMB_MATR_ASSE", "AMOR_ALPHA", "float", default=0.0),
            _v("damping.beta", "Rayleigh beta", "Analysis/Transient/Damping Beta", "COMB_MATR_ASSE", "AMOR_BETA", "float", default=0.0),
        ),
        verification_gate="SDOF free/forced vibration benchmark",
    ),
    CapabilitySpec(
        id="thermal.steady",
        label="Steady-State Thermal",
        category="Thermal",
        gui_path="Analysis/Thermal/Steady State",
        roadmap_phase="C20",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("THER_LINEAIRE",),
        variables=(
            _v("thermal.lambda", "Thermal conductivity", "Model/Materials/Thermal Conductivity", "DEFI_MATERIAU", "THER/LAMBDA", "float", unit="W/(mm*K)", required=True, constraints=("value > 0",)),
            _v("thermal.temperature", "Imposed temperature", "Loads/Thermal/Temperature", "AFFE_CHAR_THER", "TEMP_IMPO/TEMP", "float", unit="K"),
            _v("thermal.flux", "Normal heat flux", "Loads/Thermal/Heat Flux", "AFFE_CHAR_THER", "FLUX_REP/FLUN", "float", unit="W/mm^2"),
            _v("thermal.h", "Convection coefficient", "Loads/Thermal/Convection/h", "AFFE_CHAR_THER", "ECHANGE/COEF_H", "float", unit="W/(mm^2*K)", constraints=("value >= 0",)),
            _v("thermal.t_ext", "External temperature", "Loads/Thermal/Convection/T_ext", "AFFE_CHAR_THER", "ECHANGE/TEMP_EXT", "float", unit="K"),
        ),
        verification_gate="1-D conduction and convection analytical benchmarks",
    ),
    CapabilitySpec(
        id="thermal.transient",
        label="Transient Thermal",
        category="Thermal",
        gui_path="Analysis/Thermal/Transient",
        roadmap_phase="C20",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("THER_NON_LINE",),
        variables=(
            _v("thermal.cp", "Specific heat", "Model/Materials/Specific Heat", "DEFI_MATERIAU", "THER/CP", "float", unit="J/(kg*K)", required=True, constraints=("value > 0",)),
            _v("thermal.rho", "Density", "Model/Materials/Density", "DEFI_MATERIAU", "THER/RHO_CP", "float", required=True, constraints=("value > 0",)),
            _v("time.dt", "Thermal time step", "Analysis/Thermal/Transient/Time Step", "DEFI_LIST_REEL", "PAS", "float", unit="s", required=True, constraints=("value > 0",)),
        ),
        verification_gate="Transient slab conduction benchmark",
    ),
    CapabilitySpec(
        id="coupled.thermomechanical",
        label="Thermo-Mechanical",
        category="Coupled Physics",
        gui_path="Analysis/Thermo-Mechanical",
        roadmap_phase="C21",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("THER_LINEAIRE", "MECA_STATIQUE", "AFFE_VARC"),
        variables=(
            _v("material.alpha", "Thermal expansion coefficient", "Model/Materials/Thermal Expansion", "DEFI_MATERIAU", "ELAS/ALPHA", "float", unit="1/K", required=True),
            _v("coupling.reference_temperature", "Reference temperature", "Analysis/Thermo-Mechanical/Reference Temperature", "AFFE_VARC", "VALE_REF", "float", unit="K", required=True),
        ),
        verification_gate="Restrained thermal expansion analytical benchmark",
    ),
    CapabilitySpec(
        id="fracture.xfem",
        label="Fracture / XFEM",
        category="Fracture",
        gui_path="Analysis/Fracture/XFEM",
        roadmap_phase="C24",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("DEFI_FISS_XFEM", "MODI_MODELE_XFEM", "CALC_G", "POST_K1_K2_K3"),
        variables=(
            _v("fracture.crack_type", "Crack geometry type", "Model/Crack/Type", "DEFI_FISS_XFEM", "FORM_FISS", "enum", required=True),
            _v("fracture.g", "Energy release rate", "Results/Fracture/G", "CALC_G", "OPTION", "enum", default="G"),
        ),
        verification_gate="Official Code_Aster fracture validation cases",
    ),
    CapabilitySpec(
        id="fatigue.structural",
        label="Structural Fatigue",
        category="Fatigue",
        gui_path="Analysis/Fatigue",
        roadmap_phase="C23",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("CALC_FATIGUE", "POST_FATIGUE"),
        variables=(
            _v("fatigue.method", "Fatigue method", "Analysis/Fatigue/Method", "CALC_FATIGUE", "TYPE_CALCUL", "enum", required=True),
            _v("fatigue.sn_curve", "S-N curve", "Model/Materials/Fatigue/S-N", "DEFI_MATERIAU", "FATIGUE", "table", required=True),
        ),
        verification_gate="Published S-N and multiaxial fatigue benchmarks",
    ),
    CapabilitySpec(
        id="acoustic.linear",
        label="Linear Acoustics",
        category="Acoustics",
        gui_path="Analysis/Acoustic",
        roadmap_phase="C27",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("AFFE_MODELE", "DYNA_VIBRA"),
        variables=(),
        verification_gate="Acoustic cavity eigenfrequency benchmark",
    ),
    CapabilitySpec(
        id="geomechanics.basic",
        label="Geomechanics",
        category="Specialized",
        gui_path="Analysis/Geomechanics",
        roadmap_phase="C27",
        status=CapabilityStatus.SCHEMA_ONLY,
        operators=("STAT_NON_LINE",),
        variables=(),
        verification_gate="Domain-specific Code_Aster validation cases",
    ),
)


def capability_by_id(capability_id: str) -> CapabilitySpec:
    matches = [item for item in CAPABILITIES if item.id == capability_id]
    if len(matches) != 1:
        raise KeyError(capability_id)
    return matches[0]


def iter_gui_tree() -> tuple[tuple[str, str, CapabilityStatus, bool, str], ...]:
    """Return a renderer-neutral analysis tree for the GUI.

    Every capability is visible. Only capabilities whose implementation exists are
    selectable. Visibility must never be interpreted as solver support.
    """
    return tuple((item.id, item.gui_path, item.status, item.gui_selectable, item.roadmap_phase) for item in CAPABILITIES)


def validate_registry(capabilities: Iterable[CapabilitySpec] = CAPABILITIES) -> None:
    items = tuple(capabilities)
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("CAPABILITY_ID_NOT_UNIQUE")
    variable_ids: set[tuple[str, str]] = set()
    for capability in items:
        if not capability.operators:
            raise ValueError(f"CAPABILITY_OPERATORS_EMPTY:{capability.id}")
        if capability.status is CapabilityStatus.VERIFIED and not capability.verification_gate:
            raise ValueError(f"VERIFIED_CAPABILITY_WITHOUT_GATE:{capability.id}")
        for variable in capability.variables:
            key = (capability.id, variable.id)
            if key in variable_ids:
                raise ValueError(f"VARIABLE_ID_NOT_UNIQUE:{capability.id}:{variable.id}")
            variable_ids.add(key)
            if not variable.operator or not variable.keyword or not variable.ui_path:
                raise ValueError(f"VARIABLE_MAPPING_INCOMPLETE:{capability.id}:{variable.id}")


validate_registry()

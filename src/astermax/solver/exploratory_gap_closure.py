from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_meshing import sha256_file


_RESULT_CLASS = "EXPLORATORY_NOT_FOR_ACCEPTANCE"
_REQUIRED_GROUPS = {
    "HUB",
    "SEGMENTS",
    "HUB_POSTERIOR_INTERFACE",
    "SEGMENT_POSTERIOR_INTERFACE",
    "HUB_INNER_BORE",
    "SEGMENT_OUTER_CLAMP",
}


class ExploratoryMaterialV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: str = Field(min_length=1)
    elastic_modulus_mpa: float = Field(gt=0)
    poisson_ratio: float = Field(gt=0, lt=0.5)
    evidence_class: str = Field(
        default="ASSUMPTION_EXPLORATORY",
        pattern=r"^ASSUMPTION_EXPLORATORY$",
    )


class ExploratoryGapClosureRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="ExploratoryGapClosureRequestV1",
        pattern=r"^ExploratoryGapClosureRequestV1$",
    )
    case_id: str = Field(min_length=1)
    mesh_path: str = Field(min_length=1)
    mesh_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mesh_evidence_path: str = Field(min_length=1)
    gap_mm: float = Field(ge=0)
    hub_material: ExploratoryMaterialV1
    segment_material: ExploratoryMaterialV1
    preload_per_bolt_kn: float = Field(gt=0)
    bolt_count: int = Field(default=30, gt=0)
    friction_coefficient: float = Field(ge=0, le=2)
    increments: int = Field(default=20, ge=2, le=200)
    result_class: str = Field(default=_RESULT_CLASS, pattern=f"^{_RESULT_CLASS}$")
    modelling_simplification: str = Field(
        default=(
            "Thirty discrete bolts are replaced by one equivalent uniform axial traction "
            "over SEGMENT_OUTER_CLAMP. This is not bolt-local pretension."
        ),
        min_length=1,
    )
    authentic_solver_authorized: bool = False

    @model_validator(mode="after")
    def preserve_quarantine(self) -> "ExploratoryGapClosureRequestV1":
        if self.authentic_solver_authorized:
            raise ValueError("exploratory GAP closure can never authorize authentic evidence")
        return self


class MeshClosureEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    result_class: str
    authentic_solver_authorized: bool
    mesh_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    coordinate_unit: str
    physical_groups: list[str]
    segment_outer_clamp_area_mm2: float = Field(gt=0)


class GeneratedGapClosurePackV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="GeneratedGapClosurePackV1",
        pattern=r"^GeneratedGapClosurePackV1$",
    )
    case_id: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mesh_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clamp_traction_mpa: float = Field(gt=0)
    total_equivalent_clamp_force_kn: float = Field(gt=0)
    comm_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    export_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_class: str = _RESULT_CLASS
    authentic_solver_authorized: bool = False
    output_rmed_name: str
    quarantine_reasons: list[str]


def _canonical_sha256(model: BaseModel) -> str:
    text = json.dumps(model.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_verified_mesh_evidence(
    request: ExploratoryGapClosureRequestV1,
) -> tuple[Path, MeshClosureEvidenceV1]:
    mesh_path = Path(request.mesh_path).expanduser().resolve()
    evidence_path = Path(request.mesh_evidence_path).expanduser().resolve()
    if not mesh_path.is_file():
        raise FileNotFoundError(mesh_path)
    if not evidence_path.is_file():
        raise FileNotFoundError(evidence_path)

    actual_mesh_sha = sha256_file(mesh_path)
    if actual_mesh_sha != request.mesh_sha256:
        raise ValueError(
            f"MED SHA-256 mismatch: expected {request.mesh_sha256}, got {actual_mesh_sha}"
        )

    try:
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence = MeshClosureEvidenceV1.model_validate(raw)
    except Exception as exc:
        raise ValueError("mesh execution evidence is malformed") from exc

    if evidence.mesh_sha256 != actual_mesh_sha:
        raise ValueError("mesh execution evidence SHA does not match MED")
    if evidence.result_class != _RESULT_CLASS or evidence.authentic_solver_authorized:
        raise ValueError("mesh evidence escaped exploratory quarantine")
    if evidence.coordinate_unit != "mm":
        raise ValueError("W2J requires millimetre MED coordinates")

    missing = sorted(_REQUIRED_GROUPS - set(evidence.physical_groups))
    if missing:
        raise ValueError(f"required physical groups missing: {missing}")
    return mesh_path, evidence


def equivalent_clamp_traction_mpa(
    *,
    preload_per_bolt_kn: float,
    bolt_count: int,
    clamp_area_mm2: float,
) -> tuple[float, float]:
    if preload_per_bolt_kn <= 0 or bolt_count <= 0 or clamp_area_mm2 <= 0:
        raise ValueError("preload, bolt count and clamp area must be positive")
    total_force_kn = preload_per_bolt_kn * bolt_count
    traction_mpa = total_force_kn * 1000.0 / clamp_area_mm2
    return traction_mpa, total_force_kn


def render_code_aster_comm(
    request: ExploratoryGapClosureRequestV1,
    *,
    clamp_traction_mpa: float,
) -> str:
    if clamp_traction_mpa <= 0:
        raise ValueError("clamp traction must be positive")
    # N-mm-MPa consistent unit system. Positive FX pushes the displaced segments
    # toward the authenticated hub interface for the W2E/W2J geometry convention.
    return f'''# ASTERMAX RESULT CLASS: {_RESULT_CLASS}
# CASE: {request.case_id}
# GAP_MM: {request.gap_mm:.12g}
# MODELLING SIMPLIFICATION: {request.modelling_simplification}
# This file is exploratory and MUST NOT be used as acceptance evidence.
DEBUT()

MAIL = LIRE_MAILLAGE(FORMAT='MED', UNITE=20)

MODELE = AFFE_MODELE(
    MAILLAGE=MAIL,
    AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'),
)

MAT_HUB = DEFI_MATERIAU(
    ELAS=_F(E={request.hub_material.elastic_modulus_mpa:.12g}, NU={request.hub_material.poisson_ratio:.12g}),
)
MAT_SEG = DEFI_MATERIAU(
    ELAS=_F(E={request.segment_material.elastic_modulus_mpa:.12g}, NU={request.segment_material.poisson_ratio:.12g}),
)

CHMAT = AFFE_MATERIAU(
    MAILLAGE=MAIL,
    AFFE=(
        _F(GROUP_MA='HUB', MATER=MAT_HUB),
        _F(GROUP_MA='SEGMENTS', MATER=MAT_SEG),
    ),
)

SUPPORT = AFFE_CHAR_MECA(
    MODELE=MODELE,
    DDL_IMPO=_F(GROUP_MA='HUB_INNER_BORE', DX=0.0, DY=0.0, DZ=0.0),
)

CLAMP = AFFE_CHAR_MECA(
    MODELE=MODELE,
    FORCE_FACE=_F(GROUP_MA='SEGMENT_OUTER_CLAMP', FX={clamp_traction_mpa:.12g}),
)

CONTACT = DEFI_CONTACT(
    MODELE=MODELE,
    FORMULATION='CONTINUE',
    FROTTEMENT='COULOMB',
    LISSAGE='OUI',
    ALGO_RESO_GEOM='POINT_FIXE',
    ALGO_RESO_CONT='POINT_FIXE',
    ALGO_RESO_FROT='POINT_FIXE',
    ZONE=_F(
        GROUP_MA_MAIT='HUB_POSTERIOR_INTERFACE',
        GROUP_MA_ESCL='SEGMENT_POSTERIOR_INTERFACE',
        CONTACT_INIT='NON',
        COULOMB={request.friction_coefficient:.12g},
    ),
)

RAMPE = DEFI_FONCTION(
    NOM_PARA='INST',
    VALE=(0.0, 0.0, 1.0, 1.0),
)
LINST = DEFI_LIST_REEL(
    DEBUT=0.0,
    INTERVALLE=_F(JUSQU_A=1.0, NOMBRE={request.increments}),
)

RESU = STAT_NON_LINE(
    MODELE=MODELE,
    CHAM_MATER=CHMAT,
    EXCIT=(
        _F(CHARGE=SUPPORT),
        _F(CHARGE=CLAMP, FONC_MULT=RAMPE),
    ),
    CONTACT=CONTACT,
    COMPORTEMENT=_F(TOUT='OUI', RELATION='ELAS'),
    INCREMENT=_F(LIST_INST=LINST),
    NEWTON=_F(MATRICE='TANGENTE', REAC_ITER=1),
    CONVERGENCE=_F(ITER_GLOB_MAXI=50, RESI_GLOB_RELA=1.0E-6),
)

RESU = CALC_CHAMP(
    reuse=RESU,
    RESULTAT=RESU,
    CONTRAINTE=('SIGM_ELNO',),
    CRITERES=('SIEQ_ELNO',),
)

IMPR_RESU(
    FORMAT='MED',
    UNITE=80,
    RESU=(
        _F(RESULTAT=RESU, NOM_CHAM=('DEPL', 'SIGM_ELNO', 'CONT_NOEU')),
    ),
)

FIN()
'''


def render_export(
    *,
    comm_name: str,
    mesh_name: str,
    output_rmed_name: str,
) -> str:
    return f'''P actions make_etude
P version stable
P memory_limit 4096
F comm {comm_name} D 1
F mmed {mesh_name} D 20
F rmed {output_rmed_name} R 80
'''


def generate_gap_closure_pack(
    request: ExploratoryGapClosureRequestV1,
    output_dir: Path,
) -> GeneratedGapClosurePackV1:
    mesh_path, mesh_evidence = load_verified_mesh_evidence(request)
    traction_mpa, total_force_kn = equivalent_clamp_traction_mpa(
        preload_per_bolt_kn=request.preload_per_bolt_kn,
        bolt_count=request.bolt_count,
        clamp_area_mm2=mesh_evidence.segment_outer_clamp_area_mm2,
    )

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    comm_name = f"{request.case_id}_gap_closure.comm"
    export_name = f"{request.case_id}_gap_closure.export"
    output_rmed_name = f"{request.case_id}_gap_closure_results.med"

    comm_path = output_dir / comm_name
    comm_path.write_text(
        render_code_aster_comm(request, clamp_traction_mpa=traction_mpa),
        encoding="utf-8",
        newline="\n",
    )
    export_path = output_dir / export_name
    export_path.write_text(
        render_export(
            comm_name=comm_name,
            mesh_name=mesh_path.name,
            output_rmed_name=output_rmed_name,
        ),
        encoding="utf-8",
        newline="\n",
    )

    pack = GeneratedGapClosurePackV1(
        case_id=request.case_id,
        request_sha256=_canonical_sha256(request),
        mesh_sha256=request.mesh_sha256,
        clamp_traction_mpa=traction_mpa,
        total_equivalent_clamp_force_kn=total_force_kn,
        comm_sha256=sha256_file(comm_path),
        export_sha256=sha256_file(export_path),
        authentic_solver_authorized=False,
        output_rmed_name=output_rmed_name,
        quarantine_reasons=[
            "material properties are exploratory assumptions",
            "preload is an assumed proof-load fraction rather than measured clamp force",
            "segment-to-hub friction is assumed",
            "individual bolts are replaced by equivalent uniform clamp traction",
            "no operational chain torque is applied in this first GAP-closure study",
        ],
    )
    (output_dir / "gap_closure_pack_manifest.json").write_text(
        pack.model_dump_json(indent=2), encoding="utf-8", newline="\n"
    )
    (output_dir / "gap_closure_request.json").write_text(
        request.model_dump_json(indent=2), encoding="utf-8", newline="\n"
    )
    return pack

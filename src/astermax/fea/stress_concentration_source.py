from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


class StressConcentrationSourceError(ValueError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _text(name: str, value: str) -> str:
    clean = str(value).strip()
    if not clean:
        raise StressConcentrationSourceError(f"{name} must be non-empty")
    return clean


@dataclass(frozen=True)
class StressConcentrationSource:
    schema: str
    source_id: str
    title: str
    edition_or_release: str
    publisher: str
    locator: str
    source_url: str
    rights_note: str
    calculation_data_embedded: bool
    dataset_sha256: str | None
    provenance_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("provenance_sha256")
        return payload


def build_stress_concentration_source(
    *,
    source_id: str,
    title: str,
    edition_or_release: str,
    publisher: str,
    locator: str,
    source_url: str,
    rights_note: str,
    calculation_data_embedded: bool = False,
    dataset_sha256: str | None = None,
) -> StressConcentrationSource:
    source_id = _text("source_id", source_id)
    title = _text("title", title)
    edition_or_release = _text("edition_or_release", edition_or_release)
    publisher = _text("publisher", publisher)
    locator = _text("locator", locator)
    source_url = _text("source_url", source_url)
    rights_note = _text("rights_note", rights_note)
    if not source_url.lower().startswith(("https://", "http://")):
        raise StressConcentrationSourceError("source_url must be an http(s) URL")

    digest = None
    if dataset_sha256 is not None:
        digest = str(dataset_sha256).lower().strip()
        if not _SHA256_RE.fullmatch(digest):
            raise StressConcentrationSourceError("dataset_sha256 must be a lowercase SHA-256 digest")
    if calculation_data_embedded and digest is None:
        raise StressConcentrationSourceError(
            "embedded calculation data requires an exact dataset_sha256"
        )

    payload = {
        "schema": "AsterMaxStressConcentrationSourceV1",
        "source_id": source_id,
        "title": title,
        "edition_or_release": edition_or_release,
        "publisher": publisher,
        "locator": locator,
        "source_url": source_url,
        "rights_note": rights_note,
        "calculation_data_embedded": bool(calculation_data_embedded),
        "dataset_sha256": digest,
    }
    return StressConcentrationSource(**payload, provenance_sha256=canonical_sha256(payload))


def shigley_2024_release_source_metadata() -> StressConcentrationSource:
    """Return source metadata only; no proprietary chart/table values are embedded."""
    return build_stress_concentration_source(
        source_id="SHIGLEY_MDE_2024_RELEASE",
        title="Shigley's Mechanical Engineering Design",
        edition_or_release="2024 Release",
        publisher="McGraw Hill",
        locator=(
            "Stress-concentration / shaft-design material; exact figure, table, "
            "equation or page locator must be supplied with the calculation dataset"
        ),
        source_url="https://www.mheducation.com/highered/product/shigleys-mechanical-engineering-design-nisbett.html",
        rights_note=(
            "METADATA_ONLY_NO_PROPRIETARY_TABLE_VALUES_EMBEDDED; calculation data must be "
            "lawfully supplied and independently hashed"
        ),
        calculation_data_embedded=False,
        dataset_sha256=None,
    )


def naca_tn_2442_source_metadata() -> StressConcentrationSource:
    """Public-domain provenance metadata for Frocht's NACA TN-2442.

    NASA NTRS identifies NACA-TN-2442 as public and states that it is a work of
    the U.S. Government for which public use is permitted. This helper embeds
    metadata and the published applicability locator only. It deliberately does
    not digitize or embed any stress-concentration-factor curve values.
    """
    return build_stress_concentration_source(
        source_id="NACA_TN_2442_1951",
        title="A Photoelastic Investigation of Stress Concentrations Due to Small Fillets and Grooves in Tension",
        edition_or_release="NACA Technical Note 2442, August 1951",
        publisher="National Advisory Committee for Aeronautics",
        locator=(
            "Published investigation scope: tension fillets/grooves; r/d approximately "
            "0.011 to 0.08 for D/d = 1.5 and D/d = 2.0"
        ),
        source_url="https://ntrs.nasa.gov/citations/19930083271",
        rights_note=(
            "NASA_NTRS_PUBLIC; WORK_OF_US_GOV_PUBLIC_USE_PERMITTED; "
            "METADATA_AND_APPLICABILITY_ONLY_NO_DIGITIZED_FACTOR_VALUES_EMBEDDED"
        ),
        calculation_data_embedded=False,
        dataset_sha256=None,
    )


def source_provenance_evidence(source: StressConcentrationSource) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SCF_SOURCE:{source.source_id}",
        kind="STRESS_CONCENTRATION_SOURCE_PROVENANCE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Stress-concentration source metadata is structurally complete and hash-bound. "
            "This evidence does not by itself validate any published factor value."
        ),
        payload_sha256=source.provenance_sha256,
        metadata=source.canonical_without_hash(),
    )

import pytest

from astermax.fea.stress_concentration_source import (
    StressConcentrationSourceError,
    build_stress_concentration_source,
    shigley_2024_release_source_metadata,
    source_provenance_evidence,
)


def test_shigley_metadata_does_not_embed_calculation_values():
    source = shigley_2024_release_source_metadata()
    assert source.edition_or_release == "2024 Release"
    assert source.calculation_data_embedded is False
    assert source.dataset_sha256 is None
    assert "NO_PROPRIETARY_TABLE_VALUES_EMBEDDED" in source.rights_note
    assert source.provenance_sha256 == shigley_2024_release_source_metadata().provenance_sha256
    evidence = source_provenance_evidence(source)
    assert evidence.claim_grade is True
    assert evidence.kind == "STRESS_CONCENTRATION_SOURCE_PROVENANCE"


def test_embedded_calculation_data_requires_dataset_hash():
    with pytest.raises(StressConcentrationSourceError, match="dataset_sha256"):
        build_stress_concentration_source(
            source_id="X",
            title="X",
            edition_or_release="1",
            publisher="X",
            locator="X",
            source_url="https://example.invalid/source",
            rights_note="AUTHORIZED_FOR_TEST",
            calculation_data_embedded=True,
        )


def test_source_rejects_non_http_url():
    with pytest.raises(StressConcentrationSourceError, match="http"):
        build_stress_concentration_source(
            source_id="X",
            title="X",
            edition_or_release="1",
            publisher="X",
            locator="X",
            source_url="local-file",
            rights_note="TEST",
        )

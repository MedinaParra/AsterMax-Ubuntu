#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
patch = (ROOT / "patch-c10219-load-history.ps1").read_text(encoding="utf-8")

required = {
    "Tied recognition": "PressureOverclosureEnum.Tied",
    "contract collection": 'root["bonded_contacts"]=BuildBondedContacts(model);',
    "unsupported contact gate": "UnsupportedNativeContactPairs(model)",
    "Code_Aster bonded operator": "LIAISON_MAIL",
    "slave surface mapping": "GROUP_MA_ESCL",
    "master volume mapping": "GROUP_MA_MAIT",
    "3D solid tie mode": "TYPE_RACCORD='MASSIF'",
    "master adjacent volume extraction": '["parent_element"]',
    "explicit bonded manifest": '["bonded_contact_count"]',
}
missing = [name for name, token in required.items() if token not in patch]
assert not missing, "Bonded implementation markers missing: " + ", ".join(missing)

# The safety policy must stay fail-closed: only explicit Tied/Bonded pairs may pass.
assert "nonlinear native contact is not certified yet" in patch
assert "native Code_Aster contact is currently certified only for Bonded/Tied pairs" in patch
assert "Legacy C10.35 blanket contact blocker could not be replaced safely" in patch

# Ensure we do not implement Bonded by deleting all contact checks or by silently treating Hard contact as Tied.
assert "PressureOverclosureEnum.Hard" not in patch.split("private static bool IsBondedContactPair", 1)[1].split("private static JArray BuildBondedContacts", 1)[0]
assert 'mode\"]=\"BONDED_LIAISON_MAIL\"' not in patch  # guard against accidentally escaped C# text

print("PASS: Bonded/Tied contract -> LIAISON_MAIL policy is present and non-Bonded contact remains fail-closed.")

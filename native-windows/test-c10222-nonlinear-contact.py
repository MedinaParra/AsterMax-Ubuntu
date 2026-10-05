#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
script = (ROOT / "contact-c10222-nonlinear.ps1").read_text(encoding="utf-8")

required = {
    "Hard normal behavior": "PressureOverclosureEnum.Hard",
    "friction property": "OfType<Friction>()",
    "Coulomb coefficient": "friction.Coefficient",
    "custom stick slope fail closed": "friction.StickSlope",
    "surface-to-surface gate": "ContactPairMethod.SurfaceToSurface",
    "small sliding gate": "pair.SmallSliding",
    "adjust gate": "pair.Adjust",
    "frictionless mode": 'mode="HARD_FRICTIONLESS"',
    "Coulomb mode": 'mode="HARD_COULOMB"',
    "nonlinear contract": 'root["nonlinear_contacts"]=BuildNonlinearContacts(model);',
    "Code_Aster contact operator": "DEFI_CONTACT",
    "continuous formulation": "FORMULATION='CONTINUE'",
    "frictionless Code_Aster mode": "FROTTEMENT='SANS'",
    "Coulomb Code_Aster mode": "FROTTEMENT='COULOMB'",
    "master contact surface": "GROUP_MA_MAIT",
    "slave contact surface": "GROUP_MA_ESCL",
    "nonlinear static solver": "STAT_NON_LINE",
    "elastic behavior": "RELATION='ELAS'",
    "Newton tangent": "MATRICE='TANGENTE'",
    "native Windows evidence gate": "NOT_RUN_NATIVE_WINDOWS",
}
missing = [name for name, token in required.items() if token not in script]
assert not missing, "Nonlinear contact markers missing: " + ", ".join(missing)

# Fail-closed policy: these pressure-overclosure laws are not silently approximated as Hard.
for unsupported in ("Linear/Exponential/Tabular", "Adjust must be disabled", "SmallSliding is not mapped"):
    assert unsupported in script, unsupported

# Contact must stay on native Code_Aster; do not reintroduce CalculiX as solver.
assert "CalculiX" not in script

# Bonded remains available and linear models without real contact retain MECA_STATIQUE.
assert "IsBondedContactPair" in script
assert "result=MECA_STATIQUE" in script

print("PASS: Hard frictionless + Coulomb candidate maps to DEFI_CONTACT/STAT_NON_LINE and unsupported contact laws remain fail-closed.")

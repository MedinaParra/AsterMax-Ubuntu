from pathlib import Path
import importlib.util

MODULE = Path(__file__).with_name("validate_result_tables.py")
spec = importlib.util.spec_from_file_location("validate_result_tables", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_mail(path: Path):
    path.write_text("COOR_3D\nN1 0 0 0\nN2 100 0 0\nFINSF\nFIN\n", encoding="utf-8")


def section(title, comps, rows):
    out = [f"# {title}", "# NOEUD;" + ";".join(comps)]
    for node, values in rows:
        out.append("N%d;%s" % (node, ";".join(str(v) for v in values)))
    out.append("")
    return "\n".join(out)


def complete_resu():
    rows = [(1, (0.0, 0.0, 0.0)), (2, (1e-3, 0.0, 0.0))]
    parts = []
    for title, comps in mod.SECTIONS.items():
        parts.append(section(title, comps, rows))
    return "\n".join(parts)


def test_complete_tables_pass(tmp_path):
    mail = tmp_path / "case.mail"
    resu = tmp_path / "case.resu"
    write_mail(mail)
    resu.write_text(complete_resu(), encoding="utf-8")
    report = mod.validate(resu, mod.mesh_nodes(mail))
    assert report["status"] == "PASS"
    assert all(v["rows"] == 2 for v in report["sections"].values())


def test_missing_node_fails_closed(tmp_path):
    mail = tmp_path / "case.mail"
    resu = tmp_path / "case.resu"
    write_mail(mail)
    text = complete_resu().replace("N2;0.001;0.0;0.0", "", 1)
    resu.write_text(text, encoding="utf-8")
    report = mod.validate(resu, mod.mesh_nodes(mail))
    assert report["status"] == "FAIL"
    assert any("incomplete PPM_DEPL" in x for x in report["failures"])


def test_non_finite_fails_closed(tmp_path):
    mail = tmp_path / "case.mail"
    resu = tmp_path / "case.resu"
    write_mail(mail)
    text = complete_resu().replace("N2;0.001;0.0;0.0", "N2;NaN;0.0;0.0", 1)
    resu.write_text(text, encoding="utf-8")
    report = mod.validate(resu, mod.mesh_nodes(mail))
    assert report["status"] == "FAIL"
    assert any("non-finite or malformed row PPM_DEPL" in x for x in report["failures"])


def test_duplicate_node_fails_closed(tmp_path):
    mail = tmp_path / "case.mail"
    resu = tmp_path / "case.resu"
    write_mail(mail)
    text = complete_resu().replace("N2;0.001;0.0;0.0", "N2;0.001;0.0;0.0\nN2;0.001;0.0;0.0", 1)
    resu.write_text(text, encoding="utf-8")
    report = mod.validate(resu, mod.mesh_nodes(mail))
    assert report["status"] == "FAIL"
    assert any("duplicate node PPM_DEPL" in x for x in report["failures"])

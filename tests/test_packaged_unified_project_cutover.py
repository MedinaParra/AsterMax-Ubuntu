from __future__ import annotations

import inspect

from astermax import app
from astermax.fea import project_session_shell


def test_shipping_desktop_owns_verified_results_binders_before_project_shell_install():
    source = inspect.getsource(app._desktop_main)
    hotspot = source.index("bind_adaptive_hotspots = install_adaptive_hotspot_tab(notebook)")
    stress = source.index("bind_stress_compare = install_adaptive_stress_comparison_tab(notebook)")
    shell = source.index("install_project_session_tab(")
    assert hotspot < shell
    assert stress < shell
    assert "hotspot_binder=bind_adaptive_hotspots" in source
    assert "stress_binder=bind_stress_compare" in source


def test_project_shell_installs_unified_project_tree_in_shipping_notebook():
    source = inspect.getsource(project_session_shell.install_project_session_tab)
    assert "from .unified_project_model import install_unified_project_tab" in source
    assert "install_unified_project_tab(" in source
    assert "hotspot_binder=hotspot_binder" in source
    assert "stress_binder=stress_binder" in source


def test_project_shell_public_return_contract_remains_backward_compatible():
    source = inspect.getsource(project_session_shell.install_project_session_tab)
    assert "return open_path, refresh" in source
    assert "return open_path, refresh," not in source


def test_cutover_does_not_add_solver_or_gmsh_execution_to_project_tree_install_path():
    source = inspect.getsource(project_session_shell.install_project_session_tab)
    tail = source[source.index("from .unified_project_model import install_unified_project_tab") :]
    assert "solve_" not in tail
    assert "gmsh" not in tail.lower()

#!/usr/bin/env python3
"""Wire the deterministic verified-results GUI demo into pinned PrePoMax."""
from __future__ import print_function

import argparse
from pathlib import Path


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError("Patch anchor not found: " + label)
    return text.replace(old, new, 1)


def patch_file(path, transform):
    text = path.read_text(encoding="utf-8-sig")
    updated = transform(text)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        print("patched", path)
    else:
        print("unchanged", path)


def patch_program(text):
    old = "            Application.Run(new FrmMain(args));"
    new = '''            FrmMain mainForm = new FrmMain(args);
            if (args != null && args.Length > 0 &&
                String.Equals(args[0], "--astermax-results-demo", StringComparison.OrdinalIgnoreCase))
            {
                string[] demoArgs = args.Skip(1).ToArray();
                mainForm.Shown += (sender, eventArgs) =>
                {
                    mainForm.BeginInvoke((Action)(() =>
                    {
                        int rc = PrePoMax.CodeAster.CodeAsterResultsDemo.Run(mainForm.Controller, demoArgs);
                        Environment.ExitCode = rc;
                        if (rc != 0) mainForm.Close();
                    }));
                };
            }
            Application.Run(mainForm);'''
    return replace_once(text, old, new, "Program deterministic results demo")


def patch_project(text):
    old = '    <Compile Include="CodeAster\\CodeAsterStudyProbe.cs" />'
    new = (old + '\n'
           '    <Compile Include="CodeAster\\CodeAsterResultsDemo.cs" />\n'
           '    <Compile Include="CodeAster\\NativeScalarBarGate.cs" />')
    if 'CodeAster\\NativeScalarBarGate.cs' in text:
        return text
    if 'CodeAster\\CodeAsterResultsDemo.cs' in text:
        return text.replace('    <Compile Include="CodeAster\\CodeAsterResultsDemo.cs" />',
                            '    <Compile Include="CodeAster\\CodeAsterResultsDemo.cs" />\n'
                            '    <Compile Include="CodeAster\\NativeScalarBarGate.cs" />', 1)
    return replace_once(text, old, new, "CodeAster results demo compile items")


def patch_demo(text):
    old_draw = '''                controller.DrawResults(false);
                Application.DoEvents();
                controller.Form.Refresh();'''
    new_draw = '''                controller.DrawResults(false);
                Application.DoEvents();

                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);
                if (!scalarBarReport.ControlFound || !scalarBarReport.MethodFound ||
                    !scalarBarReport.MethodInvoked || !scalarBarReport.InternalSpectrumAutomatic ||
                    !scalarBarReport.ScalarBarWidgetFound || !scalarBarReport.LookupTableFound ||
                    !scalarBarReport.LookupTableRangeReadable || !scalarBarReport.RangeMatchesField)
                    throw new InvalidOperationException("Native scalar-bar numerical semantics gate failed: " + scalarBarReport.ToString());

                controller.Form.Refresh();'''
    text = replace_once(text, old_draw, new_draw, "native scalar-bar numerical runtime gate")

    old_payload = '''                    "  \\\"verification_overlay_visible\\\": true,\\n" +
                    "  \\\"verification_overlay_bound_to_field\\\": true\\n" +'''
    new_payload = '''                    "  \\\"verification_overlay_visible\\\": true,\\n" +
                    "  \\\"verification_overlay_bound_to_field\\\": true,\\n" +
                    "  \\\"native_scalar_bar_control_found\\\": true,\\n" +
                    "  \\\"native_scalar_bar_method_invoked\\\": true,\\n" +
                    "  \\\"native_scalar_bar_automatic_range_contract\\\": true,\\n" +
                    "  \\\"native_scalar_bar_lut_found\\\": true,\\n" +
                    "  \\\"native_scalar_bar_range_source\\\": \\\"vtkMaxScalarBarWidget._lookupTable.GetTableRange()\\\",\\n" +
                    "  \\\"native_scalar_bar_min_mpa\\\": " + scalarBarReport.NativeRangeMin.ToString("R", CultureInfo.InvariantCulture) + ",\\n" +
                    "  \\\"native_scalar_bar_max_mpa\\\": " + scalarBarReport.NativeRangeMax.ToString("R", CultureInfo.InvariantCulture) + ",\\n" +
                    "  \\\"native_scalar_bar_range_matches_field\\\": true,\\n" +
                    "  \\\"native_scalar_bar_semantically_verified\\\": true\\n" +'''
    text = replace_once(text, old_payload, new_payload, "native scalar-bar numerical READY evidence")

    old_console = '                Console.WriteLine("Rendered semantics overlay: VERIFIED");'
    new_console = old_console + '\n                Console.WriteLine("Native scalar-bar numerical semantics: VERIFIED " + scalarBarReport.ToString());'
    return replace_once(text, old_console, new_console, "native scalar-bar numerical console evidence")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "Program.cs", patch_program)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    patch_file(repo / "PrePoMax" / "CodeAster" / "CodeAsterResultsDemo.cs", patch_demo)
    print("Deterministic verified Results demo wiring applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

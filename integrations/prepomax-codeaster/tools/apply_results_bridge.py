#!/usr/bin/env python3
"""Wire deterministic Code_Aster nodal result tables into PrePoMax post-processing."""

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


def patch_project(text):
    return replace_once(
        text,
        '    <Compile Include="CodeAster\\CodeAsterModelTranslator.cs" />',
        '    <Compile Include="CodeAster\\CodeAsterModelTranslator.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterResultBridge.cs" />',
        "Code_Aster result bridge compile item",
    )


def patch_case_writer(text):
    return replace_once(
        text,
        '            sb.AppendLine("F mess " + options.JobName + ".mess R 6");\n'
        '            sb.AppendLine("F rmed " + options.JobName + ".rmed R 80");',
        '            sb.AppendLine("F mess " + options.JobName + ".mess R 6");\n'
        '            sb.AppendLine("F resu " + options.JobName + ".resu R 8");\n'
        '            sb.AppendLine("F rmed " + options.JobName + ".rmed R 80");',
        "Code_Aster ASCII result mapping",
    )


def patch_result_bridge(text):
    if 'public const string ReactionTitle = "PPM_REACTION";' not in text:
        text = replace_once(
            text,
            '        public const string StrainShearTitle = "PPM_STRAIN_S";',
            '        public const string StrainShearTitle = "PPM_STRAIN_S";\n'
            '        public const string ReactionTitle = "PPM_REACTION";',
            "reaction result title",
        )

    reaction_call = '''            AppendTable(sb, "tab_reac", ReactionTitle, "REAC_NODA",
                        new string[] { "NOEUD", "DX", "DY", "DZ" },
                        new string[] { "DX", "DY", "DZ" });'''
    if reaction_call not in text:
        old = '''            AppendTable(sb, "tab_eps_s", StrainShearTitle, "EPSI_NOEU",
                        new string[] { "NOEUD", "EPXY", "EPYZ", "EPXZ" },
                        new string[] { "EPXY", "EPYZ", "EPXZ" });'''
        text = replace_once(text, old, old + "\n" + reaction_call, "native reaction result table")
    return text


def patch_translator(text):
    old = '''            sb.AppendLine("        TOUT_ORDRE='OUI'))");
            sb.AppendLine();
            sb.AppendLine("FIN()");'''
    new = '''            sb.AppendLine("        TOUT_ORDRE='OUI'))");
            sb.AppendLine();
            CodeAsterResultBridge.AppendResultTables(sb);
            sb.AppendLine("FIN()");'''
    text = replace_once(text, old, new, "Code_Aster table output before FIN")

    if 'FORCE=(\'REAC_NODA\',)' not in text:
        text = replace_once(
            text,
            '            sb.AppendLine("    CRITERES=(\'SIEQ_ELNO\', \'SIEQ_NOEU\'))");',
            '            sb.AppendLine("    CRITERES=(\'SIEQ_ELNO\', \'SIEQ_NOEU\'),");\n'
            '            sb.AppendLine("    FORCE=(\'REAC_NODA\',))");',
            "native REAC_NODA CALC_CHAMP request",
        )
    return text


def patch_controller(text):
    text = replace_once(
        text,
        '            else if (extension == ".frd") OpenFrd(fileName);',
        '            else if (extension == ".frd") OpenFrd(fileName);\n'
        '            else if (extension == ".rmed") OpenCodeAsterResults(fileName);',
        "Controller Open .rmed dispatch",
    )

    text = replace_once(
        text,
        'foreach (string extension in new string[] { ".comm", ".mail", ".export", ".mess", ".rmed" })',
        'foreach (string extension in new string[] { ".comm", ".mail", ".export", ".mess", ".resu", ".rmed" })',
        "Code_Aster stale .resu cleanup",
    )

    anchor = '''        private void OpenFrd(string fileName)
        {'''
    method = '''        private void OpenCodeAsterResults(string fileName)
        {
            if (_model == null || _model.Mesh == null)
            {
                MessageBoxes.ShowError("Open the corresponding PrePoMax model before loading Code_Aster results.");
                return;
            }
            if (!File.Exists(fileName) || new FileInfo(fileName).Length == 0)
            {
                MessageBoxes.ShowError("The Code_Aster RMED results file does not exist or is empty.");
                return;
            }

            string resuFileName = Path.ChangeExtension(fileName, ".resu");
            try
            {
                FeResults results = PrePoMax.CodeAster.CodeAsterResultBridge.Read(
                    fileName, resuFileName, _model.Mesh, _model.UnitSystem.UnitSystemType);
                LoadResults(results, false);
            }
            catch (Exception ex)
            {
                MessageBoxes.ShowError("Unable to load Code_Aster results." + Environment.NewLine + ex.Message);
            }
        }
        private void OpenFrd(string fileName)
        {'''
    text = replace_once(text, anchor, method, "Controller Code_Aster result loader")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="Path to the already model-translated PrePoMax source tree")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    patch_file(repo / "PrePoMax" / "CodeAster" / "CodeAsterCaseWriter.cs", patch_case_writer)
    patch_file(repo / "PrePoMax" / "CodeAster" / "CodeAsterResultBridge.cs", patch_result_bridge)
    patch_file(repo / "PrePoMax" / "CodeAster" / "CodeAsterModelTranslator.cs", patch_translator)
    patch_file(repo / "PrePoMax" / "Controller.cs", patch_controller)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

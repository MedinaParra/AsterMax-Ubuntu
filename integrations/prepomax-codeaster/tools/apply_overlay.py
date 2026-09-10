#!/usr/bin/env python3
"""Apply the Code_Aster integration to a PrePoMax source tree.

The patch is intentionally text-based and pinned to the reviewed upstream
revision. It is idempotent: re-running it on an already patched tree is safe.
"""

from __future__ import print_function

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "overlay"
CATALOG_SCRIPT = ROOT / "scripts" / "codeaster_catalog.py"


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


def copy_overlay(repo):
    for source in OVERLAY.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(OVERLAY)
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(target))
        print("copied", relative)

    catalog_target = repo / "PrePoMax" / "CodeAster" / "codeaster_catalog.py"
    catalog_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(CATALOG_SCRIPT), str(catalog_target))
    print("copied", catalog_target.relative_to(repo))


def patch_caejob_project(text):
    return replace_once(
        text,
        '    <Compile Include="AnalysisJob.cs" />',
        '    <Compile Include="AnalysisJob.cs" />\n    <Compile Include="AnalysisSolverTypeEnum.cs" />',
        "CaeJob project compile item",
    )


def patch_analysis_job(text):
    text = replace_once(
        text,
        "        protected string _convergenceFileContents;",
        "        protected string _convergenceFileContents;\n"
        "        protected AnalysisSolverTypeEnum _analysisSolver;\n"
        "        protected string _codeAsterVersion;\n"
        "        protected int _codeAsterMemoryMB;\n"
        "        protected int _codeAsterTimeLimitSeconds;",
        "AnalysisJob solver fields",
    )

    text = replace_once(
        text,
        "                base.Name = value;\n                _argument = Name;",
        "                base.Name = value;\n"
        "                _argument = _analysisSolver == AnalysisSolverTypeEnum.CodeAster\n"
        "                    ? Name + \".export\"\n"
        "                    : Name;",
        "AnalysisJob Name argument",
    )

    text = replace_once(
        text,
        "        public bool CompatibilityMode { get { return _compatibilityMode; } set { _compatibilityMode = value; } }",
        "        public bool CompatibilityMode { get { return _compatibilityMode; } set { _compatibilityMode = value; } }\n"
        "        public AnalysisSolverTypeEnum AnalysisSolver\n"
        "        {\n"
        "            get { return _analysisSolver; }\n"
        "            set\n"
        "            {\n"
        "                _analysisSolver = value;\n"
        "                _argument = _analysisSolver == AnalysisSolverTypeEnum.CodeAster\n"
        "                    ? Name + \".export\"\n"
        "                    : Name;\n"
        "            }\n"
        "        }\n"
        "        public string CodeAsterVersion { get { return _codeAsterVersion; } set { _codeAsterVersion = value; } }\n"
        "        public int CodeAsterMemoryMB { get { return _codeAsterMemoryMB; } set { _codeAsterMemoryMB = value; } }\n"
        "        public int CodeAsterTimeLimitSeconds { get { return _codeAsterTimeLimitSeconds; } set { _codeAsterTimeLimitSeconds = value; } }",
        "AnalysisJob solver properties",
    )

    text = replace_once(
        text,
        "            _compatibilityMode = false;\n            _numCPUs = 1;",
        "            _compatibilityMode = false;\n"
        "            _analysisSolver = AnalysisSolverTypeEnum.Calculix;\n"
        "            _codeAsterVersion = \"stable\";\n"
        "            _codeAsterMemoryMB = 4096;\n"
        "            _codeAsterTimeLimitSeconds = 3600;\n"
        "            _numCPUs = 1;",
        "AnalysisJob constructor defaults",
    )

    text = replace_once(
        text,
        "            _inputFileName = Path.Combine(_workDirectory, _name + \".inp\");  // must be first for the timer to work",
        "            _inputFileName = Path.Combine(_workDirectory, _name +\n"
        "                (_analysisSolver == AnalysisSolverTypeEnum.CodeAster ? \".comm\" : \".inp\"));  // must be first for the timer to work\n"
        "            if (_analysisSolver == AnalysisSolverTypeEnum.CodeAster) EnsureCodeAsterExportFile();",
        "AnalysisJob input file",
    )

    text = replace_once(
        text,
        "            string frdFileName = Path.Combine(WorkDirectory, _name + \".frd\");\n"
        "            bool resultsExist = File.Exists(frdFileName);\n"
        "            if (resultsExist)\n"
        "            {\n"
        "                long length = new FileInfo(frdFileName).Length;\n"
        "                if (length < 15 * 20) resultsExist = false;\n"
        "            }",
        "            string resultFileName = Path.Combine(WorkDirectory, _name +\n"
        "                (_analysisSolver == AnalysisSolverTypeEnum.CodeAster ? \".rmed\" : \".frd\"));\n"
        "            bool resultsExist = File.Exists(resultFileName);\n"
        "            if (resultsExist)\n"
        "            {\n"
        "                long length = new FileInfo(resultFileName).Length;\n"
        "                if (_analysisSolver == AnalysisSolverTypeEnum.CodeAster)\n"
        "                {\n"
        "                    if (length == 0) resultsExist = false;\n"
        "                }\n"
        "                else if (length < 15 * 20) resultsExist = false;\n"
        "            }",
        "AnalysisJob result file",
    )

    text = replace_once(
        text,
        "                else if (_sbOutput.ToString().Contains(\"*ERROR\") || _sbAllOutput.ToString().Contains(\"*ERROR\"))",
        "                else if (ContainsSolverError())",
        "AnalysisJob solver error detection",
    )

    text = replace_once(
        text,
        "        private void GetStatusFileContents()\n        {",
        "        private bool ContainsSolverError()\n"
        "        {\n"
        "            string output = (_sbOutput == null ? \"\" : _sbOutput.ToString()) +\n"
        "                            (_sbAllOutput == null ? \"\" : _sbAllOutput.ToString());\n"
        "            if (_analysisSolver == AnalysisSolverTypeEnum.Calculix) return output.Contains(\"*ERROR\");\n"
        "\n"
        "            string messFile = Path.Combine(_workDirectory, Name + \".mess\");\n"
        "            try\n"
        "            {\n"
        "                if (File.Exists(messFile)) output += File.ReadAllText(messFile);\n"
        "            }\n"
        "            catch { }\n"
        "            return output.Contains(\"<F>\") ||\n"
        "                   output.IndexOf(\"FATAL\", StringComparison.OrdinalIgnoreCase) >= 0;\n"
        "        }\n"
        "        private void EnsureCodeAsterExportFile()\n"
        "        {\n"
        "            Directory.CreateDirectory(_workDirectory);\n"
        "            string exportFile = Path.Combine(_workDirectory, Name + \".export\");\n"
        "            StringBuilder sb = new StringBuilder();\n"
        "            sb.AppendLine(\"P actions make_etude\");\n"
        "            sb.AppendLine(\"P version \" + (String.IsNullOrWhiteSpace(_codeAsterVersion) ? \"stable\" : _codeAsterVersion));\n"
        "            sb.AppendLine(\"P time_limit \" + Math.Max(1, _codeAsterTimeLimitSeconds));\n"
        "            sb.AppendLine(\"P memory_limit \" + Math.Max(256, _codeAsterMemoryMB));\n"
        "            sb.AppendLine(\"P ncpus \" + Math.Max(1, _numCPUs));\n"
        "            sb.AppendLine(\"F comm \" + Name + \".comm D 1\");\n"
        "            sb.AppendLine(\"F mmed \" + Name + \".med D 20\");\n"
        "            sb.AppendLine(\"F mess \" + Name + \".mess R 6\");\n"
        "            sb.AppendLine(\"F rmed \" + Name + \".rmed R 80\");\n"
        "            File.WriteAllText(exportFile, sb.ToString(), new UTF8Encoding(false));\n"
        "        }\n"
        "        private void GetStatusFileContents()\n        {",
        "AnalysisJob Code_Aster helpers",
    )

    text = replace_once(
        text,
        "                string statusFileName = Path.Combine(_workDirectory, Name + \".sta\");",
        "                string statusFileName = Path.Combine(_workDirectory, Name +\n"
        "                    (_analysisSolver == AnalysisSolverTypeEnum.CodeAster ? \".mess\" : \".sta\"));",
        "AnalysisJob status file",
    )

    text = replace_once(
        text,
        "        private void GetConvergenceFileContents()\n        {\n            try",
        "        private void GetConvergenceFileContents()\n"
        "        {\n"
        "            if (_analysisSolver == AnalysisSolverTypeEnum.CodeAster) return;\n"
        "            try",
        "AnalysisJob convergence file",
    )
    return text


def patch_view_job(text):
    text = replace_once(
        text,
        "        //\n        [CategoryAttribute(\"Data\")]\n        [OrderedDisplayName(1, 10, \"Executable\")]",
        "        //\n"
        "        [CategoryAttribute(\"Solver\")]\n"
        "        [OrderedDisplayName(0, 10, \"Analysis solver\")]\n"
        "        [DescriptionAttribute(\"Finite-element engine used to execute this analysis.\")]\n"
        "        [Id(1, 3)]\n"
        "        public AnalysisSolverTypeEnum AnalysisSolver\n"
        "        {\n"
        "            get { return _job.AnalysisSolver; }\n"
        "            set { _job.AnalysisSolver = value; }\n"
        "        }\n"
        "        //\n"
        "        [CategoryAttribute(\"Solver\")]\n"
        "        [OrderedDisplayName(1, 10, \"Number of CPUs\")]\n"
        "        [DescriptionAttribute(\"Number of CPU threads/processors requested by the solver.\")]\n"
        "        [Id(2, 3)]\n"
        "        public int NumCPUs { get { return _job.NumCPUs; } set { _job.NumCPUs = value; } }\n"
        "        //\n"
        "        [CategoryAttribute(\"Code_Aster\")]\n"
        "        [OrderedDisplayName(0, 10, \"Version\")]\n"
        "        [DescriptionAttribute(\"Code_Aster version understood by as_run, for example stable.\")]\n"
        "        [Id(1, 4)]\n"
        "        public string CodeAsterVersion { get { return _job.CodeAsterVersion; } set { _job.CodeAsterVersion = value; } }\n"
        "        //\n"
        "        [CategoryAttribute(\"Code_Aster\")]\n"
        "        [OrderedDisplayName(1, 10, \"Memory limit [MB]\")]\n"
        "        [Id(2, 4)]\n"
        "        public int CodeAsterMemoryMB { get { return _job.CodeAsterMemoryMB; } set { _job.CodeAsterMemoryMB = value; } }\n"
        "        //\n"
        "        [CategoryAttribute(\"Code_Aster\")]\n"
        "        [OrderedDisplayName(2, 10, \"Time limit [s]\")]\n"
        "        [Id(3, 4)]\n"
        "        public int CodeAsterTimeLimitSeconds { get { return _job.CodeAsterTimeLimitSeconds; } set { _job.CodeAsterTimeLimitSeconds = value; } }\n"
        "        //\n"
        "        [CategoryAttribute(\"Data\")]\n        [OrderedDisplayName(1, 10, \"Executable\")]",
        "ViewJob solver properties",
    )

    text = replace_once(
        text,
        '[DescriptionAttribute("Calculix executable file (ccx.exe).")]',
        '[DescriptionAttribute("Solver executable: ccx.exe for CalculiX or as_run for Code_Aster.")]',
        "ViewJob executable description",
    )
    text = replace_once(
        text,
        "        public string Executable\n        {\n            get { return _job.Executable; }\n        }",
        "        public string Executable\n"
        "        {\n"
        "            get { return _job.Executable; }\n"
        "            set { _job.Executable = value; }\n"
        "        }",
        "ViewJob executable setter",
    )
    text = replace_once(
        text,
        '[DescriptionAttribute("Addtional Calculix arguments. Change this value only if you want to run the solver in a different way.")]',
        '[DescriptionAttribute("Solver command-line arguments. Code_Aster normally uses <job>.export.")]',
        "ViewJob argument description",
    )
    text = replace_once(
        text,
        "        public string WorkDirectory { get { return _job.WorkDirectory; } }",
        "        public string WorkDirectory { get { return _job.WorkDirectory; } set { _job.WorkDirectory = value; } }",
        "ViewJob work directory setter",
    )
    return text


def patch_settings_container(text):
    text = replace_once(text, "        private CalculixSettings _calculix;",
                        "        private CalculixSettings _calculix;\n        private CodeAsterSettings _codeAster;",
                        "settings field")
    text = replace_once(text, "        public CalculixSettings Calculix { get { return _calculix; } set { _calculix = value; } }",
                        "        public CalculixSettings Calculix { get { return _calculix; } set { _calculix = value; } }\n        public CodeAsterSettings CodeAster { get { return _codeAster; } set { _codeAster = value; } }",
                        "settings property")
    text = replace_once(text, "            _calculix = new CalculixSettings();",
                        "            _calculix = new CalculixSettings();\n            _codeAster = new CodeAsterSettings();",
                        "settings initialize")
    text = replace_once(text, "            _calculix.Reset();",
                        "            _calculix.Reset();\n            _codeAster.Reset();",
                        "settings reset")
    text = replace_once(text, "            _calculix = clone._calculix;",
                        "            _calculix = clone._calculix;\n            _codeAster = clone._codeAster;",
                        "settings clone")
    text = replace_once(text, "            items.Add(Globals.CalculixSettingsName, _calculix);",
                        "            items.Add(Globals.CalculixSettingsName, _calculix);\n            items.Add(\"Code_Aster\", _codeAster);",
                        "settings dictionary")
    text = replace_once(
        text,
        "                _calculix = (CalculixSettings)items[Globals.CalculixSettingsName];",
        "                _calculix = (CalculixSettings)items[Globals.CalculixSettingsName];\n"
        "                ISettings codeAsterSettings;\n"
        "                if (items.TryGetValue(\"Code_Aster\", out codeAsterSettings))\n"
        "                    _codeAster = (CodeAsterSettings)codeAsterSettings;\n"
        "                else _codeAster = new CodeAsterSettings();",
        "settings load",
    )
    return text


def patch_analysis_form(text):
    text = replace_once(
        text,
        "            propertyGrid.SetLabelColumnWidth(_labelRatio);",
        "            propertyGrid.SetLabelColumnWidth(_labelRatio);\n"
        "            // Solver tools are attached programmatically to avoid changing the designer.\n"
        "            if (propertyGrid.ContextMenuStrip == null) propertyGrid.ContextMenuStrip = new ContextMenuStrip();\n"
        "            ToolStripMenuItem codeAsterCatalog = new ToolStripMenuItem(\"Code_Aster command catalog...\");\n"
        "            codeAsterCatalog.Click += delegate { ShowCodeAsterCatalog(); };\n"
        "            propertyGrid.ContextMenuStrip.Items.Add(codeAsterCatalog);",
        "analysis form context menu",
    )

    text = replace_once(
        text,
        "        private void propertyGrid_PropertyValueChanged(object s, PropertyValueChangedEventArgs e)\n"
        "        {\n"
        "            propertyGrid.Refresh();",
        "        private void propertyGrid_PropertyValueChanged(object s, PropertyValueChangedEventArgs e)\n"
        "        {\n"
        "            if (e.ChangedItem != null && e.ChangedItem.PropertyDescriptor != null &&\n"
        "                e.ChangedItem.PropertyDescriptor.Name == nameof(ViewJob.AnalysisSolver))\n"
        "                ApplySolverDefaults();\n"
        "            propertyGrid.Refresh();",
        "analysis form solver change",
    )

    text = replace_once(
        text,
        "        private string GetJobName()\n        {",
        "        private void ApplySolverDefaults()\n"
        "        {\n"
        "            AnalysisJob job = _viewJob.GetBase();\n"
        "            if (job.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster)\n"
        "            {\n"
        "                CodeAsterSettings settings = _controller.Settings.CodeAster;\n"
        "                job.Executable = settings.AsRunExecutable;\n"
        "                job.Argument = job.Name + \".export\";\n"
        "                job.WorkDirectory = settings.WorkDirectory;\n"
        "                job.NumCPUs = settings.NumCPUs;\n"
        "                job.CodeAsterVersion = settings.Version;\n"
        "                job.CodeAsterMemoryMB = settings.MemoryMB;\n"
        "                job.CodeAsterTimeLimitSeconds = settings.TimeLimitSeconds;\n"
        "                job.EnvironmentVariables = ParseEnvironmentVariables(settings.EnvironmentVariables);\n"
        "            }\n"
        "            else\n"
        "            {\n"
        "                job.Executable = _controller.Settings.Calculix.CalculixExe;\n"
        "                job.Argument = job.Name;\n"
        "                job.WorkDirectory = _controller.Settings.GetWorkDirectory();\n"
        "            }\n"
        "        }\n"
        "        private List<EnvironmentVariable> ParseEnvironmentVariables(string[] entries)\n"
        "        {\n"
        "            List<EnvironmentVariable> result = new List<EnvironmentVariable>();\n"
        "            if (entries == null) return result;\n"
        "            foreach (string entry in entries)\n"
        "            {\n"
        "                if (String.IsNullOrWhiteSpace(entry)) continue;\n"
        "                int separator = entry.IndexOf('=');\n"
        "                if (separator <= 0) continue;\n"
        "                result.Add(new EnvironmentVariable(entry.Substring(0, separator).Trim(), entry.Substring(separator + 1)));\n"
        "            }\n"
        "            return result;\n"
        "        }\n"
        "        private void ShowCodeAsterCatalog()\n"
        "        {\n"
        "            try\n"
        "            {\n"
        "                CodeAsterSettings settings = _controller.Settings.CodeAster;\n"
        "                string helper = Path.Combine(Application.StartupPath, \"CodeAster\", \"codeaster_catalog.py\");\n"
        "                var catalog = PrePoMax.CodeAster.CodeAsterCatalogService.Load(\n"
        "                    settings.PythonExecutable, helper, settings.EnvironmentVariables, 15000);\n"
        "                using (PrePoMax.FrmCodeAsterCatalog form = new PrePoMax.FrmCodeAsterCatalog(catalog))\n"
        "                    form.ShowDialog(this);\n"
        "            }\n"
        "            catch (Exception ex)\n"
        "            {\n"
        "                ExceptionTools.Show(this, ex);\n"
        "            }\n"
        "        }\n"
        "        private string GetJobName()\n        {",
        "analysis form helper methods",
    )
    return text


def patch_prepomax_project(text):
    text = replace_once(
        text,
        '    <Compile Include="Forms\\61_Analysis\\ViewJob.cs" />',
        '    <Compile Include="Forms\\61_Analysis\\ViewJob.cs" />\n'
        '    <Compile Include="Forms\\61_Analysis\\FrmCodeAsterCatalog.cs">\n'
        '      <SubType>Form</SubType>\n'
        '    </Compile>\n'
        '    <Compile Include="CodeAster\\CodeAsterCatalogService.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterCaseWriter.cs" />\n'
        '    <Compile Include="Settings\\CodeAsterSettings.cs" />',
        "PrePoMax project compile items",
    )
    # Put the Python catalog helper next to the executable as CodeAster/codeaster_catalog.py.
    marker = "  <Import Project=\"$(MSBuildToolsPath)\\Microsoft.CSharp.targets\" />"
    content_item = (
        "  <ItemGroup>\n"
        "    <Content Include=\"CodeAster\\codeaster_catalog.py\">\n"
        "      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>\n"
        "    </Content>\n"
        "  </ItemGroup>\n"
    )
    if 'Content Include="CodeAster\\codeaster_catalog.py"' not in text:
        if marker not in text:
            raise RuntimeError("Patch anchor not found: PrePoMax content item")
        text = text.replace(marker, content_item + marker, 1)
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="Path to a PrePoMax source checkout")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    required = [
        repo / "PrePoMax.sln",
        repo / "CaeJob" / "AnalysisJob.cs",
        repo / "PrePoMax" / "Forms" / "61_Analysis" / "ViewJob.cs",
    ]
    for path in required:
        if not path.exists():
            raise SystemExit("Not a supported PrePoMax checkout: missing " + str(path))

    copy_overlay(repo)

    patch_file(repo / "CaeJob" / "CaeJob.csproj", patch_caejob_project)
    patch_file(repo / "CaeJob" / "AnalysisJob.cs", patch_analysis_job)
    patch_file(repo / "PrePoMax" / "Forms" / "61_Analysis" / "ViewJob.cs", patch_view_job)
    patch_file(repo / "PrePoMax" / "Settings" / "SettingsContainer.cs", patch_settings_container)
    patch_file(repo / "PrePoMax" / "Forms" / "61_Analysis" / "FrmAnalysis.cs", patch_analysis_form)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_prepomax_project)

    print("Code_Aster integration applied successfully.")
    print("Open PrePoMax.sln, configure Code_Aster settings, then select CodeAster in an Analysis job.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

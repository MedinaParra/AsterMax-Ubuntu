param([string]$Root)
$ErrorActionPreference = 'Stop'

$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $uiPath)){ throw 'AsterMaxNativeUi.cs must exist before C9.65 patch.' }
$ui = Get-Content $uiPath -Raw
$old = @'
            ribbon.TabPages.Add(BuildRibbonPage("Results", new Control[] {
                CommandTile("Contours", "RESULT", () => tsbResultsColorContours.PerformClick(), true),
                CommandTile("Deformed", "RESULT", () => tsbResultsDeformed.PerformClick()),
                InfoCard("Deformation • Equivalent Stress • Reactions")
            }));
'@
$new = @'
            ribbon.TabPages.Add(BuildRibbonPage("Results", new Control[] {
                CommandTile("Load Results", "CODE_ASTER", () => OpenAsterMaxResultsBundle(), true),
                CommandTile("Contours", "RESULT", () => tsbResultsColorContours.PerformClick()),
                CommandTile("Deformed", "RESULT", () => tsbResultsDeformed.PerformClick()),
                InfoCard("Real MED bundle • field selector • min/max • probe")
            }));
'@
if(-not $ui.Contains($old)){ throw 'C9.65 Results ribbon anchor not found.' }
$ui = $ui.Replace($old,$new)
Set-Content $uiPath $ui -Encoding UTF8

$code = @'
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    internal sealed class AsterMaxResultsBundle
    {
        public string SourceFile { get; private set; }
        public int NodeCount { get; private set; }
        public int ElementCount { get; private set; }
        public double[][] Coordinates { get; private set; }
        public double[][] Displacement { get; private set; }
        public double[] TotalDeformation { get; private set; }
        public double[] EquivalentStress { get; private set; }
        public string LengthUnit { get; private set; }
        public string StressUnit { get; private set; }

        public static AsterMaxResultsBundle Load(string path)
        {
            JObject root = JObject.Parse(File.ReadAllText(path));
            if ((string)root["schema"] != "astermax-results-bundle/v0")
                throw new InvalidDataException("Unsupported AsterMax results schema.");
            if ((bool?)root["integrity"]?["fea_values_invented"] != false)
                throw new InvalidDataException("Results integrity contract failed: synthetic values are not accepted.");

            var b = new AsterMaxResultsBundle();
            b.SourceFile = path;
            b.NodeCount = (int)root["mesh"]["node_count"];
            b.ElementCount = (int)root["mesh"]["element_count"];
            b.LengthUnit = (string)root["units"]["length"];
            b.StressUnit = (string)root["units"]["stress"];
            b.Coordinates = ReadJagged(root["arrays"]["coordinates"], 3);
            b.Displacement = ReadJagged(root["arrays"]["displacement"], 3);
            b.TotalDeformation = ReadVector(root["arrays"]["total_deformation"]);
            b.EquivalentStress = ReadVector(root["arrays"]["von_mises"]);
            b.Validate();
            return b;
        }

        private static double[] ReadVector(JToken token)
        {
            return token.Select(x => (double)x).ToArray();
        }

        private static double[][] ReadJagged(JToken token, int width)
        {
            return token.Select(row => row.Select(x => (double)x).ToArray())
                        .Select(row => row.Length == width ? row : throw new InvalidDataException("Unexpected vector width."))
                        .ToArray();
        }

        private void Validate()
        {
            if (NodeCount <= 0 || ElementCount <= 0) throw new InvalidDataException("Empty result mesh.");
            if (Coordinates.Length != NodeCount || Displacement.Length != NodeCount ||
                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount)
                throw new InvalidDataException("Result array/node count mismatch.");
            if (LengthUnit != "mm" || StressUnit != "MPa")
                throw new InvalidDataException("C9.65 PMV accepts the verified mm / N / MPa contract only.");
            if (Coordinates.SelectMany(x => x).Any(x => Double.IsNaN(x) || Double.IsInfinity(x)) ||
                Displacement.SelectMany(x => x).Any(x => Double.IsNaN(x) || Double.IsInfinity(x)) ||
                TotalDeformation.Any(x => Double.IsNaN(x) || Double.IsInfinity(x)) ||
                EquivalentStress.Any(x => Double.IsNaN(x) || Double.IsInfinity(x)))
                throw new InvalidDataException("Non-finite FEA value detected.");
        }

        public string[] AvailableFields()
        {
            return new[] { "Total Deformation", "Equivalent Stress", "Displacement X", "Displacement Y", "Displacement Z" };
        }

        public double[] GetScalarField(string field)
        {
            switch (field)
            {
                case "Total Deformation": return TotalDeformation;
                case "Equivalent Stress": return EquivalentStress;
                case "Displacement X": return Displacement.Select(v => v[0]).ToArray();
                case "Displacement Y": return Displacement.Select(v => v[1]).ToArray();
                case "Displacement Z": return Displacement.Select(v => v[2]).ToArray();
                default: throw new ArgumentOutOfRangeException("field", field, "Unknown result field.");
            }
        }

        public Tuple<double,double> GetRange(string field)
        {
            double[] values = GetScalarField(field);
            return Tuple.Create(values.Min(), values.Max());
        }

        public double ProbeNode(int zeroBasedNodeIndex, string field)
        {
            if (zeroBasedNodeIndex < 0 || zeroBasedNodeIndex >= NodeCount)
                throw new ArgumentOutOfRangeException("zeroBasedNodeIndex");
            return GetScalarField(field)[zeroBasedNodeIndex];
        }

        public double[][] GetDeformedCoordinates(double scale)
        {
            var result = new double[NodeCount][];
            for (int i = 0; i < NodeCount; i++)
                result[i] = new[] {
                    Coordinates[i][0] + scale * Displacement[i][0],
                    Coordinates[i][1] + scale * Displacement[i][1],
                    Coordinates[i][2] + scale * Displacement[i][2]
                };
            return result;
        }

        public string Describe(string field)
        {
            var r = GetRange(field);
            string unit = field == "Equivalent Stress" ? StressUnit : LengthUnit;
            return String.Format(CultureInfo.InvariantCulture,
                "{0} | Nodes {1} | Min {2:G7} {4} | Max {3:G7} {4}", field, NodeCount, r.Item1, r.Item2, unit);
        }
    }

    public partial class FrmMain
    {
        private AsterMaxResultsBundle _asterMaxLoadedResults;

        private void OpenAsterMaxResultsBundle()
        {
            try
            {
                using (var dlg = new OpenFileDialog())
                {
                    dlg.Title = "Load real Code_Aster results bundle";
                    dlg.Filter = "AsterMax Results Bundle (*.json)|*.json|All files (*.*)|*.*";
                    if (dlg.ShowDialog(this) != DialogResult.OK) return;
                    _asterMaxLoadedResults = AsterMaxResultsBundle.Load(dlg.FileName);
                    var fields = _asterMaxLoadedResults.AvailableFields();
                    MessageBox.Show(this,
                        _asterMaxLoadedResults.Describe(fields[0]) + Environment.NewLine +
                        _asterMaxLoadedResults.Describe(fields[1]) + Environment.NewLine + Environment.NewLine +
                        "Bundle accepted. Native VTK actor binding is the next visualization gate.",
                        "AsterMax Results Workspace", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            }
            catch (Exception ex)
            {
                MessageBoxes.ShowError("AsterMax results bundle rejected: " + ex.Message);
            }
        }
    }
}
'@
$codePath = Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
Set-Content $codePath $code -Encoding UTF8

$projPath = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$proj = Get-Content $projPath -Raw
if(-not $proj.Contains('Forms\AsterMaxResultsWorkspace.cs')){
    $anchor = '<Compile Include="Forms\AsterMaxNativeUi.cs" />'
    if(-not $proj.Contains($anchor)){ throw 'C9.65 csproj anchor not found.' }
    $proj = $proj.Replace($anchor, $anchor + [Environment]::NewLine + '    <Compile Include="Forms\AsterMaxResultsWorkspace.cs" />')
    Set-Content $projPath $proj -Encoding UTF8
}

Write-Host 'C9.65 native Results Workspace contract injected.' -ForegroundColor Green

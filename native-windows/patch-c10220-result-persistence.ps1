param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.30 result-persistence anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$c=Get-Content $controllerPath -Raw
$fieldAnchor='        [NonSerialized] protected FrmMain _form;'
if(-not $c.Contains('_asterMaxEmbeddedResultsJson'))
{
    $c=Replace-Required $c $fieldAnchor ($fieldAnchor+[Environment]::NewLine+
        '        [System.Runtime.Serialization.OptionalField] private string _asterMaxEmbeddedResultsJson;')
}
$saveAnchor='                _savingFile = true;'
if(-not $c.Contains('CaptureAsterMaxResultsForPmx()'))
{
    $c=Replace-Required $c $saveAnchor ($saveAnchor+[Environment]::NewLine+
        '                _asterMaxEmbeddedResultsJson = _form == null ? null : _form.CaptureAsterMaxResultsForPmx();')
}
$tmpAnchor='            tmp = (Controller)data[0];'
if(-not $c.Contains('_asterMaxEmbeddedResultsJson = tmp._asterMaxEmbeddedResultsJson;'))
{
    $c=Replace-Required $c $tmpAnchor ($tmpAnchor+[Environment]::NewLine+
        '            _asterMaxEmbeddedResultsJson = tmp._asterMaxEmbeddedResultsJson;')
}
$openTail='            //File.WriteAllText(@"D:\out.txt", json);'
if(-not $c.Contains('RestoreAsterMaxResultsFromPmx(_asterMaxEmbeddedResultsJson)'))
{
    $c=Replace-Required $c $openTail ($openTail+[Environment]::NewLine+
        '            _form.RestoreAsterMaxResultsFromPmx(_asterMaxEmbeddedResultsJson);')
}
Set-Content $controllerPath $c -Encoding UTF8

$workspacePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$w=Get-Content $workspacePath -Raw
$sourceAnchor='        public string SourceFile { get; private set; }'
if(-not $w.Contains('public string SerializedJson { get; private set; }'))
{
    $w=Replace-Required $w $sourceAnchor ($sourceAnchor+[Environment]::NewLine+
        '        public string SerializedJson { get; private set; }')
}
$readAnchor='            JObject root = JObject.Parse(File.ReadAllText(path));'
if(-not $w.Contains('string serializedJson = File.ReadAllText(path);'))
{
    $w=Replace-Required $w $readAnchor ('            string serializedJson = File.ReadAllText(path);'+
        [Environment]::NewLine+'            JObject root = JObject.Parse(serializedJson);')
}
$sourceAssign='            b.SourceFile = path;'
if(-not $w.Contains('b.SerializedJson = serializedJson;'))
{
    $w=Replace-Required $w $sourceAssign ($sourceAssign+[Environment]::NewLine+
        '            b.SerializedJson = serializedJson;')
}

$fieldSelector='        public string[] AvailableFields()'
if(-not $w.Contains('internal static AsterMaxResultsBundle LoadEmbedded'))
{
$embedded=@'
        internal static AsterMaxResultsBundle LoadEmbedded(string json)
        {
            if (String.IsNullOrWhiteSpace(json)) throw new InvalidDataException("Embedded AsterMax results are empty.");
            JObject root = JObject.Parse(json);
            if ((string)root["schema"] != "astermax-results-bundle/v0")
                throw new InvalidDataException("Unsupported embedded AsterMax results schema.");
            if ((bool?)root["integrity"]?["fea_values_invented"] != false)
                throw new InvalidDataException("Embedded results integrity contract failed: synthetic values are not accepted.");

            var b = new AsterMaxResultsBundle();
            b.SourceFile = "PMX:embedded-astermax-results";
            b.SerializedJson = json;
            b.NodeCount = (int)root["mesh"]["node_count"];
            b.ElementCount = (int)root["mesh"]["element_count"];
            b.LengthUnit = (string)root["units"]["length"];
            b.StressUnit = (string)root["units"]["stress"];
            b.ResultModelFingerprintSha256 = ((string)root["integrity"]?["model_fingerprint_sha256"] ?? "").ToLowerInvariant();
            b.Coordinates = ReadJagged(root["arrays"]["coordinates"], 3);
            b.Displacement = ReadJagged(root["arrays"]["displacement"], 3);
            b.TotalDeformation = ReadVector(root["arrays"]["total_deformation"]);
            b.EquivalentStress = ReadVector(root["arrays"]["von_mises"]);
            b.Validate();
            return b;
        }

'@
    $w=Replace-Required $w $fieldSelector ($embedded+$fieldSelector)
}

$openMethod='        private void OpenAsterMaxResultsBundle()'
if(-not $w.Contains('CaptureAsterMaxResultsForPmx'))
{
$frmHelpers=@'
        internal string CaptureAsterMaxResultsForPmx()
        {
            if (_asterMaxLoadedResults == null) return null;
            try
            {
                _asterMaxLoadedResults.RequireCurrentModel(_controller == null ? null : _controller.Model);
                return _asterMaxLoadedResults.SerializedJson;
            }
            catch (Exception ex) when (ex is InvalidDataException || ex is InvalidOperationException)
            {
                tsslState.ToolTipText = "Resultados no guardados: el modelo cambió y los resultados están obsoletos. Ejecute Solve nuevamente.";
                return null;
            }
        }

        internal void RestoreAsterMaxResultsFromPmx(string json)
        {
            ResetAsterMaxIntegratedResults();
            if (String.IsNullOrWhiteSpace(json))
            {
                RefreshAsterMaxResultAvailability();
                return;
            }
            try
            {
                var candidate = AsterMaxResultsBundle.LoadEmbedded(json);
                candidate.RequireCurrentModel(_controller == null ? null : _controller.Model);
                _asterMaxLoadedResults = candidate;
                RefreshAsterMaxResultAvailability();
            }
            catch (Exception ex) when (ex is InvalidDataException || ex is InvalidOperationException)
            {
                _asterMaxLoadedResults = null;
                RefreshAsterMaxResultAvailability();
                tsslState.ToolTipText = "Resultados PMX rechazados por identidad/integridad: " + ex.Message + " Ejecute Solve nuevamente.";
            }
        }

'@
    $w=Replace-Required $w $openMethod ($frmHelpers+$openMethod)
}
Set-Content $workspacePath $w -Encoding UTF8

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
if(Test-Path $auditPath)
{
    $a=Get-Content $auditPath -Raw
    if(-not $a.Contains('C10230ExerciseResultPmxReopen('))
    {
        $finalWrite='            File.WriteAllText(Path.Combine(directory, "workflow-conformance-session.json"),'
        $idx=$a.LastIndexOf($finalWrite)
        if($idx -lt 0){ throw 'C10.30 final workflow session write not found.' }
$invoke=@'
            JObject resultPmx = C10230ExerciseResultPmxReopen(
                Path.Combine(directory, "B01-C10.30-with-results.pmx"), resultField);
            File.WriteAllText(Path.Combine(directory, "pmx-result-reopen.json"), resultPmx.ToString(Formatting.Indented));
            if ((bool?)resultPmx["pass"] != true)
                throw new InvalidOperationException("PMX result save/reopen conformance failed: " + (string)resultPmx["reason"]);

'@
        $a=$a.Insert($idx,$invoke)

$helper=@'
        private JObject C10230ExerciseResultPmxReopen(string path, string field)
        {
            try
            {
                if (_asterMaxLoadedResults == null)
                    return new JObject { ["pass"]=false, ["reason"]="No current AsterMax result exists before PMX save." };
                _asterMaxLoadedResults.RequireCurrentModel(_controller.Model);
                var before = _asterMaxLoadedResults.GetRange(field);
                string fingerprint = _asterMaxLoadedResults.ResultModelFingerprintSha256;

                _controller.SaveToPmx(path);
                if (!File.Exists(path) || new FileInfo(path).Length == 0)
                    return new JObject { ["pass"]=false, ["reason"]="PMX with results was not written." };

                _controller.Open(path);
                RegenerateTree();
                _modelTree.RefreshAsterMaxOutline();
                RefreshAsterMaxResultAvailability();

                bool study = _controller.Model.StepCollection.StepsList
                    .Where(step => !(step is CaeModel.InitialStep))
                    .Any(step => step.BoundaryConditions.Count > 0 && step.Loads.Count > 0);
                bool restored = _asterMaxLoadedResults != null;
                bool identity = false;
                bool range = false;
                if (restored)
                {
                    _asterMaxLoadedResults.RequireCurrentModel(_controller.Model);
                    identity = String.Equals(fingerprint, _asterMaxLoadedResults.ResultModelFingerprintSha256, StringComparison.OrdinalIgnoreCase);
                    var after = _asterMaxLoadedResults.GetRange(field);
                    range = Math.Abs(before.Item1-after.Item1) <= 1e-12 * Math.Max(1.0,Math.Abs(before.Item1)) &&
                            Math.Abs(before.Item2-after.Item2) <= 1e-12 * Math.Max(1.0,Math.Abs(before.Item2));
                }

                int contextChecks = _modelTree.AuditAsterMaxContextMenus();
                bool pass = study && restored && identity && range && contextChecks >= 8;
                return new JObject {
                    ["pass"]=pass,
                    ["reason"]=pass ? "Study, verified AsterMax results and reusable context menus survived PMX reopen." :
                        "Study/result identity/range/context-menu persistence failed after PMX reopen.",
                    ["study_survived"]=study,
                    ["results_restored"]=restored,
                    ["fingerprint_preserved"]=identity,
                    ["field"]=field,
                    ["field_range_preserved"]=range,
                    ["context_menu_lifecycle_checks_after_reopen"]=contextChecks,
                    ["pmx_bytes"]=new FileInfo(path).Length
                };
            }
            catch(Exception ex)
            {
                return new JObject { ["pass"]=false, ["reason"]=ex.ToString() };
            }
        }

'@
        $tail='    }'+[Environment]::NewLine+'}'
        $tailIdx=$a.LastIndexOf($tail)
        if($tailIdx -lt 0){ throw 'C10.30 audit class tail not found.' }
        $a=$a.Insert($tailIdx,$helper)
    }
    Set-Content $auditPath $a -Encoding UTF8
}

Write-Host 'C10.30 verified AsterMax result persistence + PMX reopen audit applied.' -ForegroundColor Green

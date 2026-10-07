param([string]$Root)
$ErrorActionPreference='Stop'
$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=Get-Content $project -Raw
$anchor='<Compile Include="Forms\AsterMaxMechanicalQualification.cs" />'
if(-not $p.Contains('Forms\AsterMaxProjectResultsStore.cs')){
    if(-not $p.Contains($anchor)){ throw 'C10.41 qualification compile anchor missing.' }
    $p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxProjectResultsStore.cs" />')
    Set-Content $project $p -Encoding UTF8
}
Copy-Item (Join-Path $PSScriptRoot 'AsterMaxProjectResultsStore.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxProjectResultsStore.cs') -Force
$controller=Join-Path $Root 'PrePoMax/Controller.cs'
$c=[regex]::Replace((Get-Content $controller -Raw),"\r\n?","`n")
if(-not $c.Contains('_form.RestoreAsterMaxProjectResults(fileName);')){
    $start=$c.IndexOf('        public void Open(string fileName)')
    $end=$c.IndexOf('        private void OpenPmx(string fileName)',$start)
    if($start -lt 0 -or $end -le $start){ throw 'C10.41 Controller.Open method boundaries missing.' }
    $part=$c.Substring($start,$end-$start)
    $old='            AddFileNameToRecentFiles(fileName);  // this redraws the scene'
    if(-not $part.Contains($old)){ throw 'C10.41 project reopen hook anchor missing.' }
    $part=$part.Replace($old,$old+"`n"+'            if(extension==".pmx") _form.RestoreAsterMaxProjectResults(fileName);')
    $c=$c.Substring(0,$start)+$part+$c.Substring($end)
}
if(-not $c.Contains('_form.PersistAsterMaxProjectResults(fileName);')){
    $old=@'
                ResetAfterSavig(this);
                _savingFile = false;
            }
        }
        // Export
'@
    $new=@'
                ResetAfterSavig(this);
                _savingFile = false;
            }
            _form.PersistAsterMaxProjectResults(fileName);
        }
        // Export
'@
    $old=[regex]::Replace($old,"\r\n?","`n").TrimEnd()
    $new=[regex]::Replace($new,"\r\n?","`n").TrimEnd()
    if(-not $c.Contains($old)){ throw 'C10.41 post-save model restoration hook anchor missing.' }
    $c=$c.Replace($old,$new)
}
Set-Content $controller $c -Encoding UTF8

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('StartAsterMaxC1041ReopenAudit();')){
    $anchor='StartAsterMaxC1034OutlineAudit();'
    if(-not $u.Contains($anchor)){ throw 'C10.41 reopen audit startup anchor missing.' }
    $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+'                StartAsterMaxC1041ReopenAudit();')
    Set-Content $ui $u -Encoding UTF8
}
$audit=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$a=[regex]::Replace((Get-Content $audit -Raw),"\r\n?","`n")
$anchor='                "A real result field is rendered in the integrated native viewport without stale/skipped render state.");'
$save=@'
                "A real result field is rendered in the integrated native viewport without stale/skipped render state.");
            string solvedProject=Path.Combine(directory,"B01-C10.41-solved.pmx");
            _controller.SaveToPmx(solvedProject);
            if(!File.Exists(AsterMaxProjectResultsStore.ManifestPath(solvedProject)))
                throw new IOException("Solved project result sidecar was not saved.");
            File.WriteAllText(Path.Combine(directory,"solved-project-save.json"),new JObject {
                ["status"]="PASS", ["project"]=solvedProject,
                ["bundle_sha256"]=AsterMaxProjectResultsStore.Hash(_asterMaxLoadedResults.SourceFile),
                ["model_fingerprint_sha256"]=_asterMaxLoadedResults.ResultModelFingerprintSha256
            }.ToString());
'@
$save=[regex]::Replace($save,"\r\n?","`n").TrimEnd()
if(-not $a.Contains('B01-C10.41-solved.pmx')){
    if(-not $a.Contains($anchor)){ throw 'C10.41 save-after-solve audit anchor missing.' }
    $a=$a.Replace($anchor,$save)
    Set-Content $audit $a -Encoding UTF8
}

# C10.41 RC1: the Mechanical ribbon is localized after C10.18, while the integrated
# results router intentionally uses stable English command keys. Canonicalize the visible
# es-CL captions here so real ribbon clicks stay inside the AsterMax results workspace
# instead of falling through to the inherited PrePoMax result toolbar and hiding it.
$integrated=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$i=[regex]::Replace((Get-Content $integrated -Raw),"\r\n?","`n")
if(-not $i.Contains('case "Contornos": caption = "Contours"; break;')){
    $routeAnchor="        private bool RouteAsterMaxIntegratedCommand(string caption)`n        {"
    if(-not $i.Contains($routeAnchor)){ throw 'C10.41 integrated result command router anchor missing.' }
    $localizedRoute=@'
        private bool RouteAsterMaxIntegratedCommand(string caption)
        {
            switch (caption)
            {
                case "Explorador": caption = "Results Explorer"; break;
                case "Viewport FEA": caption = "FEA Viewport"; break;
                case "Contornos": caption = "Contours"; break;
                case "Deformada": caption = "Deformed"; break;
                case "Ajustar": caption = "Fit"; break;
                case "Frontal": caption = "Front"; break;
                case "Superior": caption = "Top"; break;
                case "Derecha": caption = "Right"; break;
                case "Isométrica": case "Isometrica": caption = "Isometric"; break;
                case "Aristas": caption = "Edges"; break;
                case "Guardar": caption = "Save"; break;
                case "Auditoría": case "Auditoria": caption = "Auditoria"; break;
            }
'@
    $localizedRoute=[regex]::Replace($localizedRoute,"\r\n?","`n").TrimEnd()
    $i=$i.Replace($routeAnchor,$localizedRoute)
}

# The visible "Original" result command must also remain in the integrated viewport.
# Unlike "Deformada", it is deterministic: it turns deformation off instead of toggling.
if(-not $i.Contains('case "Original":')){
    $deformedAnchor='                case "Deformed": _showDeformed.Checked = !_showDeformed.Checked; return;'
    if(-not $i.Contains($deformedAnchor)){ throw 'C10.41 integrated Original handler anchor missing.' }
    $originalHandler=@'
                case "Deformed": _showDeformed.Checked = !_showDeformed.Checked; return;
                case "Original":
                    if (_showDeformed.Checked) _showDeformed.Checked = false;
                    else if (_view == null) RenderScene();
                    return;
'@
    $originalHandler=[regex]::Replace($originalHandler,"\r\n?","`n").TrimEnd()
    $i=$i.Replace($deformedAnchor,$originalHandler)
}
$resultOnlyOld='            bool resultOnly = caption == "Contours" || caption == "Deformed";'
$resultOnlyNew='            bool resultOnly = caption == "Contours" || caption == "Deformed" || caption == "Original";'
if($i.Contains($resultOnlyOld)) { $i=$i.Replace($resultOnlyOld,$resultOnlyNew) }
elseif(-not $i.Contains($resultOnlyNew)) { throw 'C10.41 integrated Original routing anchor missing.' }
Set-Content $integrated $i -Encoding UTF8

foreach($token in @('case "Contornos": caption = "Contours"; break;','case "Deformada": caption = "Deformed"; break;','case "Ajustar": caption = "Fit"; break;','case "Isométrica": case "Isometrica": caption = "Isometric"; break;','case "Original":','caption == "Original"')){
    if(-not $i.Contains($token)){ throw "C10.41 localized result routing token missing: $token" }
}

# C10.41 RC1: fail-closed exporter regression must validate behavior, not a localized
# exception string. The es-CL patch translates the error text after this fixture source is
# copied into the build tree, so matching the English message produced a false negative.
$workflowStates=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowStates.cs'
$w=[regex]::Replace((Get-Content $workflowStates -Raw),"\r\n?","`n")
$legacyLocalized=@'
                var incomplete=CreateAsterMaxStatusFixture(); incomplete.Sections.Clear();
                bool rejected=false;
                try{AsterMaxCodeAsterNativeExporter.Export(incomplete,output,"must-not-export");}
                catch(InvalidOperationException ex){rejected=ex.Message.Contains("Asignación de material incompleta");}
                if(!rejected) throw new InvalidOperationException("Native export accepted unassigned elements.");
'@
$legacyEnglish=@'
                var incomplete=CreateAsterMaxStatusFixture(); incomplete.Sections.Clear();
                bool rejected=false;
                try{AsterMaxCodeAsterNativeExporter.Export(incomplete,output,"must-not-export");}
                catch(InvalidOperationException ex){rejected=ex.Message.Contains("Material assignment incomplete");}
                if(!rejected) throw new InvalidOperationException("Native export accepted unassigned elements.");
'@
$behavioral=@'
                var incomplete=CreateAsterMaxStatusFixture(); incomplete.Sections.Clear();
                var incompleteAssignment=AsterMaxAssignmentQualityGate.Evaluate(incomplete);
                if(incompleteAssignment.Status=="READY")
                    throw new InvalidOperationException("Unassigned exporter fixture unexpectedly passed the assignment gate.");
                string forbiddenDeck=System.IO.Path.Combine(output,"must-not-export.comm");
                if(System.IO.File.Exists(forbiddenDeck)) System.IO.File.Delete(forbiddenDeck);
                bool rejected=false;
                try{AsterMaxCodeAsterNativeExporter.Export(incomplete,output,"must-not-export");}
                catch(InvalidOperationException){rejected=true;}
                if(!rejected || System.IO.File.Exists(forbiddenDeck))
                    throw new InvalidOperationException("Native export accepted unassigned elements.");
'@
$legacyLocalized=[regex]::Replace($legacyLocalized,"\r\n?","`n").TrimEnd()
$legacyEnglish=[regex]::Replace($legacyEnglish,"\r\n?","`n").TrimEnd()
$behavioral=[regex]::Replace($behavioral,"\r\n?","`n").TrimEnd()
if($w.Contains($legacyLocalized)) { $w=$w.Replace($legacyLocalized,$behavioral) }
elseif($w.Contains($legacyEnglish)) { $w=$w.Replace($legacyEnglish,$behavioral) }
elseif(-not $w.Contains('Unassigned exporter fixture unexpectedly passed the assignment gate.')) {
    throw 'C10.41 localization-safe exporter regression anchor missing.'
}
Set-Content $workflowStates $w -Encoding UTF8

Write-Host 'C10.41 PMX result snapshots + revision/hash validation + localized integrated-result routing + localization-safe exporter audit applied.' -ForegroundColor Green

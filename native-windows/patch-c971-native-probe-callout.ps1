param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $p)){throw 'C9.70 native 3D probe must be applied before C9.71.'}
$s=Get-Content $p -Raw

# vtkControl already owns a native probe widget which is positioned at the picked point and asks
# Controller_GetAnnotationText for its text. Bind that callback to the active AsterMax results
# scene so the on-renderer callout uses the exact same field/unit/bundle as the contour and HUD.
$old=@'
            _view.SetScalarBarColorSpectrum(colorContract.CreateVtkSpectrum());
            _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");
            _view.AddCells(data);
'@
$new=@'
            _view.SetScalarBarColorSpectrum(colorContract.CreateVtkSpectrum());
            _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");
            _view.Controller_GetAnnotationText=NativeProbeAnnotation;
            _view.AddCells(data);
'@
if(-not $s.Contains($old)){throw 'C9.71 renderer callback anchor missing.'}
$s=$s.Replace($old,$new)

$anchor='        private void OnNativeVtkSelection(double[] pickedPoint, double[] direction, double[][] plane, CaeGlobals.vtkSelectOperation operation, string[] actorNames)'
$methods=@'
        private string NativeProbeAnnotation(string globalPointId)
        {
            if(_scene==null) return "No active FEA result";
            if(_scene.FeaValuesInvented) throw new InvalidOperationException("Synthetic FEA scene rejected by native callout.");
            int oneBased;
            if(!Int32.TryParse(globalPointId,System.Globalization.NumberStyles.Integer,System.Globalization.CultureInfo.InvariantCulture,out oneBased))
                throw new InvalidOperationException("VTK probe did not provide a numeric node id.");
            int i=oneBased-1;
            if(i<0 || i>=_bundle.NodeCount) throw new InvalidOperationException("VTK probe node id is outside the results bundle.");
            double value=_bundle.ProbeNode(i,_scene.Field);
            var xyz=_bundle.Coordinates[i];
            return String.Format(System.Globalization.CultureInfo.InvariantCulture,
                "N{0}  {1}: {2:G9} {3}\nX {4:G6}  Y {5:G6}  Z {6:G6} mm",
                oneBased,_scene.Field,value,_scene.Unit,xyz[0],xyz[1],xyz[2]);
        }

        // Deterministic harness surface: verifies the exact text consumed by vtkControl's own
        // probe widget without pretending that CI injected a physical mouse click.
        public string NativeProbeAnnotationSummary(int oneBasedNodeId)
        {
            RefreshMetadata();
            return NativeProbeAnnotation(oneBasedNodeId.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }

        public bool NativeProbeAnnotationRejectsInvalidNode()
        {
            RefreshMetadata();
            try { NativeProbeAnnotation((_bundle.NodeCount+1).ToString(System.Globalization.CultureInfo.InvariantCulture)); return false; }
            catch(InvalidOperationException) { return true; }
        }

'@
if(-not $s.Contains($anchor)){throw 'C9.71 native selection anchor missing.'}
$s=$s.Replace($anchor,$methods+$anchor)

Set-Content $p $s -Encoding UTF8
Write-Host 'C9.71 native vtkControl probe callout bound to real Results Bundle.' -ForegroundColor Green

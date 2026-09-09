param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $p)){throw 'C9.69 results binding must be applied before C9.70.'}
$s=Get-Content $p -Raw

# Add a renderer-derived probe contract. The VTK event supplies the world-space point produced by
# vtkPointPicker. We only accept a point that resolves to one and only one rendered node within a
# strict geometric tolerance; there is no arbitrary nearest-node fallback.
$anchor='    internal sealed class AsterMaxResultsViewportForm : Form'
if(-not $s.Contains($anchor)){throw 'C9.70 viewport class anchor missing.'}
$probe=@'
    internal sealed class AsterMaxNativeProbeResult
    {
        public int NodeIndex { get; private set; }
        public double Value { get; private set; }
        public string Field { get; private set; }
        public string Unit { get; private set; }
        public double[] PickedPoint { get; private set; }
        public bool RendererDerived { get; private set; }
        public bool FeaValuesInvented { get; private set; }

        private AsterMaxNativeProbeResult() { }

        public static AsterMaxNativeProbeResult FromRendererPoint(AsterMaxResultsBundle bundle, AsterMaxResultsScene scene, double[] pickedPoint)
        {
            if(bundle==null) throw new ArgumentNullException("bundle");
            if(scene==null) throw new ArgumentNullException("scene");
            if(scene.FeaValuesInvented) throw new InvalidOperationException("Synthetic FEA scene rejected by probe.");
            if(pickedPoint==null || pickedPoint.Length<3) throw new ArgumentException("VTK picked point is required.","pickedPoint");
            if(scene.DeformedCoordinates==null || scene.DeformedCoordinates.Length!=bundle.NodeCount)
                throw new InvalidOperationException("Deformed render coordinates are unavailable.");

            double xmin=Double.PositiveInfinity,xmax=Double.NegativeInfinity;
            double ymin=Double.PositiveInfinity,ymax=Double.NegativeInfinity;
            double zmin=Double.PositiveInfinity,zmax=Double.NegativeInfinity;
            foreach(var q in scene.DeformedCoordinates){xmin=Math.Min(xmin,q[0]);xmax=Math.Max(xmax,q[0]);ymin=Math.Min(ymin,q[1]);ymax=Math.Max(ymax,q[1]);zmin=Math.Min(zmin,q[2]);zmax=Math.Max(zmax,q[2]);}
            double diag=Math.Sqrt((xmax-xmin)*(xmax-xmin)+(ymax-ymin)*(ymax-ymin)+(zmax-zmin)*(zmax-zmin));
            double tol=Math.Max(1e-9,diag*1e-7); // mm; matching tolerance only, never used to alter FEA values.
            double tol2=tol*tol;
            int match=-1;
            for(int i=0;i<scene.DeformedCoordinates.Length;i++)
            {
                var q=scene.DeformedCoordinates[i]; double dx=q[0]-pickedPoint[0],dy=q[1]-pickedPoint[1],dz=q[2]-pickedPoint[2];
                if(dx*dx+dy*dy+dz*dz<=tol2)
                {
                    if(match>=0) throw new InvalidOperationException("Ambiguous VTK node pick rejected.");
                    match=i;
                }
            }
            if(match<0) throw new InvalidOperationException("VTK pick did not resolve to an exact rendered node; no nearest-node fallback is permitted.");
            return new AsterMaxNativeProbeResult {
                NodeIndex=match,
                Value=bundle.ProbeNode(match,scene.Field),
                Field=scene.Field,
                Unit=scene.Unit,
                PickedPoint=new[]{pickedPoint[0],pickedPoint[1],pickedPoint[2]},
                RendererDerived=true,
                FeaValuesInvented=false
            };
        }

        public string Describe()
        {
            return String.Format(System.Globalization.CultureInfo.InvariantCulture,
                "renderer=true|field={0}|unit={1}|node={2}|value={3:R}|x={4:R}|y={5:R}|z={6:R}|invented=false",
                Field,Unit,NodeIndex+1,Value,PickedPoint[0],PickedPoint[1],PickedPoint[2]);
        }
    }

'@
$s=$s.Replace($anchor,$probe+$anchor)

# Wire vtkControl's native selection event after the actor has been added. Node mode causes vtkControl
# to use its point-picking path; the callback carries the renderer/world picked point.
$old=@'
            _view.AddCells(data);
            _view.AdjustCameraDistanceAndClipping();
'@
$new=@'
            _view.AddCells(data);
            _view.SetSelectBy(CaeGlobals.vtkSelectBy.Node);
            _view.OnMouseLeftButtonUpSelection+=OnNativeVtkSelection;
            _view.AdjustCameraDistanceAndClipping();
'@
if(-not $s.Contains($old)){throw 'C9.70 AddCells anchor missing.'}
$s=$s.Replace($old,$new)

# Avoid event retention when the viewport is rebuilt for another field.
$old='            if(_view!=null){_host.Controls.Remove(_view);_view.Dispose();}'
$new='            if(_view!=null){_view.OnMouseLeftButtonUpSelection-=OnNativeVtkSelection;_host.Controls.Remove(_view);_view.Dispose();}'
if(-not $s.Contains($old)){throw 'C9.70 viewport disposal anchor missing.'}
$s=$s.Replace($old,$new)

# Add callback plus a public deterministic harness surface before RendererContractSummary.
$summaryAnchor='        public string RendererContractSummary()'
$methods=@'
        private void OnNativeVtkSelection(double[] pickedPoint, double[] direction, double[][] plane, CaeGlobals.vtkSelectOperation operation, string[] actorNames)
        {
            if(pickedPoint==null || _scene==null) return;
            try
            {
                var probe=AsterMaxNativeProbeResult.FromRendererPoint(_bundle,_scene,pickedPoint);
                _probeNode.Value=Math.Max(_probeNode.Minimum,Math.Min(_probeNode.Maximum,probe.NodeIndex+1));
                var xyz=_bundle.Coordinates[probe.NodeIndex];
                _probeLabel.Text=String.Format(System.Globalization.CultureInfo.InvariantCulture,
                    "VTK PICK N{0}: {1:G9} {2}\r\n({3:G6}, {4:G6}, {5:G6}) mm",
                    probe.NodeIndex+1,probe.Value,probe.Unit,xyz[0],xyz[1],xyz[2]);
                _status.Text=_scene.Field+" ["+_scene.Unit+"] • VTK node probe N"+(probe.NodeIndex+1);
            }
            catch(InvalidOperationException ex)
            {
                _status.Text="Probe rejected: "+ex.Message;
            }
        }

        public string NativeProbeContractSummary(int zeroBasedNodeIndex)
        {
            RefreshMetadata();
            if(zeroBasedNodeIndex<0 || zeroBasedNodeIndex>=_bundle.NodeCount) throw new ArgumentOutOfRangeException("zeroBasedNodeIndex");
            var q=_scene.DeformedCoordinates[zeroBasedNodeIndex];
            return AsterMaxNativeProbeResult.FromRendererPoint(_bundle,_scene,new[]{q[0],q[1],q[2]}).Describe();
        }

        public bool NativeProbeRejectsNonNodePoint()
        {
            RefreshMetadata();
            var q=_scene.DeformedCoordinates[0];
            try
            {
                AsterMaxNativeProbeResult.FromRendererPoint(_bundle,_scene,new[]{q[0]+0.123456789,q[1]+0.234567891,q[2]+0.345678912});
                return false;
            }
            catch(InvalidOperationException){return true;}
        }

'@
if(-not $s.Contains($summaryAnchor)){throw 'C9.70 renderer summary anchor missing.'}
$s=$s.Replace($summaryAnchor,$methods+$summaryAnchor)

Set-Content $p $s -Encoding UTF8
Write-Host 'C9.70 native renderer-derived 3D probe injected.' -ForegroundColor Green

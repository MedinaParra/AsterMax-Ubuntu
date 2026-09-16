param([string]$Root)
$ErrorActionPreference='Stop'

$rwPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$vtkPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $rwPath)){throw 'AsterMaxResultsWorkspace.cs missing.'}
if(!(Test-Path $vtkPath)){throw 'AsterMaxVtkResultsBinding.cs missing.'}

# ---- Results bundle: admit real TETRA4/TETRA10/HEXA8 connectivity dynamically. ----
$rw=Get-Content $rwPath -Raw
if(-not $rw.Contains('public int[] CellTypes { get; private set; }')) {
    $rw=$rw.Replace('        public int[][] Connectivity { get; private set; }',
                    '        public int[][] Connectivity { get; private set; }'+[Environment]::NewLine+'        public int[] CellTypes { get; private set; }')
}
$rw=$rw.Replace('            b.Connectivity = ReadIntJagged(root["arrays"]["connectivity"], 8);',@'
            b.Connectivity = ReadConnectivity(root["arrays"]["connectivity"]);
            b.CellTypes = root["arrays"]["cell_types"] == null ? InferCellTypes(b.Connectivity) : ReadIntVector(root["arrays"]["cell_types"]);
'@.TrimEnd())

$legacyReader=@'
        private static int[][] ReadIntJagged(JToken token, int width)
        {
            var rows = token.Select(row => row.Select(x => (int)x).ToArray()).ToArray();
            if (rows.Any(row => row.Length != width)) throw new InvalidDataException("Unexpected connectivity width.");
            return rows;
        }
'@
$dynamicReader=@'
        private static int[][] ReadConnectivity(JToken token)
        {
            if(token==null) throw new InvalidDataException("Result mesh connectivity is missing.");
            var rows=token.Select(row=>row.Select(x=>(int)x).ToArray()).ToArray();
            if(rows.Any(row=>row.Length!=4 && row.Length!=8 && row.Length!=10))
                throw new InvalidDataException("Unsupported result connectivity width; expected TETRA4, HEXA8 or TETRA10.");
            return rows;
        }
        private static int[] ReadIntVector(JToken token)
        {
            return token==null ? new int[0] : token.Select(x=>(int)x).ToArray();
        }
        private static int[] InferCellTypes(int[][] connectivity)
        {
            return connectivity.Select(c=>c.Length==4?10:(c.Length==8?12:(c.Length==10?24:-1))).ToArray();
        }
'@
if($rw.Contains($legacyReader)) {$rw=$rw.Replace($legacyReader,$dynamicReader)}
elseif(-not $rw.Contains('private static int[][] ReadConnectivity(JToken token)')) {throw 'Dynamic connectivity reader anchor missing.'}

$rw=$rw.Replace('                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount || Connectivity.Length != ElementCount)',
                '                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount || Connectivity.Length != ElementCount ||'+[Environment]::NewLine+'                CellTypes == null || CellTypes.Length != ElementCount)')

$legacyValidation='            if (Connectivity.Any(c => c.Length != 8 || c.Any(id => id < 1 || id > NodeCount)))'+[Environment]::NewLine+'                throw new InvalidDataException("Invalid HEXA8 connectivity detected.");'
$dynamicValidation=@'
            for(int i=0;i<Connectivity.Length;i++)
            {
                int expected=CellTypes[i]==10?4:(CellTypes[i]==12?8:(CellTypes[i]==24?10:0));
                if(expected==0) throw new InvalidDataException("Unsupported VTK cell type in result bundle: "+CellTypes[i]);
                int[] cell=Connectivity[i];
                if(cell==null || cell.Length!=expected) throw new InvalidDataException("Result connectivity/cell-type mismatch at element "+(i+1)+".");
                if(cell.Any(id=>id<1 || id>NodeCount)) throw new InvalidDataException("Result connectivity contains a node id outside the result mesh.");
                if(cell.Distinct().Count()!=expected) throw new InvalidDataException("Result connectivity contains duplicate node ids.");
            }
'@
if($rw.Contains($legacyValidation)) {$rw=$rw.Replace($legacyValidation,$dynamicValidation.TrimEnd())}
elseif(-not $rw.Contains('Result connectivity/cell-type mismatch at element')) {throw 'Dynamic connectivity validation anchor missing.'}
if($rw.Contains('Unexpected connectivity width.')) {throw 'Legacy fixed-width connectivity reader remains.'}
Set-Content $rwPath $rw -Encoding UTF8

# ---- VTK viewport: convert volume cells to the exterior 2D surface before vtkMaxActor poly rendering. ----
$vtk=Get-Content $vtkPath -Raw
if($vtk.Contains('        public const int VtkHexahedron = 12;') -and -not $vtk.Contains('VtkQuadraticTriangle')) {
    $vtk=$vtk.Replace('        public const int VtkHexahedron = 12;',@'
        public const int VtkTriangle = 5;
        public const int VtkQuad = 9;
        public const int VtkTetra = 10;
        public const int VtkHexahedron = 12;
        public const int VtkQuadraticTriangle = 22;
        public const int VtkQuadraticTetra = 24;
'@.TrimEnd())
}

$availability='            if (bundle.Connectivity == null || bundle.Connectivity.Length != bundle.ElementCount)'+[Environment]::NewLine+'                throw new InvalidOperationException("Result mesh connectivity is unavailable.");'
if($vtk.Contains($availability) -and -not $vtk.Contains('Result mesh cell types are unavailable.')) {
    $vtk=$vtk.Replace($availability,$availability+[Environment]::NewLine+'            if (bundle.CellTypes == null || bundle.CellTypes.Length != bundle.ElementCount)'+[Environment]::NewLine+'                throw new InvalidOperationException("Result mesh cell types are unavailable.");')
}

$buildAnchor='        public static vtkMaxActorData BuildActorData(AsterMaxResultsBundle bundle, AsterMaxResultsScene scene)'
if(-not $vtk.Contains('private static SurfaceMesh BuildExteriorSurface(AsterMaxResultsBundle bundle)')) {
    if(-not $vtk.Contains($buildAnchor)){throw 'BuildActorData anchor missing.'}
    $helpers=@'
        private sealed class SurfaceFace { public int Type; public int[] Nodes; public int Count; }
        private sealed class SurfaceMesh { public int[][] Connectivity; public int[] Types; }

        private static string SurfaceFaceKey(int[] nodes,int cornerCount)
        {
            return cornerCount.ToString()+":"+String.Join(",",nodes.Take(cornerCount).OrderBy(x=>x));
        }
        private static void AddSurfaceFace(System.Collections.Generic.Dictionary<string,SurfaceFace> faces,int type,int[] nodes,int cornerCount)
        {
            string key=SurfaceFaceKey(nodes,cornerCount); SurfaceFace face;
            if(faces.TryGetValue(key,out face)){face.Count++;return;}
            faces.Add(key,new SurfaceFace{Type=type,Nodes=nodes,Count=1});
        }
        private static SurfaceMesh BuildExteriorSurface(AsterMaxResultsBundle bundle)
        {
            var faces=new System.Collections.Generic.Dictionary<string,SurfaceFace>(StringComparer.Ordinal);
            for(int i=0;i<bundle.Connectivity.Length;i++)
            {
                int[] c=bundle.Connectivity[i].Select(id=>id-1).ToArray();
                int type=bundle.CellTypes[i];
                if(type==VtkTetra)
                {
                    AddSurfaceFace(faces,VtkTriangle,new[]{c[0],c[2],c[1]},3);
                    AddSurfaceFace(faces,VtkTriangle,new[]{c[0],c[1],c[3]},3);
                    AddSurfaceFace(faces,VtkTriangle,new[]{c[1],c[2],c[3]},3);
                    AddSurfaceFace(faces,VtkTriangle,new[]{c[2],c[0],c[3]},3);
                }
                else if(type==VtkQuadraticTetra)
                {
                    // VTK quadratic tetra: corners 0..3; midside nodes 01,12,20,03,13,23.
                    AddSurfaceFace(faces,VtkQuadraticTriangle,new[]{c[0],c[2],c[1],c[6],c[5],c[4]},3);
                    AddSurfaceFace(faces,VtkQuadraticTriangle,new[]{c[0],c[1],c[3],c[4],c[8],c[7]},3);
                    AddSurfaceFace(faces,VtkQuadraticTriangle,new[]{c[1],c[2],c[3],c[5],c[9],c[8]},3);
                    AddSurfaceFace(faces,VtkQuadraticTriangle,new[]{c[2],c[0],c[3],c[6],c[7],c[9]},3);
                }
                else if(type==VtkHexahedron)
                {
                    AddSurfaceFace(faces,VtkQuad,new[]{c[0],c[3],c[2],c[1]},4);
                    AddSurfaceFace(faces,VtkQuad,new[]{c[4],c[5],c[6],c[7]},4);
                    AddSurfaceFace(faces,VtkQuad,new[]{c[0],c[1],c[5],c[4]},4);
                    AddSurfaceFace(faces,VtkQuad,new[]{c[1],c[2],c[6],c[5]},4);
                    AddSurfaceFace(faces,VtkQuad,new[]{c[2],c[3],c[7],c[6]},4);
                    AddSurfaceFace(faces,VtkQuad,new[]{c[3],c[0],c[4],c[7]},4);
                }
                else throw new NotSupportedException("Unsupported volume VTK result cell type: "+type);
            }
            if(faces.Values.Any(x=>x.Count>2)) throw new InvalidOperationException("Result mesh contains a non-manifold face shared by more than two volume cells.");
            SurfaceFace[] exterior=faces.Values.Where(x=>x.Count==1).ToArray();
            if(exterior.Length==0) throw new InvalidOperationException("Result mesh exterior surface is empty.");
            return new SurfaceMesh{Connectivity=exterior.Select(x=>x.Nodes).ToArray(),Types=exterior.Select(x=>x.Type).ToArray()};
        }

'@
    $vtk=$vtk.Replace($buildAnchor,$helpers+$buildAnchor)
}

$cellPattern='(?ms)            data\.Geometry\.Cells\.Ids = Enumerable\.Range\(1, bundle\.ElementCount\)\.ToArray\(\);\s*\r?\n(?:.*?\r?\n)*?            data\.Geometry\.Cells\.Types = (?:Enumerable\.Repeat\(VtkHexahedron, bundle\.ElementCount\)|bundle\.CellTypes)\.ToArray\(\);'
$cellReplacement=@'
            SurfaceMesh surface=BuildExteriorSurface(bundle);
            data.Geometry.Cells.Ids = Enumerable.Range(1, surface.Connectivity.Length).ToArray();
            data.Geometry.Cells.CellNodeIds = surface.Connectivity;
            data.Geometry.Cells.Types = surface.Types;
'@
$vtk2=[regex]::Replace($vtk,$cellPattern,$cellReplacement.TrimEnd(),1)
if($vtk2 -eq $vtk -and -not $vtk.Contains('SurfaceMesh surface=BuildExteriorSurface(bundle);')) {throw 'Raw volume cell assignment block not found.'}
$vtk=$vtk2

# Replace the final C9.71 RenderScene implementation, preserving color bar, annotation and node probe.
$renderPattern='(?ms)        private void RenderScene\(\)\s*\{.*?\r?\n        \}\r?\n\r?\n        private string NativeProbeAnnotation'
$renderReplacement=@'
        private void RenderScene()
        {
            try
            {
                RefreshMetadata();
                var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,_scene);
                if(_view!=null)
                {
                    _view.OnMouseLeftButtonUpSelection-=OnNativeVtkSelection;
                    _host.Controls.Remove(_view); _view.Dispose(); _view=null;
                }
                _view=new vtkControl.vtkControl { Dock=DockStyle.Fill };
                _host.Controls.Add(_view);
                var colorContract=AsterMaxResultsColorContract.FromScene(_scene);
                _view.SetScalarBarColorSpectrum(colorContract.CreateVtkSpectrum());
                _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");
                _view.Controller_GetAnnotationText=NativeProbeAnnotation;
                // vtkMaxActor poly rendering receives only exterior TRI/QUADRATIC_TRI/QUAD faces.
                _view.AddCells(data);
                _view.SetSelectBy(CaeGlobals.vtkSelectBy.Node);
                _view.OnMouseLeftButtonUpSelection+=OnNativeVtkSelection;
                _view.AdjustCameraDistanceAndClipping();
                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • exterior surface rendered";
            }
            catch(Exception ex)
            {
                if(_view!=null)
                {
                    try{_view.OnMouseLeftButtonUpSelection-=OnNativeVtkSelection;}catch{}
                    _host.Controls.Remove(_view); _view.Dispose(); _view=null;
                }
                _status.Text="Render blocked: "+ex.GetType().Name;
                MessageBox.Show(this,"AsterMax results renderer blocked safely.\n\n"+ex.GetType().Name+": "+ex.Message,
                    "AsterMax Results",MessageBoxButtons.OK,MessageBoxIcon.Error);
            }
        }

        private string NativeProbeAnnotation
'@
$vtk2=[regex]::Replace($vtk,$renderPattern,$renderReplacement,1)
if($vtk2 -eq $vtk -and -not $vtk.Contains('exterior surface rendered')) {throw 'Final RenderScene method not found.'}
$vtk=$vtk2

if($vtk.Contains('data.Geometry.Cells.Types = bundle.CellTypes.ToArray();')) {throw 'Raw volume VTK cells still reach vtkMaxActor poly renderer.'}
if($vtk.Contains('Enumerable.Repeat(VtkHexahedron, bundle.ElementCount)')) {throw 'Legacy HEXA8-only renderer remains.'}
foreach($token in @('VtkQuadraticTriangle = 22','BuildExteriorSurface','SurfaceMesh surface=BuildExteriorSurface(bundle)','exterior surface rendered')) {
    if(-not $vtk.Contains($token)){throw "Viewport hotfix token missing: $token"}
}
Set-Content $vtkPath $vtk -Encoding UTF8
Write-Host 'C10.10.1 TETRA results viewport hotfix: exterior surface extraction + safe renderer boundary applied.' -ForegroundColor Green

param([string]$Root)
$ErrorActionPreference='Stop'

# C10.10.1 hotfix — results bundles produced by the production MED bridge can contain
# TETRA4 (4 nodes), TETRA10 (10 nodes), HEXA8 (8 nodes), or supported mixed meshes.
# The historical C9.67 UI reader hard-coded HEXA8 and passed 3D volume cells directly
# to vtkMaxActor.CreatePolyFromData. vtkMaxActor's poly path accepts only 0D/1D/2D
# cells, so a valid TETRA10 result crashed in AddCellDataToPoly with NotSupportedException.
# This patch keeps the real volume connectivity for provenance/validation, but converts
# it to the exterior visualization surface before calling vtkControl.AddCells.

$rwPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$vtkPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $rwPath)){ throw 'C10.10.1 connectivity hotfix requires AsterMaxResultsWorkspace.cs.' }
if(!(Test-Path $vtkPath)){ throw 'C10.10.1 connectivity hotfix requires AsterMaxVtkResultsBinding.cs.' }

$rw=Get-Content $rwPath -Raw

if(-not $rw.Contains('public int[] CellTypes { get; private set; }')){
    $anchor='        public int[][] Connectivity { get; private set; }'
    if(-not $rw.Contains($anchor)){ throw 'Connectivity property anchor missing.' }
    $rw=$rw.Replace($anchor,$anchor+[Environment]::NewLine+'        public int[] CellTypes { get; private set; }')
}

$legacyLoad='            b.Connectivity = ReadIntJagged(root["arrays"]["connectivity"], 8);'
$newLoad=@'
            b.Connectivity = ReadConnectivity(root["arrays"]["connectivity"]);
            b.CellTypes = root["arrays"]["cell_types"] == null
                ? InferCellTypes(b.Connectivity)
                : ReadIntVector(root["arrays"]["cell_types"]);
'@
if($rw.Contains($legacyLoad)){
    $rw=$rw.Replace($legacyLoad,$newLoad.TrimEnd())
}
elseif(-not $rw.Contains('b.Connectivity = ReadConnectivity(root["arrays"]["connectivity"]);')){
    throw 'Connectivity loader anchor missing.'
}

$legacyReader=@'
        private static int[][] ReadIntJagged(JToken token, int width)
        {
            var rows = token.Select(row => row.Select(x => (int)x).ToArray()).ToArray();
            if (rows.Any(row => row.Length != width)) throw new InvalidDataException("Unexpected connectivity width.");
            return rows;
        }
'@
$newReader=@'
        private static int[][] ReadConnectivity(JToken token)
        {
            if (token == null) throw new InvalidDataException("Result mesh connectivity is missing.");
            var rows = token.Select(row => row.Select(x => (int)x).ToArray()).ToArray();
            if (rows.Any(row => row.Length != 4 && row.Length != 8 && row.Length != 10))
                throw new InvalidDataException("Unsupported result connectivity width; expected TETRA4, HEXA8 or TETRA10.");
            return rows;
        }

        private static int[] ReadIntVector(JToken token)
        {
            if (token == null) return new int[0];
            return token.Select(x => (int)x).ToArray();
        }

        private static int[] InferCellTypes(int[][] connectivity)
        {
            return connectivity.Select(c => c.Length == 4 ? 10 : (c.Length == 8 ? 12 : (c.Length == 10 ? 24 : -1))).ToArray();
        }
'@
if($rw.Contains($legacyReader)){
    $rw=$rw.Replace($legacyReader,$newReader)
}
elseif(-not $rw.Contains('private static int[][] ReadConnectivity(JToken token)')){
    throw 'Connectivity reader anchor missing.'
}

$legacyCounts='                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount || Connectivity.Length != ElementCount)'
$newCounts='                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount || Connectivity.Length != ElementCount ||'+[Environment]::NewLine+'                CellTypes == null || CellTypes.Length != ElementCount)'
if($rw.Contains($legacyCounts)){
    $rw=$rw.Replace($legacyCounts,$newCounts)
}
elseif(-not $rw.Contains('CellTypes == null || CellTypes.Length != ElementCount')){
    throw 'Result count validation anchor missing.'
}

$legacyHex='            if (Connectivity.Any(c => c.Length != 8 || c.Any(id => id < 1 || id > NodeCount)))'+[Environment]::NewLine+'                throw new InvalidDataException("Invalid HEXA8 connectivity detected.");'
$newConnectivityValidation=@'
            for (int i = 0; i < Connectivity.Length; i++)
            {
                int expected = CellTypes[i] == 10 ? 4 : (CellTypes[i] == 12 ? 8 : (CellTypes[i] == 24 ? 10 : 0));
                if (expected == 0)
                    throw new InvalidDataException("Unsupported VTK cell type in result bundle: " + CellTypes[i]);
                int[] cell = Connectivity[i];
                if (cell == null || cell.Length != expected)
                    throw new InvalidDataException(String.Format(CultureInfo.InvariantCulture,
                        "Result connectivity/cell-type mismatch at element {0}: VTK {1} requires {2} nodes, got {3}.",
                        i + 1, CellTypes[i], expected, cell == null ? 0 : cell.Length));
                if (cell.Any(id => id < 1 || id > NodeCount))
                    throw new InvalidDataException("Result connectivity contains a node id outside the result mesh.");
                if (cell.Distinct().Count() != expected)
                    throw new InvalidDataException("Result connectivity contains duplicate node ids.");
            }
'@
if($rw.Contains($legacyHex)){
    $rw=$rw.Replace($legacyHex,$newConnectivityValidation.TrimEnd())
}
elseif(-not $rw.Contains('Result connectivity/cell-type mismatch at element')){
    throw 'Legacy HEXA8 validation anchor missing.'
}

if($rw.Contains('Unexpected connectivity width.')){
    throw 'Hard-coded connectivity-width rejection remains in AsterMaxResultsWorkspace.cs.'
}
Set-Content $rwPath $rw -Encoding UTF8

$vtk=Get-Content $vtkPath -Raw
$legacyConst='        public const int VtkHexahedron = 12;'
$newConst=@'
        public const int VtkTriangle = 5;
        public const int VtkQuad = 9;
        public const int VtkTetra = 10;
        public const int VtkHexahedron = 12;
        public const int VtkQuadraticTriangle = 22;
        public const int VtkQuadraticTetra = 24;
'@
if($vtk.Contains($legacyConst)){
    $vtk=$vtk.Replace($legacyConst,$newConst.TrimEnd())
}
elseif(-not $vtk.Contains('public const int VtkQuadraticTriangle = 22;')){
    throw 'VTK cell constant anchor missing.'
}

$legacyAvailability=@'
            if (bundle.Connectivity == null || bundle.Connectivity.Length != bundle.ElementCount)
                throw new InvalidOperationException("Result mesh connectivity is unavailable.");
'@
$newAvailability=@'
            if (bundle.Connectivity == null || bundle.Connectivity.Length != bundle.ElementCount)
                throw new InvalidOperationException("Result mesh connectivity is unavailable.");
            if (bundle.CellTypes == null || bundle.CellTypes.Length != bundle.ElementCount)
                throw new InvalidOperationException("Result mesh cell types are unavailable.");
'@
if($vtk.Contains($legacyAvailability)){
    $vtk=$vtk.Replace($legacyAvailability,$newAvailability)
}
elseif(-not $vtk.Contains('Result mesh cell types are unavailable.')){
    throw 'VTK result availability anchor missing.'
}

# Inject exterior-surface extraction. The native vtkMaxActor poly renderer only accepts
# surface/edge/vertex cells. Internal faces are removed by their sorted corner-node key.
$buildAnchor='        public static vtkMaxActorData BuildActorData(AsterMaxResultsBundle bundle, AsterMaxResultsScene scene)'
if(-not $vtk.Contains('private static SurfaceMesh BuildExteriorSurface(AsterMaxResultsBundle bundle)')){
    if(-not $vtk.Contains($buildAnchor)){ throw 'VTK BuildActorData anchor missing.' }
    $surfaceHelpers=@'
        private sealed class SurfaceFace
        {
            public int Type;
            public int[] Nodes;
            public int Count;
        }

        private sealed class SurfaceMesh
        {
            public int[][] Connectivity;
            public int[] Types;
        }

        private static string SurfaceFaceKey(int[] nodes, int cornerCount)
        {
            int[] corners=nodes.Take(cornerCount).OrderBy(x=>x).ToArray();
            return cornerCount.ToString()+":"+String.Join(",",corners);
        }

        private static void AddSurfaceFace(System.Collections.Generic.Dictionary<string,SurfaceFace> faces,
                                           int type,int[] nodes,int cornerCount)
        {
            string key=SurfaceFaceKey(nodes,cornerCount);
            SurfaceFace face;
            if(faces.TryGetValue(key,out face))
            {
                face.Count++;
                return;
            }
            faces.Add(key,new SurfaceFace { Type=type, Nodes=nodes, Count=1 });
        }

        private static SurfaceMesh BuildExteriorSurface(AsterMaxResultsBundle bundle)
        {
            var faces=new System.Collections.Generic.Dictionary<string,SurfaceFace>(StringComparer.Ordinal);
            for(int i=0;i<bundle.Connectivity.Length;i++)
            {
                // MED/Code_Aster ids are one-based; PartExchangeData requires zero-based point indices.
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
                    // VTK quadratic tetra order: 0..3 corners, then edges
                    // 01,12,20,03,13,23. Preserve midside nodes on every exterior face.
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
            SurfaceFace[] exterior=faces.Values.Where(x=>x.Count==1).ToArray();
            if(exterior.Length==0) throw new InvalidOperationException("Result mesh exterior surface is empty.");
            if(faces.Values.Any(x=>x.Count>2))
                throw new InvalidOperationException("Result mesh contains a non-manifold face shared by more than two volume cells.");
            return new SurfaceMesh {
                Connectivity=exterior.Select(x=>x.Nodes).ToArray(),
                Types=exterior.Select(x=>x.Type).ToArray()
            };
        }

'@
    $vtk=$vtk.Replace($buildAnchor,$surfaceHelpers+$buildAnchor)
}

$legacyCells=@'
            data.Geometry.Cells.Ids = Enumerable.Range(1, bundle.ElementCount).ToArray();
            // C9.64 connectivity is one-based Code_Aster/MED numbering. PartExchangeData expects
            // zero-based point indices when constructing VTK cells.
            data.Geometry.Cells.CellNodeIds = bundle.Connectivity.Select(c => c.Select(id => id - 1).ToArray()).ToArray();
            data.Geometry.Cells.Types = bundle.CellTypes.ToArray();
'@
$surfaceCells=@'
            SurfaceMesh surface=BuildExteriorSurface(bundle);
            data.Geometry.Cells.Ids = Enumerable.Range(1, surface.Connectivity.Length).ToArray();
            data.Geometry.Cells.CellNodeIds = surface.Connectivity;
            data.Geometry.Cells.Types = surface.Types;
'@
if($vtk.Contains($legacyCells)){
    $vtk=$vtk.Replace($legacyCells,$surfaceCells.TrimEnd())
}
elseif($vtk.Contains('data.Geometry.Cells.Types = Enumerable.Repeat(VtkHexahedron, bundle.ElementCount).ToArray();')){
    $legacyOld=@'
            data.Geometry.Cells.Ids = Enumerable.Range(1, bundle.ElementCount).ToArray();
            // C9.64 connectivity is one-based Code_Aster/MED numbering. PartExchangeData expects
            // zero-based point indices when constructing VTK cells.
            data.Geometry.Cells.CellNodeIds = bundle.Connectivity.Select(c => c.Select(id => id - 1).ToArray()).ToArray();
            data.Geometry.Cells.Types = Enumerable.Repeat(VtkHexahedron, bundle.ElementCount).ToArray();
'@
    if(-not $vtk.Contains($legacyOld)){ throw 'Legacy VTK cell assignment block missing.' }
    $vtk=$vtk.Replace($legacyOld,$surfaceCells.TrimEnd())
}
elseif(-not $vtk.Contains('SurfaceMesh surface=BuildExteriorSurface(bundle);')){
    throw 'VTK surface cell assignment anchor missing.'
}

$vtk=$vtk.Replace('from deformed coordinates, HEXA8 connectivity and the real nodal scalar array.',
                  'from deformed coordinates, extracted exterior TETRA4/TETRA10/HEXA8 faces and the real nodal scalar array.')
$vtk=$vtk.Replace('from deformed coordinates, native TETRA4/TETRA10/HEXA8 connectivity and the real nodal scalar array.',
                  'from deformed coordinates, extracted exterior TETRA4/TETRA10/HEXA8 faces and the real nodal scalar array.')

# Never allow a renderer exception raised from Form.Shown to escape into the WinForms/JIT dialog.
$legacyRender=@'
        private void RenderScene()
        {
            string field=(string)_field.SelectedItem;
            var scene=AsterMaxResultsScene.Build(_bundle,field,(double)_scale.Value);
            var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,scene);
            // A fresh native vtkControl is used for each field change, avoiding reliance on any
            // non-existent renderer-reset API while keeping the source-of-truth actor path native.
            if (_view != null)
            {
                _host.Controls.Remove(_view);
                _view.Dispose();
            }
            _view = new vtkControl.vtkControl { Dock=DockStyle.Fill };
            _host.Controls.Add(_view);
            // AddCells is PrePoMax's public native actor path: it constructs vtkMaxActor/mappers
            // from deformed coordinates, extracted exterior TETRA4/TETRA10/HEXA8 faces and the real nodal scalar array.
            _view.AddCells(data);
            _view.AdjustCameraDistanceAndClipping();
            _status.Text=scene.Describe();
        }
'@
$safeRender=@'
        private void RenderScene()
        {
            try
            {
                string field=(string)_field.SelectedItem;
                var scene=AsterMaxResultsScene.Build(_bundle,field,(double)_scale.Value);
                var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,scene);
                if (_view != null)
                {
                    _host.Controls.Remove(_view);
                    _view.Dispose();
                    _view=null;
                }
                _view = new vtkControl.vtkControl { Dock=DockStyle.Fill };
                _host.Controls.Add(_view);
                // vtkMaxActor's poly path receives only exterior 2D faces; real nodal FEA scalars remain unchanged.
                _view.AddCells(data);
                _view.AdjustCameraDistanceAndClipping();
                _status.Text=scene.Describe()+" • exterior surface rendered";
            }
            catch(Exception ex)
            {
                if(_view!=null)
                {
                    _host.Controls.Remove(_view);
                    _view.Dispose();
                    _view=null;
                }
                _status.Text="Render blocked: "+ex.GetType().Name;
                MessageBox.Show(this,"AsterMax results renderer blocked safely.\n\n"+ex.GetType().Name+": "+ex.Message,
                    "AsterMax Results",MessageBoxButtons.OK,MessageBoxIcon.Error);
            }
        }
'@
if($vtk.Contains($legacyRender)){
    $vtk=$vtk.Replace($legacyRender,$safeRender)
}
elseif(-not $vtk.Contains('exterior surface rendered')){
    # Older comment wording may differ; require a safe renderer before shipping.
    throw 'RenderScene safe exception boundary anchor missing.'
}

if($vtk.Contains('data.Geometry.Cells.Types = bundle.CellTypes.ToArray();')){
    throw 'Raw volume VTK cells are still passed to vtkMaxActor poly renderer.'
}
if($vtk.Contains('Enumerable.Repeat(VtkHexahedron, bundle.ElementCount)')){
    throw 'Hard-coded HEXA8 VTK rendering remains.'
}
foreach($required in @('BuildExteriorSurface','VtkQuadraticTriangle','SurfaceMesh surface=BuildExteriorSurface(bundle)','exterior surface rendered')){
    if(-not $vtk.Contains($required)){ throw "TETRA result surface renderer token missing: $required" }
}
Set-Content $vtkPath $vtk -Encoding UTF8

Write-Host 'C10.10.1 hotfix: TETRA4/TETRA10/HEXA8 result volumes are converted to exterior VTK faces before vtkMaxActor poly rendering.' -ForegroundColor Green

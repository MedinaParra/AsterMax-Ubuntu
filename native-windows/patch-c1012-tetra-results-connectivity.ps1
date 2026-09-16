param([string]$Root)
$ErrorActionPreference='Stop'

# C10.10.1 hotfix — results bundles produced by the production MED bridge can contain
# TETRA4 (4 nodes), TETRA10 (10 nodes), HEXA8 (8 nodes), or supported mixed meshes.
# The historical C9.67 UI reader hard-coded connectivity width 8 and VTK_HEXAHEDRON,
# causing a valid TETRA4 solve to fail with "Unexpected connectivity width.".

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
        public const int VtkTetra = 10;
        public const int VtkHexahedron = 12;
        public const int VtkQuadraticTetra = 24;
'@
if($vtk.Contains($legacyConst)){
    $vtk=$vtk.Replace($legacyConst,$newConst.TrimEnd())
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

$legacyTypes='            data.Geometry.Cells.Types = Enumerable.Repeat(VtkHexahedron, bundle.ElementCount).ToArray();'
$newTypes='            data.Geometry.Cells.Types = bundle.CellTypes.ToArray();'
if($vtk.Contains($legacyTypes)){
    $vtk=$vtk.Replace($legacyTypes,$newTypes)
}
elseif(-not $vtk.Contains($newTypes)){
    throw 'VTK cell-type assignment anchor missing.'
}

$vtk=$vtk.Replace('from deformed coordinates, HEXA8 connectivity and the real nodal scalar array.',
                  'from deformed coordinates, native TETRA4/TETRA10/HEXA8 connectivity and the real nodal scalar array.')

if($vtk.Contains('Enumerable.Repeat(VtkHexahedron, bundle.ElementCount)')){
    throw 'Hard-coded HEXA8 VTK rendering remains.'
}
Set-Content $vtkPath $vtk -Encoding UTF8

Write-Host 'C10.10.1 hotfix: dynamic TETRA4/TETRA10/HEXA8 result connectivity + VTK cell types enabled.' -ForegroundColor Green

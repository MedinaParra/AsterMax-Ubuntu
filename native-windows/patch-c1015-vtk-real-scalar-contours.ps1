param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $vtkPath)){throw 'C10.15 requires AsterMaxVtkResultsBinding.cs.'}
$s=Get-Content $vtkPath -Raw

# PrePoMax/vtkControl only enables scalar contour formatting for actors that carry
# valid MinNode/MaxNode metadata. AsterMax was providing the nodal scalar array but
# not Geometry.ExtremeNodes, so UpdateScalarFormatting skipped the actor and left
# the surface at its uniform base color.
$anchor='            data.Geometry.Nodes.Values = scene.Scalars.Select(x => (float)x).ToArray();'
$replacement=@'
            data.Geometry.Nodes.Values = scene.Scalars.Select(x => (float)x).ToArray();

            // Required by vtkControl.UpdateScalarFormatting(): actors without MinNode/MaxNode
            // are treated as if no scalar field exists, even when PointData scalars are present.
            int minScalarIndex=0, maxScalarIndex=0;
            for(int si=1;si<scene.Scalars.Length;si++)
            {
                if(scene.Scalars[si] < scene.Scalars[minScalarIndex]) minScalarIndex=si;
                if(scene.Scalars[si] > scene.Scalars[maxScalarIndex]) maxScalarIndex=si;
            }
            data.Geometry.ExtremeNodes.Ids = new[]{minScalarIndex+1,maxScalarIndex+1};
            data.Geometry.ExtremeNodes.Coor = new[]{
                new[]{scene.DeformedCoordinates[minScalarIndex][0],scene.DeformedCoordinates[minScalarIndex][1],scene.DeformedCoordinates[minScalarIndex][2]},
                new[]{scene.DeformedCoordinates[maxScalarIndex][0],scene.DeformedCoordinates[maxScalarIndex][1],scene.DeformedCoordinates[maxScalarIndex][2]}
            };
            data.Geometry.ExtremeNodes.Values = new[]{(float)scene.Scalars[minScalarIndex],(float)scene.Scalars[maxScalarIndex]};
'@
if($s.Contains($anchor) -and -not $s.Contains('minScalarIndex=0')){$s=$s.Replace($anchor,$replacement.TrimEnd())}
elseif(-not $s.Contains('minScalarIndex=0')){throw 'C10.15 nodal scalar anchor missing.'}

# Make the render status explicitly distinguish a bound contour actor from merely a visible legend.
$statusOld='                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • contours "+(_showContours.Checked?"ON":"OFF")+" • edges "+(_showEdges.Checked?"ON":"OFF")+" • deformed "+(_showDeformed.Checked?"ON":"OFF");'
$statusNew='                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • scalar contours "+(_showContours.Checked?"BOUND":"OFF")+" • edges "+(_showEdges.Checked?"ON":"OFF")+" • deformed "+(_showDeformed.Checked?"ON":"OFF");'
if($s.Contains($statusOld)){$s=$s.Replace($statusOld,$statusNew)}

foreach($token in @('data.Geometry.ExtremeNodes.Ids','data.Geometry.ExtremeNodes.Coor','data.Geometry.ExtremeNodes.Values','minScalarIndex=0','maxScalarIndex=0','UpdateScalarsAndCameraAndRedraw')){
    if(-not $s.Contains($token)){throw "C10.15 scalar-contour token missing: $token"}
}
Set-Content $vtkPath $s -Encoding UTF8
Write-Host 'C10.15 real nodal scalar contours: vtk actor extreme-node metadata bound.' -ForegroundColor Green

param(
  [Parameter(Mandatory=$true)][string]$ModelPath,
  [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
$culture = [System.Globalization.CultureInfo]::InvariantCulture
function F([double]$v){ $v.ToString('0.###############',$culture) }
$model = Get-Content $ModelPath -Raw | ConvertFrom-Json
if($model.schema -ne 'astermax-model-contract/v0'){ throw "Unsupported schema: $($model.schema)" }
if($model.unit_system -ne 'MM_N_S_MPA'){ throw "C9.59 adapter requires MM_N_S_MPA; got $($model.unit_system)" }
if($model.analysis.type -ne 'static_structural'){ throw "Only static_structural is supported in adapter v0" }
if($model.mesh.element_type -ne 'HEXA8'){ throw "Adapter v0 supports HEXA8 benchmark only" }
if($model.materials.Count -ne 1){ throw 'Adapter v0 requires exactly one isotropic material.' }
if($model.supports.Count -ne 1){ throw 'Adapter v0 requires exactly one support.' }
if($model.loads.Count -ne 1){ throw 'Adapter v0 requires exactly one load.' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$base = [IO.Path]::GetFileNameWithoutExtension([IO.Path]::GetFileNameWithoutExtension($ModelPath))
$mailPath = Join-Path $OutDir "$base.mail"
$commPath = Join-Path $OutDir "$base.comm"

$nodes = @($model.mesh.nodes | Sort-Object id)
$elements = @($model.mesh.elements | Sort-Object id)
$groups = $model.mesh.node_groups
$mail = New-Object System.Collections.Generic.List[string]
$mail.Add('TITRE')
$mail.Add("ASTERMAX C9.59 GENERATED - $($model.name)")
$mail.Add('FINSF')
$mail.Add('COOR_3D')
foreach($n in $nodes){ $mail.Add("$($n.id)  $(F $n.x)  $(F $n.y)  $(F $n.z)") }
$mail.Add('FINSF')
$mail.Add($model.mesh.element_type)
foreach($e in $elements){ $mail.Add("$($e.id) " + (($e.nodes) -join ' ')) }
$mail.Add('FINSF')
foreach($p in $groups.PSObject.Properties | Sort-Object Name){
  $mail.Add('GROUP_NO'); $mail.Add($p.Name + ' ' + (@($p.Value) -join ' ')); $mail.Add('FINSF')
}
$mail.Add('FIN')
[IO.File]::WriteAllLines($mailPath,$mail,[Text.UTF8Encoding]::new($false))

$mat = $model.materials[0]
$sup = $model.supports[0]
$load = $model.loads[0]
$loadNodes = @($groups.PSObject.Properties[$load.group].Value)
if($loadNodes.Count -lt 1){ throw "Load group $($load.group) is empty or missing." }
$fx = [double]$load.fx_total_n / $loadNodes.Count
$fy = [double]$load.fy_total_n / $loadNodes.Count
$fz = [double]$load.fz_total_n / $loadNodes.Count
$comm = @"
DEBUT()

mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)

model = AFFE_MODELE(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'),
)

steel = DEFI_MATERIAU(
    ELAS=_F(E=$(F $mat.young_modulus_mpa), NU=$(F $mat.poisson)),
)

matfield = AFFE_MATERIAU(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', MATER=steel),
)

fixed = AFFE_CHAR_MECA(
    MODELE=model,
    DDL_IMPO=_F(GROUP_NO='$($sup.group)', DX=$(F $sup.dx), DY=$(F $sup.dy), DZ=$(F $sup.dz)),
)

load = AFFE_CHAR_MECA(
    MODELE=model,
    FORCE_NODALE=_F(GROUP_NO='$($load.group)', FX=$(F $fx), FY=$(F $fy), FZ=$(F $fz)),
)

result = MECA_STATIQUE(
    MODELE=model,
    CHAM_MATER=matfield,
    EXCIT=(
        _F(CHARGE=fixed),
        _F(CHARGE=load),
    ),
)

result = CALC_CHAMP(
    reuse=result,
    RESULTAT=result,
    CONTRAINTE=('SIGM_ELNO',),
    CRITERES=('SIEQ_ELNO',),
)

probe = POST_RELEVE_T(
    ACTION=_F(
        OPERATION='EXTRACTION',
        INTITULE='LOAD_FACE_DISPLACEMENT',
        RESULTAT=result,
        NOM_CHAM='DEPL',
        GROUP_NO='$($model.postprocess.displacement_probe_group)',
        NOM_CMP=('DX','DY','DZ'),
        TOUT_ORDRE='OUI',
    ),
)

IMPR_TABLE(TABLE=probe, UNITE=80)
IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result))

FIN()
"@
[IO.File]::WriteAllText($commPath,$comm.TrimStart(),[Text.UTF8Encoding]::new($false))
$manifest = [ordered]@{
  adapter='AsterMax-CodeAster-v0'
  source_model=(Resolve-Path $ModelPath).Path
  unit_system=$model.unit_system
  nodes=$nodes.Count
  elements=$elements.Count
  element_type=$model.mesh.element_type
  total_load_n=[math]::Sqrt([math]::Pow([double]$load.fx_total_n,2)+[math]::Pow([double]$load.fy_total_n,2)+[math]::Pow([double]$load.fz_total_n,2))
  load_nodes=$loadNodes.Count
  generated_mail=[IO.Path]::GetFileName($mailPath)
  generated_comm=[IO.Path]::GetFileName($commPath)
  solver_execution='NOT_RUN'
  result_claim='NONE'
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir "$base.adapter.json") -Encoding UTF8
Write-Host "Generated $mailPath"
Write-Host "Generated $commPath"

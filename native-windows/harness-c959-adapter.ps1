param([string]$Root='.')
$ErrorActionPreference='Stop'
$repo=(Resolve-Path $Root).Path
$model=Join-Path $repo 'native-windows/c959-adapter/axial-bar.model.json'
$adapter=Join-Path $repo 'native-windows/Export-AsterMaxCodeAster.ps1'
$out=Join-Path $repo 'c959-out'
Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
& $adapter -ModelPath $model -OutDir $out
$mail=Join-Path $out 'axial-bar.mail'
$comm=Join-Path $out 'axial-bar.comm'
$manifest=Join-Path $out 'axial-bar.adapter.json'
if(!(Test-Path $mail) -or !(Test-Path $comm) -or !(Test-Path $manifest)){ throw 'Adapter did not emit all expected files.' }
$m=Get-Content $model -Raw | ConvertFrom-Json
$ma=Get-Content $manifest -Raw | ConvertFrom-Json
$mailText=Get-Content $mail -Raw
$commText=Get-Content $comm -Raw
$checks=@()
function Gate([string]$name,[bool]$pass,[string]$evidence){ $script:checks += [pscustomobject]@{name=$name;pass=$pass;evidence=$evidence} }
Gate 'contract_schema' ($m.schema -eq 'astermax-model-contract/v0') $m.schema
Gate 'units_mm_n_mpa' ($m.unit_system -eq 'MM_N_S_MPA') $m.unit_system
Gate 'mesh_hex8' (($m.mesh.element_type -eq 'HEXA8') -and ($m.mesh.nodes.Count -eq 8) -and ($m.mesh.elements.Count -eq 1)) 'HEXA8 / 8 nodes / 1 element'
Gate 'mail_has_groups' (($mailText -match 'FIXED N1 N4 N5 N8') -and ($mailText -match 'LOAD N2 N3 N6 N7')) 'FIXED + LOAD node groups'
Gate 'material_preserved' (($commText -match 'E=210000') -and ($commText -match 'NU=0.3')) 'E=210000 MPa; nu=0.30'
Gate 'support_preserved' ($commText -match "GROUP_NO='FIXED'.*DX=0.*DY=0.*DZ=0") 'fixed XYZ'
Gate 'total_force_distributed' (($commText -match "GROUP_NO='LOAD'.*FX=2500") -and ($ma.total_load_n -eq 10000) -and ($ma.load_nodes -eq 4)) '10000 N / 4 = 2500 N per node'
Gate 'static_solver_deck' (($commText -match 'MECA_STATIQUE') -and ($commText -match 'CALC_CHAMP')) 'MECA_STATIQUE + CALC_CHAMP'
Gate 'postprocess_contract' (($commText -match "NOM_CHAM='DEPL'") -and ($commText -match "SIEQ_ELNO") -and ($commText -match "FORMAT='MED'")) 'DEPL + von Mises + MED'
Gate 'no_simulated_result_claim' (($ma.solver_execution -eq 'NOT_RUN') -and ($ma.result_claim -eq 'NONE')) 'solver not run; no result claim'

$L=[double]$m.geometry.dimensions_mm[0]
$A=[double]$m.geometry.dimensions_mm[1]*[double]$m.geometry.dimensions_mm[2]
$F=[double]$m.loads[0].fx_total_n
$E=[double]$m.materials[0].young_modulus_mpa
$sigma=$F/$A
$disp=$F*$L/($A*$E)
$stressErr=[math]::Abs($sigma-[double]$m.reference.axial_stress_mpa)
$dispErr=[math]::Abs($disp-[double]$m.reference.axial_displacement_mm)
Gate 'analytical_reference_recomputed' (($stressErr -lt 1e-10) -and ($dispErr -lt 1e-12)) ("sigma={0}; ux={1}" -f $sigma,$disp)

# C9.58 parity gates: the generated adapter deck must preserve the validated benchmark semantics.
$c958Mail=Get-Content (Join-Path $repo 'native-windows/c958-benchmark/axial-bar.mail') -Raw
$c958Comm=Get-Content (Join-Path $repo 'native-windows/c958-benchmark/axial-bar.comm') -Raw
$semanticTokens=@('HEXA8','FIXED','LOAD','E=210000','NU=0.30','MECA_STATIQUE','SIGM_ELNO','SIEQ_ELNO','POST_RELEVE_T',"FORMAT='MED'")
$parity=$true
foreach($token in $semanticTokens){ if(($c958Mail+$c958Comm) -notmatch [regex]::Escape($token) -or ($mailText+$commText) -notmatch [regex]::Escape($token)){ $parity=$false } }
Gate 'c958_semantic_parity' $parity ($semanticTokens -join ', ')

$checks | Format-Table -AutoSize | Out-String | Write-Host
$pass=($checks | Where-Object{-not $_.pass}).Count -eq 0
$evidence=[ordered]@{
  release='C9.59'
  title='AsterMax Model Contract to Code_Aster Adapter v0'
  all_checks_pass=$pass
  checks_total=$checks.Count
  checks_passed=($checks|Where-Object pass).Count
  solver_execution='NOT_RUN'
  fea_result_generated=$false
  analytical_reference=[ordered]@{stress_mpa=$sigma;displacement_mm=$disp;kind='analytical_not_fea'}
  generated=[ordered]@{mail=(Get-FileHash $mail -Algorithm SHA256).Hash.ToLower();comm=(Get-FileHash $comm -Algorithm SHA256).Hash.ToLower()}
  checks=$checks
}
$evidence | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $out 'C9.59_VALIDATION.json') -Encoding UTF8
if(-not $pass){ throw 'C9.59 adapter harness failed.' }
Write-Host 'C9.59 adapter harness PASS.' -ForegroundColor Green

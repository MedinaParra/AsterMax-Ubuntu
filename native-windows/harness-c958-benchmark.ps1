param([string]$Root, [string]$OutDir)
$ErrorActionPreference = 'Stop'

if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir = Join-Path $PSScriptRoot 'out-c958' }
New-Item -ItemType Directory -Force $OutDir | Out-Null

$fixture = Join-Path $PSScriptRoot 'c958-benchmark'
$mail = Join-Path $fixture 'axial-bar.mail'
$comm = Join-Path $fixture 'axial-bar.comm'
if(!(Test-Path $mail)){ throw 'C9.58 ASTER mesh fixture missing' }
if(!(Test-Path $comm)){ throw 'C9.58 Code_Aster command deck missing' }

$mailText = Get-Content $mail -Raw
$commText = Get-Content $comm -Raw

function Gate([string]$name,[bool]$pass,[string]$evidence,[string]$kind='benchmark'){
  [pscustomobject]@{ name=$name; pass=$pass; kind=$kind; evidence=$evidence }
}

# Engineering contract: mm, N, MPa. These are analytical reference values only.
$L = 100.0
$W = 10.0
$H = 10.0
$E = 210000.0
$nu = 0.30
$Ftotal = 10000.0
$loadedNodes = 4
$forcePerNode = $Ftotal / $loadedNodes
$A = $W * $H
$sigma = $Ftotal / $A
$epsilon = $sigma / $E
$u = $Ftotal * $L / ($A * $E)

$checks = @()
$checks += Gate 'units_contract' (($L -eq 100.0) -and ($E -eq 210000.0)) 'benchmark is defined in mm, N, MPa'
$checks += Gate 'mesh_hexa8_present' ($mailText -match '(?m)^HEXA8\s*$') 'single HEXA8 structural fixture declared'
$checks += Gate 'mesh_has_8_nodes' (([regex]::Matches($mailText,'(?m)^N[1-8]\s+')).Count -eq 8) 'eight deterministic corner nodes found'
$checks += Gate 'fixed_group_present' ($mailText -match 'FIXED\s+N1\s+N4\s+N5\s+N8') 'x=0 face node group exists'
$checks += Gate 'load_group_present' ($mailText -match 'LOAD\s+N2\s+N3\s+N6\s+N7') 'x=100 face node group exists'
$checks += Gate 'linear_elastic_material' (($commText -match 'E=210000\.0') -and ($commText -match 'NU=0\.30')) 'steel-like isotropic elastic material is explicit'
$checks += Gate 'fixed_bc_xyz' (($commText -match "GROUP_NO='FIXED'") -and ($commText -match 'DX=0\.0') -and ($commText -match 'DY=0\.0') -and ($commText -match 'DZ=0\.0')) 'fixed face constrains all translations'
$checks += Gate 'load_total_10kn' (($commText -match "GROUP_NO='LOAD'") -and ($commText -match 'FX=2500\.0') -and (($forcePerNode*$loadedNodes) -eq $Ftotal)) '4 x 2500 N = 10000 N total axial load'
$checks += Gate 'static_solution_operator' ($commText -match 'MECA_STATIQUE') 'Code_Aster static mechanical solve operator present'
$checks += Gate 'stress_postprocess_operator' (($commText -match 'CALC_CHAMP') -and ($commText -match 'SIGM_ELNO') -and ($commText -match 'SIEQ_ELNO')) 'stress and equivalent-stress postprocess requested'
$checks += Gate 'displacement_probe' (($commText -match 'POST_RELEVE_T') -and ($commText -match 'LOAD_FACE_DISPLACEMENT')) 'load-face displacement extraction requested'
$checks += Gate 'med_result_export' ($commText -match "IMPR_RESU\(FORMAT='MED'") 'MED result export requested for professional visualization'
$checks += Gate 'analytical_sigma_100mpa' ([math]::Abs($sigma - 100.0) -lt 1e-12) 'F/A = 100 MPa analytical axial stress' 'analytical-reference'
$checks += Gate 'analytical_u_0_047619mm' ([math]::Abs($u - 0.0476190476190476) -lt 1e-12) 'FL/AE = 0.0476190476 mm analytical axial displacement' 'analytical-reference'
$checks += Gate 'no_solver_result_fabricated' (-not ($commText -match 'ASTERMAX_FAKE|SYNTHETIC_RESULT')) 'fixture contains no embedded simulation result values' 'integrity'

$failed = $checks | Where-Object { -not $_.pass }

$reference = [pscustomobject]@{
  basis='ANALYTICAL_1D_AXIAL_BAR_REFERENCE_NOT_FEA_OUTPUT'
  unit_system='mm-N-MPa'
  length_mm=$L
  width_mm=$W
  height_mm=$H
  area_mm2=$A
  elastic_modulus_mpa=$E
  poisson_ratio=$nu
  total_force_n=$Ftotal
  expected_axial_stress_mpa=$sigma
  expected_axial_strain=$epsilon
  expected_axial_displacement_mm=$u
  acceptance_note='Future Code_Aster runtime results must be compared to this reference with an explicitly declared tolerance; this harness does not claim a solver result.'
}

$gaps = @(
  [pscustomobject]@{ area='Code_Aster executable in CI'; state='NOT_PROVEN'; priority='P0'; note='Deck is generated and statically validated, but no Code_Aster binary is invoked in this harness.' },
  [pscustomobject]@{ area='AsterMax native model-to-deck adapter'; state='NOT_IMPLEMENTED'; priority='P0'; note='This deterministic deck is a contract fixture, not yet emitted from a live AsterMax model.' },
  [pscustomobject]@{ area='Mesh convergence'; state='NOT_IMPLEMENTED'; priority='P1'; note='One HEXA8 fixture proves pipeline semantics, not mesh convergence or production accuracy.' },
  [pscustomobject]@{ area='Result re-import and professional probes'; state='NOT_RUNTIME_PROVEN'; priority='P0'; note='MED export is requested, but AsterMax has not yet re-imported this benchmark result in CI.' }
)

$report = [pscustomobject]@{
  release='C9.58'
  title='Deterministic FEA Benchmark Contract'
  generated_utc=(Get-Date).ToUniversalTime().ToString('O')
  benchmark='100x10x10 mm axial bar; fixed x=0; +10 kN at x=100; E=210000 MPa; nu=0.30'
  checks_total=$checks.Count
  checks_passed=($checks | Where-Object pass).Count
  benchmark_contract_pass=($failed.Count -eq 0)
  solver_execution='NOT_RUN_BY_THIS_HARNESS'
  simulation_results='NONE_CLAIMED'
  checks=$checks
  analytical_reference=$reference
  gaps=$gaps
}

$reportPath = Join-Path $OutDir 'C9.58_BENCHMARK_CONTRACT.json'
$report | ConvertTo-Json -Depth 8 | Set-Content $reportPath -Encoding UTF8
$reference | Export-Csv (Join-Path $OutDir 'C9.58_ANALYTICAL_REFERENCE.csv') -NoTypeInformation -Encoding UTF8
Copy-Item $mail (Join-Path $OutDir 'axial-bar.mail') -Force
Copy-Item $comm (Join-Path $OutDir 'axial-bar.comm') -Force

$checks | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "C9.58 benchmark report: $reportPath"
if($failed.Count -gt 0){ throw ('C9.58 benchmark contract failed: ' + (($failed | ForEach-Object name) -join ', ')) }

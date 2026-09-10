Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Export-AsterMaxFeModelContract {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)] [object] $Model,
        [Parameter(Mandatory=$true)] [string] $OutPath
    )

    if ($null -eq $Model.UnitSystem) { throw 'C9.88: FeModel unit system is missing.' }
    if ($Model.UnitSystem.LengthUnitAbbreviation -ne 'mm' -or
        $Model.UnitSystem.ForceUnitAbbreviation -ne 'N' -or
        $Model.UnitSystem.PressureUnitAbbreviation -ne 'MPa') {
        throw "C9.88: production serializer requires mm / N / MPa; got $($Model.UnitSystem.LengthUnitAbbreviation) / $($Model.UnitSystem.ForceUnitAbbreviation) / $($Model.UnitSystem.PressureUnitAbbreviation)."
    }
    if ($null -eq $Model.Mesh -or $Model.Mesh.Nodes.Count -eq 0 -or $Model.Mesh.Elements.Count -eq 0) {
        throw 'C9.88: FeModel must contain a non-empty mesh.'
    }

    $nodes = @()
    foreach ($kv in ($Model.Mesh.Nodes.GetEnumerator() | Sort-Object Key)) {
        $nodes += [ordered]@{ id=[int]$kv.Key; x=[double]$kv.Value.X; y=[double]$kv.Value.Y; z=[double]$kv.Value.Z }
    }

    $elements = @()
    foreach ($kv in ($Model.Mesh.Elements.GetEnumerator() | Sort-Object Key)) {
        if ($kv.Value.GetType().Name -ne 'LinearHexaElement') {
            throw "C9.88: v1 production serializer supports LinearHexaElement/HEXA8 only; got $($kv.Value.GetType().Name)."
        }
        $elements += [ordered]@{ id=[int]$kv.Key; nodes=@($kv.Value.NodeIds | ForEach-Object { [int]$_ }) }
    }

    $nodeGroups = [ordered]@{}
    foreach ($kv in ($Model.Mesh.NodeSets.GetEnumerator() | Sort-Object Key)) {
        $nodeGroups[[string]$kv.Key] = @($kv.Value.Labels | ForEach-Object { [int]$_ })
    }

    $materials = @()
    foreach ($kv in ($Model.Materials.GetEnumerator() | Sort-Object Key)) {
        $elastic = $null
        $density = $null
        foreach ($p in $kv.Value.Properties) {
            if ($p.GetType().Name -eq 'Elastic') { $elastic = $p }
            elseif ($p.GetType().Name -eq 'Density') { $density = $p }
        }
        if ($null -eq $elastic -or $null -eq $elastic.YoungsPoissonsTemp -or $elastic.YoungsPoissonsTemp.Length -lt 1) {
            throw "C9.88: material '$($kv.Key)' has no supported Elastic property."
        }
        $row = $elastic.YoungsPoissonsTemp[0]
        $m = [ordered]@{ name=[string]$kv.Key; young_modulus_mpa=[double]$row[0]; poisson=[double]$row[1] }
        if ($null -ne $density -and $density.DensityTemp.Length -gt 0) { $m.density = [double]$density.DensityTemp[0][0] }
        $materials += $m
    }
    if ($materials.Count -ne 1) { throw "C9.88: v1 production exporter gate requires exactly one material; got $($materials.Count)." }

    $steps = @($Model.StepCollection.StepsList)
    if ($steps.Count -ne 1 -or $steps[0].GetType().Name -ne 'StaticStep') {
        throw 'C9.88: v1 requires exactly one StaticStep.'
    }
    $step = $steps[0]

    $supports = @()
    foreach ($kv in ($step.BoundaryConditions.GetEnumerator() | Sort-Object Key)) {
        $bc = $kv.Value
        if ($bc.GetType().Name -ne 'FixedBC' -or [string]$bc.RegionType -ne 'NodeSetName') {
            throw "C9.88: only FixedBC on NodeSetName is supported in v1; got $($bc.GetType().Name)/$($bc.RegionType)."
        }
        if (-not $nodeGroups.Contains($bc.RegionName)) { throw "C9.88: BC group '$($bc.RegionName)' does not exist." }
        $supports += [ordered]@{ name=[string]$kv.Key; group=[string]$bc.RegionName; dx=0.0; dy=0.0; dz=0.0 }
    }
    if ($supports.Count -ne 1) { throw "C9.88: v1 requires exactly one fixed support; got $($supports.Count)." }

    $loads = @()
    foreach ($kv in ($step.Loads.GetEnumerator() | Sort-Object Key)) {
        $load = $kv.Value
        if ($load.GetType().Name -ne 'CLoad' -or [string]$load.RegionType -ne 'NodeSetName') {
            throw "C9.88: only CLoad on NodeSetName is supported in v1; got $($load.GetType().Name)/$($load.RegionType)."
        }
        if (-not $nodeGroups.Contains($load.RegionName)) { throw "C9.88: load group '$($load.RegionName)' does not exist." }
        # AsterMax v1 contract treats F1/F2/F3 as the requested total resultant for the selected node set.
        # The Code_Aster exporter distributes this total uniformly and independently verifies conservation.
        $loads += [ordered]@{ name=[string]$kv.Key; group=[string]$load.RegionName; fx_total_n=[double]$load.F1; fy_total_n=[double]$load.F2; fz_total_n=[double]$load.F3 }
    }
    if ($loads.Count -ne 1) { throw "C9.88: v1 requires exactly one nodal force load; got $($loads.Count)." }

    $contract = [ordered]@{
        schema='astermax-model-contract/v0'
        name=[string]$Model.Name
        unit_system='MM_N_S_MPA'
        source=[ordered]@{ kind='compiled_native_femodel'; serializer='C9.88'; cad_length_unit='mm' }
        analysis=[ordered]@{ type='static_structural' }
        mesh=[ordered]@{ element_type='HEXA8'; nodes=$nodes; elements=$elements; node_groups=$nodeGroups }
        materials=$materials
        supports=$supports
        loads=$loads
        postprocess=[ordered]@{ displacement_probe_group=[string]$loads[0].group }
        truth_boundary=[ordered]@{
            solver_execution='NOT_RUN'
            result_claim='NONE'
            supported_scope='single-material HEXA8 linear static; one FixedBC; one CLoad; node-set regions; mm/N/MPa'
        }
    }

    $dir = Split-Path -Parent $OutPath
    if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $contract | ConvertTo-Json -Depth 14 | Set-Content $OutPath -Encoding UTF8
    return $contract
}

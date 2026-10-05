param([string]$Root)
$ErrorActionPreference='Stop'

# C10.22 — make scope membership part of the frozen FeModel identity.
$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C10.22 results workspace missing.'}
$s=[regex]::Replace((Get-Content $workspace -Raw),"\r\n?","`n")
$anchor='            f.MaterialCount = model.Materials == null ? 0 : model.Materials.Count;'
$scopeCode=@'
            // C10.22: mesh-group and surface membership are part of result identity.
            // A BC/load that keeps the same group name but changes membership must stale old results.
            if (model.Mesh.NodeSets != null)
            {
                lines.Add("mesh.nodesets=" + model.Mesh.NodeSets.Count.ToString(CultureInfo.InvariantCulture));
                foreach (var kv in model.Mesh.NodeSets.OrderBy(x => x.Key, StringComparer.Ordinal))
                {
                    int[] labels = kv.Value == null || kv.Value.Labels == null ? new int[0] : kv.Value.Labels.OrderBy(x => x).ToArray();
                    lines.Add("nodeset|" + Escape(kv.Key) + "|" +
                        String.Join(",", labels.Select(x => x.ToString(CultureInfo.InvariantCulture))));
                }
            }
            if (model.Mesh.ElementSets != null)
            {
                lines.Add("mesh.elementsets=" + model.Mesh.ElementSets.Count.ToString(CultureInfo.InvariantCulture));
                foreach (var kv in model.Mesh.ElementSets.OrderBy(x => x.Key, StringComparer.Ordinal))
                {
                    int[] labels = kv.Value == null || kv.Value.Labels == null ? new int[0] : kv.Value.Labels.OrderBy(x => x).ToArray();
                    lines.Add("elementset|" + Escape(kv.Key) + "|" +
                        String.Join(",", labels.Select(x => x.ToString(CultureInfo.InvariantCulture))));
                }
            }
            if (model.Mesh.Surfaces != null)
            {
                lines.Add("mesh.surfaces=" + model.Mesh.Surfaces.Count.ToString(CultureInfo.InvariantCulture));
                foreach (var kv in model.Mesh.Surfaces.OrderBy(x => x.Key, StringComparer.Ordinal))
                {
                    var surface = kv.Value;
                    if (surface == null) { lines.Add("surface|" + Escape(kv.Key) + "|<null>"); continue; }
                    lines.Add(String.Format(CultureInfo.InvariantCulture,
                        "surface|{0}|type={1}|created={2}|area={3:R}|nodeset={4}|source_nodeset={5}",
                        Escape(kv.Key), surface.Type, surface.CreatedFrom, surface.Area,
                        Escape(surface.NodeSetName), Escape(surface.CreatedFromNodeSetName)));
                    if (surface.FaceIds != null)
                        lines.Add("surface.faces|" + Escape(kv.Key) + "|" +
                            String.Join(",", surface.FaceIds.OrderBy(x => x).Select(x => x.ToString(CultureInfo.InvariantCulture))));
                    if (surface.ElementFaces != null)
                    {
                        foreach (var ef in surface.ElementFaces.OrderBy(x => x.Key.ToString(), StringComparer.Ordinal))
                            lines.Add("surface.elementface|" + Escape(kv.Key) + "|" + ef.Key + "|" + Escape(ef.Value));
                    }
                }
            }

'@
$scopeCode=[regex]::Replace($scopeCode,"\r\n?","`n")
if(-not $s.Contains('mesh.nodesets=')){
    if(-not $s.Contains($anchor)){throw 'C10.22 model fingerprint material anchor missing.'}
    $s=$s.Replace($anchor,$scopeCode+$anchor)
}
Set-Content $workspace $s -Encoding UTF8

# Tell the qualification gate that native node/element/surface scopes are frozen by this fingerprint.
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporter)){throw 'C10.22 native exporter missing.'}
$e=[regex]::Replace((Get-Content $exporter -Raw),"\r\n?","`n")
$manifestAnchor='                ["load_nodes"]=loadNodes.Count,'
$manifestInsert=@'
                ["scope_binding"]=new JObject
                {
                    ["mode"]="model_fingerprint_mesh_scope",
                    ["verified"]=true,
                    ["support_group"]=(string)sup["group"],
                    ["load_group"]=loadGroup,
                    ["mesh_scope_membership_in_fingerprint"]=true
                },
                ["load_nodes"]=loadNodes.Count,
'@
$manifestInsert=[regex]::Replace($manifestInsert,"\r\n?","`n").TrimEnd()
if(-not $e.Contains('model_fingerprint_mesh_scope')){
    if(-not $e.Contains($manifestAnchor)){throw 'C10.22 exporter scope manifest anchor missing.'}
    $e=$e.Replace($manifestAnchor,$manifestInsert)
}
Set-Content $exporter $e -Encoding UTF8

Write-Host 'C10.22 scope membership fingerprint + native scope evidence applied.' -ForegroundColor Green

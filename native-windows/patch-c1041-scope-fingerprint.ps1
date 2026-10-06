param([string]$Root)
$ErrorActionPreference='Stop'

# C10.41 — make scope membership part of the frozen FeModel identity.
$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C10.41 results workspace missing.'}
$s=[regex]::Replace((Get-Content $workspace -Raw),"\r\n?","`n")
$anchor='            f.MaterialCount = model.Materials == null ? 0 : model.Materials.Count;'
$scopeCode=@'
            // C10.41: mesh-group and surface membership are part of result identity.
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
    if(-not $s.Contains($anchor)){throw 'C10.41 model fingerprint material anchor missing.'}
    $s=$s.Replace($anchor,$scopeCode+$anchor)
}

# Nested elastic/friction tables and region-to-material assignments affect the
# solution but were skipped by the legacy scalar-property reflector.
$extraAnchor='            f.Canonical = String.Join("\n", lines);'
$extra=@'
            lines.Add("mechanical_revision_schema=C10.41");
            if(model.Materials!=null)
                foreach(var kv in model.Materials.OrderBy(x=>x.Key,StringComparer.Ordinal))
                    lines.Add("material.properties|"+Escape(kv.Key)+"|"+
                        Newtonsoft.Json.JsonConvert.SerializeObject(kv.Value.Properties,Newtonsoft.Json.Formatting.None));
            if(model.Sections!=null)
                foreach(var kv in model.Sections.OrderBy(x=>x.Key,StringComparer.Ordinal))
                    AppendSimpleProperties(lines,"section."+Escape(kv.Key),kv.Value);
            if(model.ContactPairs!=null)
                foreach(var kv in model.ContactPairs.OrderBy(x=>x.Key,StringComparer.Ordinal))
                    AppendSimpleProperties(lines,"contact."+Escape(kv.Key),kv.Value);
            if(model.SurfaceInteractions!=null)
                foreach(var kv in model.SurfaceInteractions.OrderBy(x=>x.Key,StringComparer.Ordinal))
                    lines.Add("interaction.properties|"+Escape(kv.Key)+"|"+
                        Newtonsoft.Json.JsonConvert.SerializeObject(kv.Value.Properties,Newtonsoft.Json.Formatting.None));

'@
$extra=[regex]::Replace($extra,"\r\n?","`n")
if(-not $s.Contains('mechanical_revision_schema=C10.41')){
    if(-not $s.Contains($extraAnchor)){ throw 'C10.41 nested mechanics fingerprint anchor missing.' }
    $s=$s.Replace($extraAnchor,$extra+$extraAnchor)
}
Set-Content $workspace $s -Encoding UTF8


Write-Host "C10.41 scope membership fingerprint applied." -ForegroundColor Green

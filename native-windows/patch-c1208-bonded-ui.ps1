param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'

function Read-Source([string]$Relative) {
    return [regex]::Replace((Get-Content -LiteralPath (Join-Path $Root $Relative) -Raw),"\r\n?","`n")
}
function Write-Source([string]$Relative,[string]$Text) {
    [IO.File]::WriteAllText((Join-Path $Root $Relative),$Text,(New-Object Text.UTF8Encoding($false)))
}
function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $Old=$Old.Replace("`r",'')
    $New=$New.Replace("`r",'')
    if(-not $Text.Contains($Old)){ throw ('C12.08 UI anchor missing: '+$Old.Substring(0,[Math]::Min(120,$Old.Length))) }
    return $Text.Replace($Old,$New)
}

# Keep the native serializable Tie type, its selection editor and undo commands.
# The ribbon selects Tie explicitly; unrelated native constraints retain their UI.
$relative='PrePoMax/Forms/AsterMaxNativeUi.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_BONDED_RIBBON')) {
    $old=@'
            ribbon.TabPages.Add(BuildRibbonPage("Conexiones", new Control[] {
                CommandTile("Auto contactos", "CONEXIONES", AsterMaxAutoGenerateContacts, true),
                InfoCard("Detección automática por proximidad • rojo master • azul slave"),
                StateCard("Ámbito", "Geometría / selección")
            }));
'@
    $new=@'
            // C1208_BONDED_RIBBON
            ribbon.TabPages.Add(BuildRibbonPage("Conexiones", new Control[] {
                CommandTile("Unión bonded", "SOLDADURA", () => {
                    _frmConstraint.PreselectListViewItem(3);
                    tsmiCreateConstraint_Click(null, EventArgs.Empty);
                }, true),
                CommandTile("Editar unión", "CONEXIONES", () => tsmiEditConstraint_Click(null, EventArgs.Empty)),
                CommandTile("Auto contactos", "CONTACTO", AsterMaxAutoGenerateContacts),
                InfoCard("Bonded: unión permanente de superficies. Defina la tolerancia de cada unión.")
            }));
'@
    $s=Replace-Required $s $old $new
    # Automatic contact detection also runs after meshing. Never add a second,
    # incompatible contact law on top of already defined welded interfaces.
    $old='            if (_controller.GetContactPairNames().Length > 0) return;'
    $new=@'
            if (_controller.GetContactPairNames().Length > 0) return;
            // C1208_PRESERVE_BONDED_CONNECTIONS
            foreach (var constraint in _controller.Model.Constraints.Values)
                if (constraint.Active && constraint is CaeModel.Tie)
                {
                    tsslState.Text="El modelo contiene uniones bonded. Revise sus superficies desde Conexiones / Editar unión.";
                    return;
                }
'@
    $s=Replace-Required $s $old $new
    Write-Source $relative $s
}

$relative='PrePoMax/Forms/33_Constraint/FrmConstraint.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_BONDED_DEFAULTS')) {
    $s=Replace-Required $s 'lvTypes.FindItemWithText("Tie")' 'lvTypes.FindItemWithText("Unión soldada (bonded)")'
    $s=Replace-Required $s 'item = new ListViewItem("Tie");' 'item = new ListViewItem("Unión soldada (bonded)");'
    $old='            Tie tie = new Tie(GetConstraintName("Tie"), "", RegionTypeEnum.Selection, "", RegionTypeEnum.Selection, twoD);'
    $new=@'
            // C1208_BONDED_DEFAULTS: preserve the mesh; tolerance is explicit and editable.
            Tie tie = new Tie(GetConstraintName("Bonded"), 0.05, false,
                              "", RegionTypeEnum.Selection, "", RegionTypeEnum.Selection, twoD);
'@
    $s=Replace-Required $s $old $new
    $old='                // Check for errors with constructor'
    $new=@'
                if (Double.IsNaN(tie.PositionTolerance) || Double.IsInfinity(tie.PositionTolerance) || tie.PositionTolerance <= 0)
                    throw new CaeException("La unión bonded requiere una tolerancia de posición positiva y explícita.");
                if (tie.Adjust)
                    throw new CaeException("En Code_Aster, establezca Ajustar geometría = No. La unión bonded conserva la malla y acopla las superficies dentro de la tolerancia indicada.");
                // Check for errors with constructor
'@
    $s=Replace-Required $s $old $new
    Write-Source $relative $s
}

$relative='PrePoMax/Forms/33_Constraint/ViewTie.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_BONDED_PROPERTIES')) {
    $old=@'
        [DescriptionAttribute("Enter the value of largest distance from the master surface for which the slave nodes will be " +
                              "included in the tie constraint. Default value equals 2.5 % of the typical element size.")]
'@
    $new=@'
        // C1208_BONDED_PROPERTIES
        [DescriptionAttribute("Distancia máxima entre las superficies para incluir nodos en la unión soldada (bonded). " +
                              "Introduzca un valor positivo explícito y revise las regiones seleccionadas. La malla no se mueve.")]
'@
    $s=Replace-Required $s $old $new
    $s=$s.Replace('"Position tolerance"','"Tolerancia de posición"')
    $s=$s.Replace('"Adjust"','"Ajustar geometría"')
    $s=$s.Replace('Set adjust to No to prevent the projection of the slave nodes on the master surface.',
        'Para el puente Code_Aster, use No. El acoplamiento bonded conserva las coordenadas y transmite desplazamientos a través de la separación.')
    Write-Source $relative $s
}

# Per-node CLoad is an existing model convention. Make it visible without
# changing any load value or dividing by the number of selected nodes.
$relative='PrePoMax/Forms/45_Load/ViewCLoad.cs'
$s=Read-Source $relative
if(-not $s.Contains('"F2 por nodo"')) {
    $s=$s.Replace('"F1"','"F1 por nodo"').Replace('"F2"','"F2 por nodo"').Replace('"F3"','"F3 por nodo"')
    $s=$s.Replace('"Force components"','"Fuerza por nodo"').Replace('"Force magnitude"','"Magnitud por nodo"')
    $s=$s.Replace('"Magnitude"','"Magnitud por nodo"')
    $s=$s.Replace('Value of the force component per node in the direction of the first axis.',
        'Componente X aplicada a cada nodo de la región. La resultante es este valor multiplicado por el número de nodos.')
    $s=$s.Replace('Value of the force component per node in the direction of the second axis.',
        'Componente Y aplicada a cada nodo de la región. La resultante es este valor multiplicado por el número de nodos.')
    $s=$s.Replace('Value of the force component per node in the direction of the third axis.',
        'Componente Z aplicada a cada nodo de la región. La resultante es este valor multiplicado por el número de nodos.')
    Write-Source $relative $s
}

# Changing a bonded law or its regions must invalidate a previous solution.
# Surface/element/node-set membership is already covered by C10.41.
$relative='PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_CONSTRAINT_FINGERPRINT')) {
    $old='            f.Canonical = String.Join("\n", lines);'
    $new=@'
            // C1208_CONSTRAINT_FINGERPRINT
            lines.Add("constraint_revision_schema=C12.08");
            lines.Add("constraints="+(model.Constraints==null?0:model.Constraints.Count).ToString(CultureInfo.InvariantCulture));
            if(model.Constraints!=null)
                foreach(var kv in model.Constraints.OrderBy(x=>x.Key,StringComparer.Ordinal))
                {
                    lines.Add("constraint|"+Escape(kv.Key)+"|"+(kv.Value==null?"<null>":kv.Value.GetType().FullName));
                    AppendSimpleProperties(lines,"constraint."+Escape(kv.Key),kv.Value);
                }
            f.Canonical = String.Join("\n", lines);
'@
    $s=Replace-Required $s $old $new
    Write-Source $relative $s
}

$relative='PrePoMax/Forms/AsterMaxWorkflowStates.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_CONNECTION_STATE')) {
    $old='            states["ax-connections"]=new AsterMaxSectionState(1,"Opcional para un sólido continuo; los contactos no están soportados por el puente actual.");'
    $new=@'
            // C1208_CONNECTION_STATE: configuration presence is not a solved load-path certification.
            int bondedCount=model.Constraints.Values.Count(x=>x.Active && x is Tie);
            int contactCount=model.ContactPairs.Values.Count(x=>x.Active);
            states["ax-connections"]=new AsterMaxSectionState(1,
                bondedCount+" uniones bonded y "+contactCount+" contactos activos. Revise superficies y tolerancias; la exportación comprueba el acoplamiento numérico.");
'@
    $s=Replace-Required $s $old $new
    # Existing native workflow audit exercises real FeModel/fingerprint classes.
    $old='            string output=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"AsterMax-Audit-"+Guid.NewGuid().ToString("N"));'
    $new=@'
            // C1208_BONDED_FINGERPRINT_AUDIT: no FEA values are synthesized.
            var bondedModel=CreateAsterMaxStatusFixture();
            string withoutTie=AsterMaxModelFingerprint.Extract(bondedModel).Sha256;
            var bondedTie=new Tie("Bonded-Audit",0.05,false,"Master",RegionTypeEnum.SurfaceName,
                                  "Slave",RegionTypeEnum.SurfaceName,false);
            bondedModel.Constraints.Add(bondedTie.Name,bondedTie);
            string beforeChange=AsterMaxModelFingerprint.Extract(bondedModel).Sha256;
            if(beforeChange==withoutTie) throw new InvalidOperationException("Adding a bonded union did not change result identity.");
            Action<string,Action> fingerprintCheck=(name,change)=>{
                change();
                string afterChange=AsterMaxModelFingerprint.Extract(bondedModel).Sha256;
                if(afterChange==beforeChange) throw new InvalidOperationException("Bonded change did not invalidate result identity: "+name);
                beforeChange=afterChange;
                evidence.Add(new JObject{["case"]="bonded_fingerprint_"+name,["pass"]=true});
            };
            fingerprintCheck("tolerance",()=>bondedTie.PositionTolerance=0.1);
            fingerprintCheck("adjust",()=>bondedTie.Adjust=true);
            fingerprintCheck("master_region",()=>bondedTie.MasterRegionName="OtherMaster");
            fingerprintCheck("slave_region",()=>bondedTie.SlaveRegionName="OtherSlave");
            fingerprintCheck("active",()=>bondedTie.Active=false);
            fingerprintCheck("remove",()=>bondedModel.Constraints.Remove(bondedTie.Name));
            string output=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"AsterMax-Audit-"+Guid.NewGuid().ToString("N"));
'@
    $s=Replace-Required $s $old $new
    Write-Source $relative $s
}

# Report the exported mechanics, not an independently recomputed GUI estimate.
$relative='PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_BONDED_AND_LOAD_INFO')) {
    $new=@'
        // C1208_BONDED_AND_LOAD_INFO
        public static string DescribeBondedAndLoads(string workspace)
        {
            try
            {
                string path=Path.Combine(workspace,"ASTERMAX_SOLVE_TRANSACTION.json");
                if(!File.Exists(path)) return "";
                JObject manifest=JObject.Parse(File.ReadAllText(path))["native_exporter_manifest"] as JObject;
                if(manifest==null) return "";
                var b=new StringBuilder();
                int pairs=(int?)manifest["bonded_pair_count"] ?? 0;
                JObject report=manifest["bonded_mpc_report"] as JObject;
                if(pairs>0 && report!=null)
                {
                    b.AppendLine("Uniones soldadas (bonded) exportadas: "+pairs+".");
                    b.AppendLine("Acoplamiento permanente de las superficies seleccionadas; coordenadas de la malla conservadas.");
                    b.AppendLine("Separación máxima incluida: "+BondedInfoNumber((double?)report["maximum_gap_mm"])+" mm.");
                    b.AppendLine("Ecuaciones independientes: "+((int?)report["retained_rows"] ?? 0)+
                        "; redundantes eliminadas: "+((int?)report["redundant_rows"] ?? 0)+".");
                    int unmatched=(int?)report["unmatched_slave_node_count"] ?? 0;
                    if(unmatched>0)
                        b.AppendLine("Nodos seleccionados fuera de la tolerancia y sin unión: "+unmatched+
                            ". Revise el informe .bonded-mpc.json antes de interpretar el resultado.");
                    b.AppendLine("Esta idealización no calcula la resistencia local de un cordón de soldadura.");
                    b.AppendLine();
                }
                if(manifest["load_nodes"]!=null && manifest["fx_total_n"]!=null)
                {
                    b.AppendLine("Fuerza nodal exportada: "+manifest["load_nodes"]+" nodos.");
                    b.AppendLine("Componentes por nodo [N]: Fx="+BondedInfoNumber((double?)manifest["fx_per_node_n"])+
                        "; Fy="+BondedInfoNumber((double?)manifest["fy_per_node_n"])+
                        "; Fz="+BondedInfoNumber((double?)manifest["fz_per_node_n"])+".");
                    b.AppendLine("Resultante de esa fuerza [N]: Fx="+BondedInfoNumber((double?)manifest["fx_total_n"])+
                        "; Fy="+BondedInfoNumber((double?)manifest["fy_total_n"])+
                        "; Fz="+BondedInfoNumber((double?)manifest["fz_total_n"])+".");
                    if((bool?)manifest["gravity_enabled"]==true)
                        b.AppendLine("La resultante anterior corresponde a la fuerza nodal; la gravedad se aplica adicionalmente.");
                }
                return b.ToString().Trim();
            }
            catch { return "El resumen de uniones y cargas exportadas no está disponible. Revise el manifiesto del cálculo."; }
        }

        private static string BondedInfoNumber(double? value)
        {
            return value.HasValue?value.Value.ToString("#,0.########",CultureInfo.GetCultureInfo("es-CL")):"n/d";
        }
        // C1208_BONDED_AND_LOAD_INFO_END

'@
    $s=Replace-Required $s '        // C1207_SOLVER_DIAGNOSTICS_BEGIN' ($new+'        // C1207_SOLVER_DIAGNOSTICS_BEGIN')
    Write-Source $relative $s
}

$relative='PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$s=Read-Source $relative
if(-not $s.Contains('// C1208_VISIBLE_BONDED_AND_LOADS')) {
    $old='                // C1207_VISIBLE_CONTACT_ORIENTATION'
    $new=@'
                // C1208_VISIBLE_BONDED_AND_LOADS
                string bondedAndLoads=AsterMaxNativeSolveTransaction.DescribeBondedAndLoads(_asterMaxSolveTransaction.Workspace);
                if(!String.IsNullOrWhiteSpace(bondedAndLoads)) text+="\r\n"+bondedAndLoads+"\r\n\r\n";
                // C1207_VISIBLE_CONTACT_ORIENTATION
'@
    $s=Replace-Required $s $old $new
    $s=$s.Replace('string text = "Solution Information\r\n\r\n";','string text = "Información de la solución\r\n\r\n";')
    Write-Source $relative $s
}

foreach($relative in @('PrePoMax/Globals.cs','PrePoMax/Forms/AsterMaxC1034Audit.cs')) {
    $s=Read-Source $relative
    Write-Source $relative ($s.Replace('AsterMax Mechanical C12.07','AsterMax Mechanical C12.08'))
}
Write-Host 'C12.08: native bonded editor, explicit force semantics, exported mechanics summary and constraint result identity applied.' -ForegroundColor Green

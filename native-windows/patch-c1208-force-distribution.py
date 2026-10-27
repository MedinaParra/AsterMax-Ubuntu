"""Apply after the pinned C12.08 chain. Stage every source edit before writing."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
root = Path(p.parse_args().root)
changes = {}

def read(rel):
    if rel not in changes:
        changes[rel] = (root / rel).read_text(encoding='utf-8-sig')
    return changes[rel]

def replace(rel, old, new):
    text = read(rel)
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError('C12.08 force anchor missing/ambiguous: ' + rel + ': ' + old[:90])
    changes[rel] = text.replace(old, new)

load = 'CaeModel/Steps/Loads/Load.cs'
replace(load, '        // Methods', '''        // C1208_FORCE_COPY: preserve every inherited serialized field.
        protected Load(Load source) : base(source)
        {
            _creationIds = source._creationIds == null ? null : (int[])source._creationIds.Clone();
            _creationData = source._creationData == null ? null : source._creationData.DeepClone();
            _twoD = source._twoD; _amplitudeName = source._amplitudeName;
            _complex = source._complex; _phaseDeg = source._phaseDeg; _color = source._color;
        }

        // Methods''')
cload = 'CaeModel/Steps/Loads/CLoad.cs'
replace(cload, '    [Serializable]\n    public class CLoad', '''    public enum NodalForceDistribution { PorNodo = 0, TotalUniformePorNodo = 1 }

    // A distinct serialized type prevents an older executable from silently
    // interpreting a newly saved total as a per-node CLoad. Existing CLoad
    // streams acquire no new serialized fields and keep their original meaning.
    [Serializable]
    public sealed class UniformTotalCLoad : CLoad
    {
        public UniformTotalCLoad(CLoad source) : base(source) { }
        public override NodalForceDistribution ForceDistribution { get { return NodalForceDistribution.TotalUniformePorNodo; } }
    }

    [Serializable]
    public class CLoad''')
replace(cload, '        // Methods', '''        public virtual NodalForceDistribution ForceDistribution { get { return NodalForceDistribution.PorNodo; } }
        protected CLoad(CLoad source) : base(source)
        {
            _regionName=source._regionName; _regionType=source._regionType; _nodeId=source._nodeId;
            _f1=source._f1; _f2=source._f2; _f3=source._f3;
        }
        public CLoad WithForceDistribution(NodalForceDistribution mode)
        {
            if(mode == NodalForceDistribution.PorNodo) return new CLoad(this);
            if(mode == NodalForceDistribution.TotalUniformePorNodo) return new UniformTotalCLoad(this);
            throw new ArgumentOutOfRangeException("mode");
        }

        // Methods''')
replace('CaeModel/Steps/StaticStep.cs', 'if (loadType == typeof(CLoad) ||',
        'if (loadType == typeof(CLoad) || loadType == typeof(UniformTotalCLoad) ||')
# Do not let an unrelated backend reinterpret the new total type as a CLoad.
replace('CaeModel/FileInOut/Output/Calculix/Keywords/Step/Load/CalCLoad.cs',
        '            _load = load;', '''            if(load is UniformTotalCLoad)
                throw new NotSupportedException("La fuerza total uniforme requiere el exportador nativo Code_Aster. No se convierte a CLoad por nodo.");
            _load = load;''')

view = 'PrePoMax/Forms/45_Load/ViewCLoad.cs'
replace(view, '        public override string Name', '''        [CategoryAttribute("Fuerza")]
        [DisplayName("Interpretación de las componentes")]
        [DescriptionAttribute("PorNodo: cada nodo recibe F1/F2/F3. TotalUniformePorNodo: F1/F2/F3 son la resultante total, repartida entre nodos únicos. Cambiar el modo conserva los números y cambia su interpretación; revise la resultante antes de resolver. Sólo estática Code_Aster; no es presión por área.")]
        [RefreshProperties(RefreshProperties.All)]
        public CaeModel.NodalForceDistribution ForceDistribution
        {
            get { return _cLoad.ForceDistribution; }
            set
            {
                _cLoad = _cLoad.WithForceDistribution(value);
                SetBase(_cLoad, new Dictionary<RegionTypeEnum,string> {
                    { RegionTypeEnum.Selection, nameof(SelectionHidden) },
                    { RegionTypeEnum.NodeSetName, nameof(NodeSetName) },
                    { RegionTypeEnum.ReferencePointName, nameof(ReferencePointName) }
                });
            }
        }

        public override string Name''')
for old, new in [('"Fuerza por nodo"','"Fuerza"'),('"F1 por nodo"','"F1 según modo"'),
                 ('"F2 por nodo"','"F2 según modo"'),('"F3 por nodo"','"F3 según modo"'),
                 ('"Magnitud por nodo"','"Magnitud según modo"'),
                 ('Value of the force load magnitude per node.','Magnitud de las componentes según la interpretación elegida.')]:
    changes[view] = read(view).replace(old,new)
for axis in 'XYZ':
    changes[view] = read(view).replace(f'Componente {axis} aplicada a cada nodo de la región. La resultante es este valor multiplicado por el número de nodos.',
        f'Componente {axis}: por nodo o total según el modo seleccionado. El resumen previo al cálculo muestra ambas cantidades.')

bridge = 'PrePoMax/AsterMaxModelContractBridge.cs'
replace(bridge, '''                        loads.Add(new JObject
                        {
                            ["name"] = cload.Name,
                            ["type"] = "nodal_force_per_node",
                            ["group"] = group,
                            ["fx_per_node_n"] = cload.F1,
                            ["fy_per_node_n"] = cload.F2,
                            ["fz_per_node_n"] = cload.F3
                        });''', '''                        bool total = cload is UniformTotalCLoad;
                        var force = new JObject {
                            ["name"] = cload.Name,
                            ["type"] = total ? "nodal_force_total" : "nodal_force_per_node",
                            ["group"] = group
                        };
                        string suffix = total ? "_total_n" : "_per_node_n";
                        force["fx"+suffix] = cload.F1; force["fy"+suffix] = cload.F2; force["fz"+suffix] = cload.F3;
                        if(total) force["distribution"] = "UNIFORM_PER_SELECTED_NODE";
                        loads.Add(force);''')

exporter = 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
replace(exporter, '            Directory.CreateDirectory(outDir);', '''            // C1208_FORCE_PLAN: validate current selection and semantics before any file is written.
            AsterMaxForceDistribution.Plan forcePlan=AsterMaxForceDistribution.Build(contract);
            Directory.CreateDirectory(outDir);''')
start = '            bool perNodeLoad = load["fx_per_node_n"] != null || load["fy_per_node_n"] != null || load["fz_per_node_n"] != null;'
end = '            double fzTotal=fz*loadNodes.Count;'
text = read(exporter)
if start in text:
    old = text[text.index(start):text.index(end)+len(end)]
    replace(exporter, old, '''            double fx=forcePlan.Fx, fy=forcePlan.Fy, fz=forcePlan.Fz;
            string loadSemantics=forcePlan.Semantics;
            double fxTotal=forcePlan.FxTotal, fyTotal=forcePlan.FyTotal, fzTotal=forcePlan.FzTotal;''')
replace(exporter, '                ["load_semantics"]=loadSemantics,', '''                ["load_semantics"]=loadSemantics,
                ["force_distribution_report"]=forcePlan.Report,''')
replace(exporter, 'return v.ToString("0.###############",CultureInfo.InvariantCulture);',
        'return v.ToString("R",CultureInfo.InvariantCulture);')

transaction = 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
replace(transaction, '                solveModel=_controller.Model;', '''                solveModel=_controller.Model;
                // C1208_FORCE_PREVIEW: current model contents, not the EXE release label.
                JObject forcePreviewContract=AsterMaxModelContractBridge.Build(solveModel);
                var forcePreview=AsterMaxForceDistribution.Build(forcePreviewContract);
                if(!_asterMaxUiAuditMode && MessageBox.Show(this,
                    AsterMaxForceDistribution.Describe(forcePreviewContract,forcePreview)+"\\n\\n¿Continuar con esta definición?",
                    "[Astermax] Revisar fuerza y conexiones",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,
                    MessageBoxDefaultButton.Button2)!=DialogResult.Yes) return;''')
project = 'PrePoMax/PrePoMax.csproj'
replace(project, '    <Compile Include="AsterMaxBondedMpc.cs" />',
        '    <Compile Include="AsterMaxBondedMpc.cs" />\n    <Compile Include="AsterMaxForceDistribution.cs" />')
changes['PrePoMax/AsterMaxForceDistribution.cs'] = (Path(__file__).parent / 'AsterMaxForceDistribution.cs').read_text()
for rel, text in changes.items():
    (root/rel).write_text(text, encoding='utf-8')
print('C12.08 explicit total/per-node force model, editor, preview and exporter applied.')

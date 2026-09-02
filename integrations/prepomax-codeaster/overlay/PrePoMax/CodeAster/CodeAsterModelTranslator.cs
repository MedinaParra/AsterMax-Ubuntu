using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using CaeModel;
using CaeMesh;

namespace PrePoMax.CodeAster
{
    public sealed class CodeAsterTranslationResult
    {
        public string MeshFileName { get; internal set; }
        public string CommandFileName { get; internal set; }
        public string ExportFileName { get; internal set; }
        public List<string> Warnings { get; private set; }

        public CodeAsterTranslationResult()
        {
            Warnings = new List<string>();
        }
    }

    /// <summary>
    /// Semantic adapter from the PrePoMax object model to a Code_Aster command study.
    /// Phase 1 covers linear 3-D solid statics, elastic materials, fixed/prescribed
    /// displacement BCs, nodal forces, pressure and gravity. Unsupported entities are
    /// reported explicitly instead of being silently approximated.
    /// </summary>
    public static class CodeAsterModelTranslator
    {
        public static CodeAsterTranslationResult WriteStudy(FeModel model, CodeAsterCaseOptions options)
        {
            if (model == null) throw new ArgumentNullException("model");
            if (model.Mesh == null) throw new InvalidOperationException("The PrePoMax model has no mesh.");
            if (options == null) throw new ArgumentNullException("options");

            Directory.CreateDirectory(options.WorkingDirectory);
            CodeAsterTranslationResult output = new CodeAsterTranslationResult();

            string meshFile = Path.Combine(options.WorkingDirectory, options.JobName + ".mail");
            CodeAsterMeshWriteResult meshResult = CodeAsterMeshWriter.Write(meshFile, model.Mesh);
            output.MeshFileName = meshFile;
            output.Warnings.AddRange(meshResult.Warnings);

            StaticStep step = SelectStaticStep(model, output.Warnings);
            string comm = BuildLinearStaticComm(model, step, meshResult.Map, output.Warnings);
            output.CommandFileName = CodeAsterCaseWriter.WriteRawComm(options, comm);
            output.ExportFileName = CodeAsterCaseWriter.WriteExport(options);
            return output;
        }

        private static StaticStep SelectStaticStep(FeModel model, List<string> warnings)
        {
            List<StaticStep> staticSteps = new List<StaticStep>();
            foreach (Step step in model.StepCollection.StepsList)
            {
                if (!step.Active || !step.RunAnalysis) continue;
                StaticStep staticStep = step as StaticStep;
                if (staticStep != null && step.GetType() == typeof(StaticStep)) staticSteps.Add(staticStep);
                else warnings.Add("Step '" + step.Name + "' (" + step.GetType().Name + ") is not translated in the first Code_Aster static adapter.");
            }

            if (staticSteps.Count == 0)
                throw new NotSupportedException("Code_Aster phase 1 requires at least one active linear StaticStep.");
            if (staticSteps.Count > 1)
                warnings.Add("Multiple static steps are active; phase 1 translates only the first one: '" + staticSteps[0].Name + "'.");
            if (staticSteps[0].Nlgeom)
                throw new NotSupportedException("NLGEOM requires STAT_NON_LINE and is not enabled by the linear phase-1 translator.");
            return staticSteps[0];
        }

        private static string BuildLinearStaticComm(FeModel model, StaticStep step, CodeAsterMeshMap map, List<string> warnings)
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("DEBUT()");
            sb.AppendLine();
            sb.AppendLine("mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)");
            sb.AppendLine("model = AFFE_MODELE(");
            sb.AppendLine("    MAILLAGE=mesh,");
            sb.AppendLine("    AFFE=_F(GROUP_MA='" + Aster(map.VolumeGroup) + "', PHENOMENE='MECANIQUE', MODELISATION='3D'))");
            sb.AppendLine();

            Dictionary<string, string> materialVariables = WriteMaterials(sb, model, warnings);
            WriteMaterialAssignment(sb, model, map, materialVariables, warnings);

            LoadBlocks loads = BuildLoads(step, map, warnings);
            WriteLoad(sb, loads);

            sb.AppendLine("result = MECA_STATIQUE(");
            sb.AppendLine("    MODELE=model,");
            sb.Append("    CHAM_MATER=material_field");
            if (loads.HasAny) sb.AppendLine(",").AppendLine("    EXCIT=_F(CHARGE=load))");
            else sb.AppendLine(")");
            sb.AppendLine();
            sb.AppendLine("result = CALC_CHAMP(");
            sb.AppendLine("    reuse=result,");
            sb.AppendLine("    RESULTAT=result,");
            sb.AppendLine("    CONTRAINTE=('SIGM_ELNO', 'SIGM_NOEU'),");
            sb.AppendLine("    DEFORMATION=('EPSI_ELNO', 'EPSI_NOEU'),");
            sb.AppendLine("    CRITERES=('SIEQ_ELNO', 'SIEQ_NOEU'))");
            sb.AppendLine();
            sb.AppendLine("IMPR_RESU(");
            sb.AppendLine("    FORMAT='MED',");
            sb.AppendLine("    UNITE=80,");
            sb.AppendLine("    RESU=_F(");
            sb.AppendLine("        MAILLAGE=mesh,");
            sb.AppendLine("        RESULTAT=result,");
            sb.AppendLine("        NOM_CHAM=('DEPL', 'SIGM_NOEU', 'SIEQ_NOEU', 'EPSI_NOEU'),");
            sb.AppendLine("        TOUT_ORDRE='OUI'))");
            sb.AppendLine();
            sb.AppendLine("FIN()");
            return sb.ToString();
        }

        private static Dictionary<string, string> WriteMaterials(StringBuilder sb, FeModel model, List<string> warnings)
        {
            Dictionary<string, string> variables = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            int index = 1;
            foreach (var entry in model.Materials)
            {
                Material material = entry.Value;
                if (material == null || !material.Active) continue;

                double young;
                double poisson;
                double? density;
                if (!GetElasticData(material, out young, out poisson, out density, warnings))
                {
                    warnings.Add("Material '" + entry.Key + "' has no supported isotropic elastic definition and was skipped.");
                    continue;
                }

                string variable = "mat" + index.ToString(CultureInfo.InvariantCulture);
                index++;
                variables[entry.Key] = variable;
                sb.Append(variable).Append(" = DEFI_MATERIAU(ELAS=_F(E=")
                  .Append(F(young)).Append(", NU=").Append(F(poisson));
                if (density.HasValue) sb.Append(", RHO=").Append(F(density.Value));
                sb.AppendLine("))");
            }
            sb.AppendLine();

            if (variables.Count == 0)
                throw new NotSupportedException("No active isotropic elastic material can be translated to Code_Aster.");
            return variables;
        }

        private static bool GetElasticData(Material material, out double young, out double poisson, out double? density,
                                           List<string> warnings)
        {
            young = 0;
            poisson = 0;
            density = null;

            ElasticWithDensity combined = material.GetProperty<ElasticWithDensity>() as ElasticWithDensity;
            if (combined != null)
            {
                young = combined.YoungsModulus;
                poisson = combined.PoissonsRatio;
                if (combined.Density > 0) density = combined.Density;
                return young > 0;
            }

            Elastic elastic = material.GetProperty<Elastic>() as Elastic;
            if (elastic == null || elastic.YoungsPoissonsTemp == null || elastic.YoungsPoissonsTemp.Length == 0) return false;
            if (elastic.YoungsPoissonsTemp.Length > 1)
                warnings.Add("Temperature-dependent elastic table in material '" + material.Name + "' is reduced to its first row in phase 1.");
            young = elastic.YoungsPoissonsTemp[0][0];
            poisson = elastic.YoungsPoissonsTemp[0][1];

            Density den = material.GetProperty<Density>() as Density;
            if (den != null && den.DensityTemp != null && den.DensityTemp.Length > 0)
            {
                if (den.DensityTemp.Length > 1)
                    warnings.Add("Temperature-dependent density in material '" + material.Name + "' is reduced to its first row in phase 1.");
                density = den.DensityTemp[0][0];
            }
            return young > 0;
        }

        private static void WriteMaterialAssignment(StringBuilder sb, FeModel model, CodeAsterMeshMap map,
                                                    Dictionary<string, string> materialVariables, List<string> warnings)
        {
            List<string> assignments = new List<string>();
            foreach (var entry in model.Sections)
            {
                SolidSection section = entry.Value as SolidSection;
                if (section == null || !section.Active) continue;
                if (section.TwoD)
                {
                    warnings.Add("2-D solid section '" + section.Name + "' is outside the 3-D phase-1 adapter.");
                    continue;
                }

                string materialVariable;
                if (!materialVariables.TryGetValue(section.MaterialName, out materialVariable))
                {
                    warnings.Add("Section '" + section.Name + "' references unsupported material '" + section.MaterialName + "'.");
                    continue;
                }

                string group = map.ResolveElementGroup(section.RegionName);
                if (group == null)
                {
                    warnings.Add("Section '" + section.Name + "' region '" + section.RegionName + "' could not be mapped to GROUP_MA.");
                    continue;
                }
                assignments.Add("        _F(GROUP_MA='" + Aster(group) + "', MATER=" + materialVariable + ")");
            }

            sb.AppendLine("material_field = AFFE_MATERIAU(");
            sb.AppendLine("    MAILLAGE=mesh,");
            if (assignments.Count == 0)
            {
                if (materialVariables.Count != 1)
                    throw new NotSupportedException("Multiple materials exist but no supported solid-section assignments could be translated.");
                sb.AppendLine("    AFFE=_F(GROUP_MA='" + Aster(map.VolumeGroup) + "', MATER=" + materialVariables.Values.First() + "))");
                warnings.Add("No supported 3-D solid section assignment was found; the only active material was assigned to all volume elements.");
            }
            else
            {
                sb.AppendLine("    AFFE=(");
                for (int i = 0; i < assignments.Count; i++)
                    sb.Append(assignments[i]).AppendLine(i == assignments.Count - 1 ? "))" : ",");
            }
            sb.AppendLine();
        }

        private sealed class LoadBlocks
        {
            public List<string> Ddl = new List<string>();
            public List<string> Nodal = new List<string>();
            public List<string> Pressure = new List<string>();
            public List<string> Gravity = new List<string>();
            public bool HasAny { get { return Ddl.Count + Nodal.Count + Pressure.Count + Gravity.Count > 0; } }
        }

        private static LoadBlocks BuildLoads(StaticStep step, CodeAsterMeshMap map, List<string> warnings)
        {
            LoadBlocks blocks = new LoadBlocks();

            foreach (var entry in step.BoundaryConditions)
            {
                BoundaryCondition bc = entry.Value;
                if (bc == null || !bc.Active) continue;
                if (bc.Complex)
                {
                    warnings.Add("Complex boundary condition '" + bc.Name + "' is not supported by the static adapter.");
                    continue;
                }

                string group = map.ResolveNodeGroup(bc.RegionName);
                if (group == null)
                {
                    warnings.Add("Boundary condition '" + bc.Name + "' region '" + bc.RegionName + "' could not be mapped to GROUP_NO.");
                    continue;
                }

                if (bc is FixedBC)
                {
                    blocks.Ddl.Add("_F(GROUP_NO='" + Aster(group) + "', DX=0.0, DY=0.0, DZ=0.0)");
                }
                else if (bc is DisplacementRotation)
                {
                    DisplacementRotation dr = (DisplacementRotation)bc;
                    List<string> values = new List<string>();
                    AddDof(values, "DX", dr.U1);
                    AddDof(values, "DY", dr.U2);
                    AddDof(values, "DZ", dr.U3);
                    if (values.Count > 0)
                        blocks.Ddl.Add("_F(GROUP_NO='" + Aster(group) + "', " + String.Join(", ", values) + ")");
                    if (!Double.IsNaN(dr.UR1) || !Double.IsNaN(dr.UR2) || !Double.IsNaN(dr.UR3))
                        warnings.Add("Rotational DOFs in BC '" + bc.Name + "' are ignored for the phase-1 3-D solid model.");
                }
                else warnings.Add("Boundary condition '" + bc.Name + "' type " + bc.GetType().Name + " is not yet translated.");
            }

            foreach (var entry in step.Loads)
            {
                Load load = entry.Value;
                if (load == null || !load.Active) continue;
                if (load.Complex)
                {
                    warnings.Add("Complex load '" + load.Name + "' is not supported by the static adapter.");
                    continue;
                }

                CLoad cload = load as CLoad;
                if (cload != null)
                {
                    List<string> components = new List<string>();
                    if (cload.F1 != 0) components.Add("FX=" + F(cload.F1));
                    if (cload.F2 != 0) components.Add("FY=" + F(cload.F2));
                    if (cload.F3 != 0) components.Add("FZ=" + F(cload.F3));
                    if (components.Count == 0) continue;

                    if (cload.RegionType == RegionTypeEnum.NodeId && cload.NodeId >= 0)
                        blocks.Nodal.Add("_F(NOEUD='N" + cload.NodeId.ToString(CultureInfo.InvariantCulture) + "', " + String.Join(", ", components) + ")");
                    else
                    {
                        string group = map.ResolveNodeGroup(cload.RegionName);
                        if (group != null)
                            blocks.Nodal.Add("_F(GROUP_NO='" + Aster(group) + "', " + String.Join(", ", components) + ")");
                        else warnings.Add("Concentrated load '" + load.Name + "' region could not be mapped to GROUP_NO.");
                    }
                    continue;
                }

                DLoad pressure = load as DLoad;
                if (pressure != null)
                {
                    string group = map.ResolveSurfaceGroup(pressure.SurfaceName);
                    if (group != null)
                        blocks.Pressure.Add("_F(GROUP_MA='" + Aster(group) + "', PRES=" + F(pressure.Magnitude) + ")");
                    else warnings.Add("Pressure load '" + load.Name + "' surface '" + pressure.SurfaceName + "' has no exported solid-face GROUP_MA.");
                    continue;
                }

                GravityLoad gravity = load as GravityLoad;
                if (gravity != null)
                {
                    double norm = Math.Sqrt(gravity.F1 * gravity.F1 + gravity.F2 * gravity.F2 + gravity.F3 * gravity.F3);
                    if (norm <= 0) continue;
                    string group = map.ResolveElementGroup(gravity.RegionName);
                    if (group == null)
                    {
                        warnings.Add("Gravity load '" + load.Name + "' region could not be mapped to GROUP_MA.");
                        continue;
                    }
                    blocks.Gravity.Add("_F(GROUP_MA='" + Aster(group) + "', GRAVITE=" + F(norm) +
                                       ", DIRECTION=(" + F(gravity.F1 / norm) + ", " + F(gravity.F2 / norm) + ", " + F(gravity.F3 / norm) + "))");
                    continue;
                }

                warnings.Add("Load '" + load.Name + "' type " + load.GetType().Name + " is not yet translated.");
            }
            return blocks;
        }

        private static void WriteLoad(StringBuilder sb, LoadBlocks blocks)
        {
            if (!blocks.HasAny) return;
            sb.AppendLine("load = AFFE_CHAR_MECA(");
            sb.AppendLine("    MODELE=model,");
            List<Tuple<string, List<string>>> sections = new List<Tuple<string, List<string>>>();
            if (blocks.Ddl.Count > 0) sections.Add(Tuple.Create("DDL_IMPO", blocks.Ddl));
            if (blocks.Nodal.Count > 0) sections.Add(Tuple.Create("FORCE_NODALE", blocks.Nodal));
            if (blocks.Pressure.Count > 0) sections.Add(Tuple.Create("PRES_REP", blocks.Pressure));
            if (blocks.Gravity.Count > 0) sections.Add(Tuple.Create("PESANTEUR", blocks.Gravity));

            for (int s = 0; s < sections.Count; s++)
            {
                sb.Append("    ").Append(sections[s].Item1).AppendLine("=(");
                for (int i = 0; i < sections[s].Item2.Count; i++)
                    sb.Append("        ").Append(sections[s].Item2[i]).AppendLine(i == sections[s].Item2.Count - 1 ? ")" + (s == sections.Count - 1 ? ")" : ",") : ",");
            }
            sb.AppendLine();
        }

        private static void AddDof(List<string> values, string name, double value)
        {
            if (Double.IsNaN(value)) return;
            if (Double.IsPositiveInfinity(value)) value = 0;
            values.Add(name + "=" + F(value));
        }

        private static string F(double value)
        {
            return value.ToString("R", CultureInfo.InvariantCulture);
        }

        private static string Aster(string value)
        {
            return (value ?? String.Empty).Replace("'", "''");
        }
    }
}

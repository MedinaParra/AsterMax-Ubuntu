using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace PrePoMax.CodeAster
{
    public sealed class CodeAsterCaseOptions
    {
        public string JobName { get; set; }
        public string WorkingDirectory { get; set; }
        public string Version { get; set; }
        public int NumCpus { get; set; }
        public int MemoryMB { get; set; }
        public int TimeLimitSeconds { get; set; }

        public CodeAsterCaseOptions()
        {
            Version = "stable";
            NumCpus = 1;
            MemoryMB = 4096;
            TimeLimitSeconds = 3600;
        }
    }

    public static class CodeAsterCaseWriter
    {
        public static string WriteExport(CodeAsterCaseOptions options)
        {
            Validate(options);
            Directory.CreateDirectory(options.WorkingDirectory);

            string path = Path.Combine(options.WorkingDirectory, options.JobName + ".export");
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("P actions make_etude");
            sb.AppendLine("P version " + SafeToken(options.Version, "stable"));
            sb.AppendLine("P time_limit " + Math.Max(1, options.TimeLimitSeconds).ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("P memory_limit " + Math.Max(256, options.MemoryMB).ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("P ncpus " + Math.Max(1, options.NumCpus).ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("F comm " + options.JobName + ".comm D 1");
            sb.AppendLine("F libr " + options.JobName + ".mail D 20");
            sb.AppendLine("F mess " + options.JobName + ".mess R 6");
            sb.AppendLine("F rmed " + options.JobName + ".rmed R 80");
            File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));
            return path;
        }

        public static string WriteRawComm(CodeAsterCaseOptions options, string commandBody)
        {
            Validate(options);
            if (String.IsNullOrWhiteSpace(commandBody))
                throw new ArgumentException("A Code_Aster command body is required.", "commandBody");

            Directory.CreateDirectory(options.WorkingDirectory);
            string path = Path.Combine(options.WorkingDirectory, options.JobName + ".comm");
            File.WriteAllText(path, commandBody, new UTF8Encoding(false));
            return path;
        }

        public static string WriteLinearStatic3D(CodeAsterCaseOptions options,
                                                  double youngModulus,
                                                  double poissonRatio,
                                                  string fixedGroup,
                                                  string pressureGroup,
                                                  double pressure)
        {
            Validate(options);
            if (youngModulus <= 0) throw new ArgumentOutOfRangeException("youngModulus");
            if (poissonRatio <= -1 || poissonRatio >= 0.5) throw new ArgumentOutOfRangeException("poissonRatio");
            if (String.IsNullOrWhiteSpace(fixedGroup)) throw new ArgumentException("Fixed group is required.", "fixedGroup");
            if (String.IsNullOrWhiteSpace(pressureGroup)) throw new ArgumentException("Pressure group is required.", "pressureGroup");

            string e = youngModulus.ToString("R", CultureInfo.InvariantCulture);
            string nu = poissonRatio.ToString("R", CultureInfo.InvariantCulture);
            string p = pressure.ToString("R", CultureInfo.InvariantCulture);

            StringBuilder sb = new StringBuilder();
            sb.AppendLine("DEBUT()");
            sb.AppendLine();
            sb.AppendLine("mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)");
            sb.AppendLine("model = AFFE_MODELE(");
            sb.AppendLine("    MAILLAGE=mesh,");
            sb.AppendLine("    AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'))");
            sb.AppendLine();
            sb.AppendLine("material = DEFI_MATERIAU(ELAS=_F(E=" + e + ", NU=" + nu + "))");
            sb.AppendLine("material_field = AFFE_MATERIAU(");
            sb.AppendLine("    MAILLAGE=mesh,");
            sb.AppendLine("    AFFE=_F(GROUP_MA='VOLUME_ALL', MATER=material))");
            sb.AppendLine();
            sb.AppendLine("load = AFFE_CHAR_MECA(");
            sb.AppendLine("    MODELE=model,");
            sb.AppendLine("    DDL_IMPO=_F(GROUP_NO='" + EscapeAster(fixedGroup) + "', DX=0.0, DY=0.0, DZ=0.0),");
            sb.AppendLine("    PRES_REP=_F(GROUP_MA='" + EscapeAster(pressureGroup) + "', PRES=" + p + "))");
            sb.AppendLine();
            sb.AppendLine("result = MECA_STATIQUE(");
            sb.AppendLine("    MODELE=model,");
            sb.AppendLine("    CHAM_MATER=material_field,");
            sb.AppendLine("    EXCIT=_F(CHARGE=load))");
            sb.AppendLine();
            sb.AppendLine("result = CALC_CHAMP(");
            sb.AppendLine("    reuse=result,");
            sb.AppendLine("    RESULTAT=result,");
            sb.AppendLine("    CONTRAINTE=('SIGM_ELNO', 'SIGM_NOEU'),");
            sb.AppendLine("    DEFORMATION=('EPSI_ELNO', 'EPSI_NOEU'),");
            sb.AppendLine("    CRITERES=('SIEQ_ELNO', 'SIEQ_NOEU'))");
            sb.AppendLine();
            sb.AppendLine("IMPR_RESU(");
            sb.AppendLine("    FORMAT='MED', UNITE=80,");
            sb.AppendLine("    RESU=_F(MAILLAGE=mesh, RESULTAT=result,");
            sb.AppendLine("            NOM_CHAM=('DEPL', 'SIGM_NOEU', 'SIEQ_NOEU', 'EPSI_NOEU'), TOUT_ORDRE='OUI'))");
            sb.AppendLine();
            sb.AppendLine("FIN()");

            return WriteRawComm(options, sb.ToString());
        }

        public static void WriteLinearStaticStudy(CodeAsterCaseOptions options,
                                                   double youngModulus,
                                                   double poissonRatio,
                                                   string fixedGroup,
                                                   string pressureGroup,
                                                   double pressure)
        {
            WriteLinearStatic3D(options, youngModulus, poissonRatio, fixedGroup, pressureGroup, pressure);
            WriteExport(options);
        }

        private static void Validate(CodeAsterCaseOptions options)
        {
            if (options == null) throw new ArgumentNullException("options");
            if (String.IsNullOrWhiteSpace(options.JobName)) throw new ArgumentException("Job name is required.");
            if (String.IsNullOrWhiteSpace(options.WorkingDirectory)) throw new ArgumentException("Working directory is required.");
        }

        private static string SafeToken(string value, string fallback)
        {
            if (String.IsNullOrWhiteSpace(value)) return fallback;
            return value.Trim().Replace(" ", "_");
        }

        private static string EscapeAster(string value)
        {
            return value.Replace("'", "''");
        }
    }
}

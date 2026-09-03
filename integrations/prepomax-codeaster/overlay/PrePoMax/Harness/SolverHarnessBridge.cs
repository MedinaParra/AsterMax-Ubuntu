using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using CaeJob;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax.Harness
{
    /// <summary>
    /// Builds the solver-neutral AsterMax harness manifest and validates the
    /// resulting harness report before solver results are admitted to the GUI.
    /// </summary>
    public static class SolverHarnessBridge
    {
        public const int SchemaVersion = 1;

        public static string Prepare(AnalysisJob job, string pythonExecutable, string harnessScriptPath)
        {
            if (job == null) throw new ArgumentNullException("job");
            if (String.IsNullOrWhiteSpace(job.WorkDirectory))
                throw new InvalidOperationException("The analysis job has no working directory.");
            if (String.IsNullOrWhiteSpace(job.Executable))
                throw new InvalidOperationException("The analysis job has no solver executable.");
            if (String.IsNullOrWhiteSpace(pythonExecutable))
                throw new InvalidOperationException("A Python executable is required by the AsterMax solver harness.");
            if (String.IsNullOrWhiteSpace(harnessScriptPath) || !File.Exists(harnessScriptPath))
                throw new FileNotFoundException("The bundled AsterMax solver harness was not found.", harnessScriptPath);

            Directory.CreateDirectory(job.WorkDirectory);

            string solver = job.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster ? "code_aster" : "calculix";
            string manifestPath = Path.Combine(job.WorkDirectory, job.Name + ".harness.manifest.json");

            Dictionary<string, object> manifest = new Dictionary<string, object>();
            manifest["schema"] = SchemaVersion;
            manifest["case_name"] = job.Name;
            manifest["solver"] = solver;
            manifest["job_name"] = job.Name;
            manifest["working_directory"] = ".";
            manifest["solver_executable"] = job.Executable;
            manifest["timeout_seconds"] = Math.Max(1, job.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster
                ? job.CodeAsterTimeLimitSeconds
                : 3600 * 24 * 7);
            manifest["environment"] = GetEnvironment(job.EnvironmentVariables);

            if (job.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster)
            {
                manifest["required_inputs"] = new string[]
                {
                    job.Name + ".comm",
                    job.Name + ".mail",
                    job.Name + ".export"
                };
                manifest["required_outputs"] = new string[]
                {
                    job.Name + ".mess",
                    job.Name + ".rmed",
                    job.Name + ".resu"
                };
                manifest["result_contract"] = new Dictionary<string, object>
                {
                    { "required_tables", new string[]
                        {
                            "PPM_DEPL",
                            "PPM_STRESS_N",
                            "PPM_STRESS_S",
                            "PPM_STRAIN_N",
                            "PPM_STRAIN_S"
                        }
                    },
                    { "min_rows_per_table", 1 }
                };
            }
            else
            {
                manifest["required_inputs"] = new string[] { job.Name + ".inp" };
                manifest["required_outputs"] = new string[] { job.Name + ".frd" };
            }

            File.WriteAllText(manifestPath,
                              JsonConvert.SerializeObject(manifest, Formatting.Indented),
                              new UTF8Encoding(false));

            job.UseSolverHarness = true;
            job.HarnessExecutable = pythonExecutable;
            job.HarnessScriptPath = harnessScriptPath;
            job.HarnessManifestPath = manifestPath;
            job.HarnessReportPath = GetReportPath(job.WorkDirectory, job.Name);
            return manifestPath;
        }

        private static Dictionary<string, string> GetEnvironment(List<EnvironmentVariable> variables)
        {
            Dictionary<string, string> environment = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (variables == null) return environment;

            foreach (EnvironmentVariable variable in variables)
            {
                if (variable == null || !variable.Active || String.IsNullOrWhiteSpace(variable.Name)) continue;
                environment[variable.Name.Trim()] = variable.Value ?? String.Empty;
            }
            return environment;
        }

        public static string GetReportPath(string workDirectory, string jobName)
        {
            return Path.Combine(workDirectory, jobName + ".harness.json");
        }

        public static string GetReportPathForResult(string resultFileName)
        {
            string directory = Path.GetDirectoryName(resultFileName);
            string name = Path.GetFileNameWithoutExtension(resultFileName);
            return GetReportPath(directory, name);
        }

        public static bool TryValidatePassingReport(string reportPath, out string reason)
        {
            reason = null;
            try
            {
                if (String.IsNullOrWhiteSpace(reportPath) || !File.Exists(reportPath))
                {
                    reason = "Harness report does not exist: " + reportPath;
                    return false;
                }

                JObject report = JObject.Parse(File.ReadAllText(reportPath));
                string status = (string)report["status"];
                if (!String.Equals(status, "PASS", StringComparison.OrdinalIgnoreCase))
                {
                    reason = "Harness status is " + (status ?? "missing") + ".";
                    return false;
                }

                JToken checksToken = report["checks"];
                JArray checks = checksToken as JArray;
                if (checks == null || checks.Count == 0)
                {
                    reason = "Harness report contains no post-run checks.";
                    return false;
                }

                foreach (JToken item in checks)
                {
                    bool? passed = (bool?)item["passed"];
                    if (passed != true)
                    {
                        reason = "Harness report contains a failed or invalid check: " + ((string)item["name"] ?? "unnamed") + ".";
                        return false;
                    }
                }

                return true;
            }
            catch (Exception ex)
            {
                reason = "Unable to validate harness report: " + ex.Message;
                return false;
            }
        }
    }
}

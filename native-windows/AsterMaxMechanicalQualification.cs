using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    internal sealed class AsterMaxMechanicalQualification
    {
        public string Status { get; private set; }
        public List<string> Findings { get; private set; }

        private AsterMaxMechanicalQualification()
        {
            Status = "SOLVED_WITH_ENGINEERING_WARNINGS";
            Findings = new List<string>();
        }

        public static AsterMaxMechanicalQualification Evaluate(AsterMaxResultsBundle bundle)
        {
            var q = new AsterMaxMechanicalQualification();
            if (bundle == null || String.IsNullOrWhiteSpace(bundle.SourceFile) || !File.Exists(bundle.SourceFile))
            {
                q.Status = "BLOCKED";
                q.Findings.Add("BLOCK · Results bundle is unavailable.");
                return q;
            }

            string sidecar = Path.Combine(Path.GetDirectoryName(bundle.SourceFile) ?? "", "mechanical-qualification.json");
            if (File.Exists(sidecar))
            {
                JObject report = JObject.Parse(File.ReadAllText(sidecar));
                q.Status = (string)report["status"] ?? "SOLVED_WITH_ENGINEERING_WARNINGS";
                JArray findings = report["findings"] as JArray;
                if (findings != null)
                {
                    foreach (JObject item in findings.OfType<JObject>())
                    {
                        string level=(string)item["level"] ?? "INFO";
                        string message=(string)item["message"] ?? "";
                        q.Findings.Add(level+" · "+message);
                    }
                }
                if (q.Findings.Count == 0) q.Findings.Add("INFO · Mechanical qualification sidecar is present.");
                return q;
            }

            JObject root = JObject.Parse(File.ReadAllText(bundle.SourceFile));
            JObject source = root["source"] as JObject;
            JObject integrity = root["integrity"] as JObject;
            JObject mesh = root["mesh"] as JObject;
            JObject fields = root["fields"] as JObject;

            bool real = (string)source?["kind"] == "REAL_CODE_ASTER_MED" &&
                        (bool?)integrity?["fea_values_invented"] == false;
            if (real) q.Findings.Add("PASS · Real Code_Aster MED evidence.");
            else
            {
                q.Status = "BLOCKED";
                q.Findings.Add("BLOCK · Solver evidence is not authenticated as real Code_Aster output.");
            }

            bool componentFirst = (bool?)integrity?["von_mises_component_first_ansys_parity"] == true;
            q.Findings.Add((componentFirst ? "PASS" : "WARN") +
                " · Equivalent stress " +
                (componentFirst ? "uses component-first nodal tensor averaging." :
                                  "does not prove component-first nodal tensor averaging."));

            string[] elementTypes = mesh?["element_types"] == null
                ? new string[0]
                : mesh["element_types"].Select(x => (string)x).Where(x => !String.IsNullOrWhiteSpace(x)).ToArray();
            bool quadratic = elementTypes.Length > 0 && elementTypes.All(x => x == "TETRA10");
            if (quadratic) q.Findings.Add("PASS · Structural solid mesh is quadratic TETRA10.");
            else
            {
                q.Findings.Add("WARN · Structural solid mesh is not proven quadratic; stress comparison may be mesh-order sensitive.");
                if (q.Status != "BLOCKED") q.Status = "SOLVED_WITH_ENGINEERING_WARNINGS";
            }

            JObject reaction = fields?["reaction"] as JObject;
            if (reaction != null && reaction["resultant_n"] is JArray rv && rv.Count >= 3)
            {
                double rx=(double)rv[0], ry=(double)rv[1], rz=(double)rv[2];
                q.Findings.Add(String.Format(CultureInfo.InvariantCulture,
                    "PASS · REAC_NODA resultant captured: [{0:G7}, {1:G7}, {2:G7}] N.", rx, ry, rz));
                q.Findings.Add("WARN · No qualification sidecar is present, so the independently assembled load resultant has not been compared here.");
            }
            else
            {
                q.Findings.Add("WARN · REAC_NODA resultant is unavailable; global equilibrium is not automatically checked.");
                if (q.Status != "BLOCKED") q.Status = "SOLVED_WITH_ENGINEERING_WARNINGS";
            }

            if (q.Status != "BLOCKED")
            {
                bool hasWarnings = q.Findings.Any(x => x.StartsWith("WARN", StringComparison.Ordinal));
                q.Status = hasWarnings ? "SOLVED_WITH_ENGINEERING_WARNINGS" : "ENGINEERING_QUALIFIED";
            }
            return q;
        }

        public string Describe()
        {
            return "Mechanical Qualification: " + Status + Environment.NewLine +
                   String.Join(Environment.NewLine, Findings);
        }
    }
}

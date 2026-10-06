using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    internal sealed class AsterMaxMechanicalQualification
    {
        public string Status { get; private set; }
        public List<string> Findings { get; private set; }
        private AsterMaxMechanicalQualification()
        {
            Status = "BLOCKED";
            Findings = new List<string>();
        }
        public static AsterMaxMechanicalQualification Evaluate(AsterMaxResultsBundle bundle)
        {
            var q = new AsterMaxMechanicalQualification();
            if(bundle==null || String.IsNullOrWhiteSpace(bundle.SourceFile) || !File.Exists(bundle.SourceFile))
            {
                q.Findings.Add("BLOCKED: Results bundle is unavailable.");
                return q;
            }
            string sidecar=Path.Combine(Path.GetDirectoryName(bundle.SourceFile) ?? "", "mechanical-qualification.json");
            if(!File.Exists(sidecar))
            {
                q.Findings.Add("BLOCKED: No mechanical qualification report accompanies this result.");
                return q;
            }
            JObject report=JObject.Parse(File.ReadAllText(sidecar));
            string expected=(string)report["bundle_sha256"];
            string actual;
            using(var sha=SHA256.Create())
            using(var stream=File.OpenRead(bundle.SourceFile))
                actual=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            if(!String.Equals(expected, actual, StringComparison.OrdinalIgnoreCase))
            {
                q.Findings.Add("BLOCKED: Qualification report belongs to another result bundle.");
                return q;
            }
            string qualification=(string)report["engineering_qualification"];
            if(qualification!="ENGINEERING_QUALIFIED" && qualification!="SOLVED_WITH_ENGINEERING_WARNINGS")
            {
                q.Findings.Add("BLOCKED: Mechanical qualification rejected this result.");
                return q;
            }
            q.Status=qualification;
            var findings=report["findings"] as JArray;
            if(findings!=null)
                foreach(var item in findings.OfType<JObject>())
                    q.Findings.Add(((string)item["level"] ?? "INFO")+": "+((string)item["message"] ?? ""));
            return q;
        }
        public string Describe()
        {
            return "Mechanical Qualification: "+Status+Environment.NewLine+String.Join(Environment.NewLine,Findings);
        }
    }
}

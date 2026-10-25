using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PrePoMax.CodeAster
{
    public sealed class CodeAsterCommandInfo
    {
        public string Name { get; set; }
        public string Module { get; set; }

        public override string ToString()
        {
            return Name;
        }
    }

    public sealed class CodeAsterCatalog
    {
        public string Version { get; set; }
        public List<CodeAsterCommandInfo> Commands { get; private set; }

        public CodeAsterCatalog()
        {
            Commands = new List<CodeAsterCommandInfo>();
        }
    }

    public static class CodeAsterCatalogService
    {
        public static CodeAsterCatalog Load(string pythonExecutable,
                                            string helperScriptPath,
                                            string[] environmentVariables,
                                            int timeoutMilliseconds)
        {
            if (String.IsNullOrWhiteSpace(pythonExecutable))
                throw new ArgumentException("Python executable is required.", "pythonExecutable");
            if (String.IsNullOrWhiteSpace(helperScriptPath) || !File.Exists(helperScriptPath))
                throw new FileNotFoundException("Code_Aster catalog helper was not found.", helperScriptPath);

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExecutable;
            psi.Arguments = Quote(helperScriptPath);
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;

            ApplyEnvironment(psi, environmentVariables);

            using (Process process = new Process())
            {
                process.StartInfo = psi;
                process.Start();

                string stdout = process.StandardOutput.ReadToEnd();
                string stderr = process.StandardError.ReadToEnd();

                if (!process.WaitForExit(timeoutMilliseconds))
                {
                    try { process.Kill(); }
                    catch { }
                    throw new TimeoutException("Timed out while reading the Code_Aster command catalog.");
                }

                JObject root;
                try
                {
                    root = JObject.Parse(stdout);
                }
                catch (Exception ex)
                {
                    throw new InvalidDataException("Code_Aster catalog helper returned invalid JSON. " + stderr, ex);
                }

                string error = (string)root["error"];
                if (process.ExitCode != 0 || !String.IsNullOrWhiteSpace(error))
                {
                    string message = !String.IsNullOrWhiteSpace(error) ? error : stderr;
                    throw new InvalidOperationException("Unable to load Code_Aster catalog: " + message);
                }

                CodeAsterCatalog catalog = new CodeAsterCatalog();
                catalog.Version = (string)root["version"];

                JArray commands = root["commands"] as JArray;
                if (commands != null)
                {
                    foreach (JToken token in commands)
                    {
                        string name = (string)token["name"];
                        if (String.IsNullOrWhiteSpace(name)) continue;
                        catalog.Commands.Add(new CodeAsterCommandInfo
                        {
                            Name = name,
                            Module = (string)token["module"]
                        });
                    }
                }

                return catalog;
            }
        }

        private static void ApplyEnvironment(ProcessStartInfo psi, string[] variables)
        {
            if (variables == null) return;
            foreach (string entry in variables)
            {
                if (String.IsNullOrWhiteSpace(entry)) continue;
                int separator = entry.IndexOf('=');
                if (separator <= 0) continue;
                string key = entry.Substring(0, separator).Trim();
                string value = entry.Substring(separator + 1);
                if (key.Length > 0) psi.EnvironmentVariables[key] = value;
            }
        }

        private static string Quote(string value)
        {
            if (value == null) return "\"\"";
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }
    }
}

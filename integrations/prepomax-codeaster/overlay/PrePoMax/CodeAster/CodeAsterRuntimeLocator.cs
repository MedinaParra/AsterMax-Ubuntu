using System;
using System.Collections.Generic;
using System.IO;
using System.Diagnostics;
using Microsoft.Win32;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Resolves a usable native Windows Code_Aster launcher.
    /// Modern Code_Aster Windows MSI packages install a wrapper at
    /// %LOCALAPPDATA%\code_aster\bin\run_aster.bat.
    /// </summary>
    public static class CodeAsterRuntimeLocator
    {
        public static string Resolve(string configured)
        {
            List<string> candidates = new List<string>();
            AddConfiguredCandidate(candidates, configured);

            string appBase = AppDomain.CurrentDomain.BaseDirectory;
            Add(candidates, Path.Combine(appBase, "CodeAsterRuntime", "bin", "run_aster.bat"));
            Add(candidates, Path.Combine(appBase, "CodeAsterRuntime", "bin", "as_run.bat"));
            Add(candidates, Path.Combine(appBase, "CodeAster", "bin", "run_aster.bat"));

            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrWhiteSpace(local)) local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (!String.IsNullOrWhiteSpace(local))
            {
                Add(candidates, Path.Combine(local, "code_aster", "bin", "run_aster.bat"));
                Add(candidates, Path.Combine(local, "code_aster", "bin", "as_run.bat"));
                Add(candidates, Path.Combine(local, "code_aster", "install", "bin", "as_run.bat"));
            }

            string env = Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER");
            if (!String.IsNullOrWhiteSpace(env))
            {
                string expanded = Environment.ExpandEnvironmentVariables(env.Trim().Trim('"'));
                if (File.Exists(expanded)) Add(candidates, expanded);
                else
                {
                    Add(candidates, Path.Combine(expanded, "bin", "run_aster.bat"));
                    Add(candidates, Path.Combine(expanded, "bin", "as_run.bat"));
                    Add(candidates, Path.Combine(expanded, "install", "bin", "as_run.bat"));
                }
            }

            foreach (string key in new string[] { "v2026", "v2025", "v2024", "v2023", "v2021" })
            {
                string root = ReadRegistryRoot(key);
                if (String.IsNullOrWhiteSpace(root)) continue;
                Add(candidates, Path.Combine(root, "bin", "run_aster.bat"));
                Add(candidates, Path.Combine(root, "bin", "as_run.bat"));
                Add(candidates, Path.Combine(root, "install", "bin", "as_run.bat"));
            }

            foreach (string candidate in candidates)
            {
                try
                {
                    if (!String.IsNullOrWhiteSpace(candidate) && File.Exists(candidate))
                        return Path.GetFullPath(candidate);
                }
                catch { }
            }

            foreach (string name in new string[] { "run_aster.bat", "run_aster.cmd", "run_aster.exe",
                                                   "as_run.bat", "as_run.cmd", "as_run.exe" })
            {
                string path = FindOnPath(name);
                if (path != null) return path;
            }

            return GetExpectedWindowsLauncher();
        }

        public static bool IsAvailable(string configured)
        {
            string launcher = Resolve(configured);
            return !String.IsNullOrWhiteSpace(launcher) && File.Exists(launcher);
        }

        public static bool TryInstallInteractive()
        {
            string setup = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "INSTALL_CODE_ASTER.cmd");
            if (!File.Exists(setup)) return false;

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = setup;
                psi.WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory;
                psi.UseShellExecute = true;
                using (Process process = Process.Start(psi))
                {
                    if (process == null) return false;
                    process.WaitForExit();
                }
                return IsAvailable(null);
            }
            catch
            {
                return false;
            }
        }

        public static string GetExpectedWindowsLauncher()
        {
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrWhiteSpace(local)) local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (String.IsNullOrWhiteSpace(local)) return "run_aster.bat";
            return Path.Combine(local, "code_aster", "bin", "run_aster.bat");
        }

        public static string GetDefaultWorkDirectory()
        {
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrWhiteSpace(local)) local = Path.GetTempPath();
            return Path.Combine(local, "AsterMax Mechanical", "Work", "CodeAster");
        }

        private static void AddConfiguredCandidate(List<string> candidates, string configured)
        {
            if (String.IsNullOrWhiteSpace(configured)) return;
            string value = Environment.ExpandEnvironmentVariables(configured.Trim().Trim('"'));

            // Bare tokens such as "as_run" are intentionally ignored here.
            // They are handled by PATH lookup after the native Windows install locations.
            if (!Path.IsPathRooted(value) &&
                value.IndexOf(Path.DirectorySeparatorChar) < 0 &&
                value.IndexOf(Path.AltDirectorySeparatorChar) < 0)
                return;
            Add(candidates, value);
        }

        private static void Add(List<string> candidates, string value)
        {
            if (!String.IsNullOrWhiteSpace(value)) candidates.Add(value);
        }

        private static string FindOnPath(string fileName)
        {
            string path = Environment.GetEnvironmentVariable("PATH");
            if (String.IsNullOrWhiteSpace(path)) return null;

            foreach (string entry in path.Split(Path.PathSeparator))
            {
                try
                {
                    string folder = entry.Trim().Trim('"');
                    if (String.IsNullOrWhiteSpace(folder)) continue;
                    string candidate = Path.Combine(folder, fileName);
                    if (File.Exists(candidate)) return Path.GetFullPath(candidate);
                }
                catch { }
            }
            return null;
        }

        private static string ReadRegistryRoot(string versionKey)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"SOFTWARE\code_aster\" + versionKey))
                {
                    if (key == null) return null;
                    foreach (string valueName in key.GetValueNames())
                    {
                        object value = key.GetValue(valueName);
                        string path = value as string;
                        if (!String.IsNullOrWhiteSpace(path) && Directory.Exists(path)) return path;
                    }
                }
            }
            catch { }
            return null;
        }
    }
}

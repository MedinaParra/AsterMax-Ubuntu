using System;
using System.IO;

namespace PrePoMax
{
    /// <summary>
    /// Solver-neutral execution-harness settings. The harness runtime is intentionally
    /// separate from the Python environment used to inspect the Code_Aster catalog.
    /// </summary>
    [Serializable]
    public class HarnessSettings : ISettings
    {
        private string _pythonExecutable;

        public string PythonExecutable
        {
            get { return _pythonExecutable; }
            set { _pythonExecutable = value; }
        }

        public HarnessSettings()
        {
            Reset();
        }

        public void CheckValues()
        {
            string bundled = GetBundledPythonExecutable();
            if (File.Exists(bundled) &&
                (String.IsNullOrWhiteSpace(_pythonExecutable) ||
                 String.Equals(_pythonExecutable, "python", StringComparison.OrdinalIgnoreCase) ||
                 String.Equals(_pythonExecutable, "python.exe", StringComparison.OrdinalIgnoreCase)))
                _pythonExecutable = bundled;
            else if (String.IsNullOrWhiteSpace(_pythonExecutable))
                _pythonExecutable = GetDefaultPythonExecutable();
        }

        public void Reset()
        {
            _pythonExecutable = GetDefaultPythonExecutable();
            CheckValues();
        }

        private static string GetBundledPythonExecutable()
        {
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory,
                                "Runtime", "Python", "python.exe");
        }

        private static string GetDefaultPythonExecutable()
        {
            string bundled = GetBundledPythonExecutable();
            if (File.Exists(bundled)) return bundled;
            return "python";
        }
    }
}

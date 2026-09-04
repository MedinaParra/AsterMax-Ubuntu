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
            if (String.IsNullOrWhiteSpace(_pythonExecutable)) _pythonExecutable = GetDefaultPythonExecutable();
        }

        public void Reset()
        {
            _pythonExecutable = GetDefaultPythonExecutable();
            CheckValues();
        }

        private static string GetDefaultPythonExecutable()
        {
            string bundled = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,
                                          "Runtime", "Python", "python.exe");
            if (File.Exists(bundled)) return bundled;
            return "python";
        }
    }
}

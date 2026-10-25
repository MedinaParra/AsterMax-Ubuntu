using System;
using System.Collections.Generic;
using System.IO;

namespace PrePoMax
{
    [Serializable]
    public class CodeAsterSettings : ISettings
    {
        private string _asRunExecutable;
        private string _pythonExecutable;
        private string _workDirectory;
        private int _numCPUs;
        private int _memoryMB;
        private int _timeLimitSeconds;
        private string _version;
        private string[] _environmentVariables;

        public string AsRunExecutable
        {
            get { return _asRunExecutable; }
            set { _asRunExecutable = value; }
        }

        public string PythonExecutable
        {
            get { return _pythonExecutable; }
            set { _pythonExecutable = value; }
        }

        public string WorkDirectory
        {
            get { return _workDirectory; }
            set { _workDirectory = value; }
        }

        public int NumCPUs
        {
            get { return _numCPUs; }
            set { _numCPUs = value; }
        }

        public int MemoryMB
        {
            get { return _memoryMB; }
            set { _memoryMB = value; }
        }

        public int TimeLimitSeconds
        {
            get { return _timeLimitSeconds; }
            set { _timeLimitSeconds = value; }
        }

        /// <summary>Code_Aster version understood by as_run, e.g. stable or testing.</summary>
        public string Version
        {
            get { return _version; }
            set { _version = value; }
        }

        /// <summary>KEY=VALUE entries added to the solver process environment.</summary>
        public string[] EnvironmentVariables
        {
            get { return _environmentVariables; }
            set { _environmentVariables = value; }
        }

        public CodeAsterSettings()
        {
            Reset();
        }

        public void CheckValues()
        {
            if (_numCPUs < 1) _numCPUs = 1;
            if (_memoryMB < 256) _memoryMB = 256;
            if (_timeLimitSeconds < 1) _timeLimitSeconds = 3600;
            if (String.IsNullOrWhiteSpace(_version)) _version = "stable";
            if (_environmentVariables == null) _environmentVariables = new string[0];
        }

        public void Clear()
        {
            _asRunExecutable = null;
            _pythonExecutable = null;
            _workDirectory = null;
            _numCPUs = 1;
            _memoryMB = 2048;
            _timeLimitSeconds = 3600;
            _version = "stable";
            _environmentVariables = new string[0];
        }

        public void Reset()
        {
            _asRunExecutable = "as_run";
            _pythonExecutable = "python3";
            _workDirectory = Path.Combine(Path.GetTempPath(), "PrePoMax-CodeAster");
            _numCPUs = Math.Max(1, Environment.ProcessorCount / 2);
            _memoryMB = 4096;
            _timeLimitSeconds = 3600;
            _version = "stable";
            _environmentVariables = new string[0];
            CheckValues();
        }

        public ISettings Get()
        {
            CodeAsterSettings copy = new CodeAsterSettings();
            copy._asRunExecutable = _asRunExecutable;
            copy._pythonExecutable = _pythonExecutable;
            copy._workDirectory = _workDirectory;
            copy._numCPUs = _numCPUs;
            copy._memoryMB = _memoryMB;
            copy._timeLimitSeconds = _timeLimitSeconds;
            copy._version = _version;
            copy._environmentVariables = _environmentVariables == null
                ? new string[0]
                : (string[])_environmentVariables.Clone();
            return copy;
        }

        public void Set(ISettings settings)
        {
            CodeAsterSettings source = settings as CodeAsterSettings;
            if (source == null) throw new ArgumentException("Expected CodeAsterSettings.", "settings");

            _asRunExecutable = source._asRunExecutable;
            _pythonExecutable = source._pythonExecutable;
            _workDirectory = source._workDirectory;
            _numCPUs = source._numCPUs;
            _memoryMB = source._memoryMB;
            _timeLimitSeconds = source._timeLimitSeconds;
            _version = source._version;
            _environmentVariables = source._environmentVariables == null
                ? new string[0]
                : (string[])source._environmentVariables.Clone();
            CheckValues();
        }

        public string[] GetEnvironmentVariables()
        {
            return _environmentVariables == null ? new string[0] : (string[])_environmentVariables.Clone();
        }
    }
}

using System;
using System.ComponentModel;
using System.Drawing.Design;
using CaeGlobals;

namespace PrePoMax.Settings
{
    [Serializable]
    public class ViewCodeAsterSettings : IViewSettings, IReset
    {
        private PrePoMax.CodeAsterSettings _settings;

        [CategoryAttribute("Code_Aster")]
        [OrderedDisplayName(0, 10, "as_run executable")]
        [DescriptionAttribute("Executable or command used to launch Code_Aster studies.")]
        public string AsRunExecutable
        {
            get { return _settings.AsRunExecutable; }
            set { _settings.AsRunExecutable = value; }
        }

        [CategoryAttribute("Code_Aster")]
        [OrderedDisplayName(1, 10, "Catalog Python executable")]
        [DescriptionAttribute("Python environment able to import code_aster.Cata.Commands. This is independent from the solver harness runtime.")]
        public string PythonExecutable
        {
            get { return _settings.PythonExecutable; }
            set { _settings.PythonExecutable = value; }
        }

        [CategoryAttribute("Code_Aster")]
        [OrderedDisplayName(2, 10, "Work directory")]
        [DescriptionAttribute("Default Code_Aster study work directory.")]
        [EditorAttribute(typeof(System.Windows.Forms.Design.FolderNameEditor), typeof(UITypeEditor))]
        public string WorkDirectory
        {
            get { return _settings.WorkDirectory; }
            set { _settings.WorkDirectory = value; }
        }

        [CategoryAttribute("Code_Aster")]
        [OrderedDisplayName(3, 10, "Version")]
        [DescriptionAttribute("Code_Aster version token understood by as_run, for example stable or testing.")]
        public string Version
        {
            get { return _settings.Version; }
            set { _settings.Version = value; }
        }

        [CategoryAttribute("Resources")]
        [OrderedDisplayName(0, 10, "Number of processors")]
        public int NumCPUs
        {
            get { return _settings.NumCPUs; }
            set { _settings.NumCPUs = value; }
        }

        [CategoryAttribute("Resources")]
        [OrderedDisplayName(1, 10, "Memory limit [MB]")]
        public int MemoryMB
        {
            get { return _settings.MemoryMB; }
            set { _settings.MemoryMB = value; }
        }

        [CategoryAttribute("Resources")]
        [OrderedDisplayName(2, 10, "Time limit [s]")]
        public int TimeLimitSeconds
        {
            get { return _settings.TimeLimitSeconds; }
            set { _settings.TimeLimitSeconds = value; }
        }

        [CategoryAttribute("Environment")]
        [OrderedDisplayName(0, 10, "Environment variables")]
        [DescriptionAttribute("KEY=VALUE entries supplied to Code_Aster and catalog discovery.")]
        public string[] EnvironmentVariables
        {
            get { return _settings.EnvironmentVariables; }
            set { _settings.EnvironmentVariables = value; }
        }

        public ViewCodeAsterSettings(PrePoMax.CodeAsterSettings settings)
        {
            _settings = settings;
        }

        public ISettings GetBase()
        {
            return _settings;
        }

        public void Reset()
        {
            _settings.Reset();
        }
    }
}

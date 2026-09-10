using System;
using System.ComponentModel;
using CaeGlobals;

namespace PrePoMax.Settings
{
    [Serializable]
    public class ViewHarnessSettings : IViewSettings, IReset
    {
        private PrePoMax.HarnessSettings _settings;

        [CategoryAttribute("Harness")]
        [OrderedDisplayName(0, 10, "Python executable")]
        [DescriptionAttribute("Python runtime used only to execute the AsterMax solver harness. It can later point to a bundled AsterMax Python runtime and is independent from Code_Aster catalog Python.")]
        public string PythonExecutable
        {
            get { return _settings.PythonExecutable; }
            set { _settings.PythonExecutable = value; }
        }

        public ViewHarnessSettings(PrePoMax.HarnessSettings settings)
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

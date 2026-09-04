using System;
using System.Collections.Generic;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Fail-closed runtime proof that the pinned native VTK control exposes and accepts
    /// the same Legend.ColorSpectrum object used by the Results workspace. This verifies
    /// the native scalar-bar wiring seam without claiming pixel-level semantic equivalence.
    /// </summary>
    public static class NativeScalarBarGate
    {
        public sealed class Report
        {
            public bool ControlFound;
            public bool MethodFound;
            public bool MethodInvoked;
            public bool InternalSpectrumAutomatic;
            public string ControlType;

            public override string ToString()
            {
                return "control=" + ControlFound +
                       ", method=" + MethodFound +
                       ", invoked=" + MethodInvoked +
                       ", automatic=" + InternalSpectrumAutomatic +
                       ", type=" + (ControlType ?? "<null>");
            }
        }

        private static IEnumerable<Control> Walk(Control root)
        {
            if (root == null) yield break;
            foreach (Control child in root.Controls)
            {
                yield return child;
                foreach (Control nested in Walk(child)) yield return nested;
            }
        }

        public static Report Verify(Controller controller)
        {
            if (controller == null) throw new ArgumentNullException("controller");
            if (controller.Form == null) throw new InvalidOperationException("Controller.Form is unavailable.");
            if (controller.Settings == null || controller.Settings.Legend == null || controller.Settings.Legend.ColorSpectrum == null)
                throw new InvalidOperationException("Legend color spectrum is unavailable.");

            Report report = new Report();
            object vtk = null;
            foreach (Control control in Walk(controller.Form))
            {
                Type type = control.GetType();
                if (String.Equals(type.FullName, "vtkControl.vtkControl", StringComparison.Ordinal) ||
                    String.Equals(type.Name, "vtkControl", StringComparison.OrdinalIgnoreCase))
                {
                    vtk = control;
                    report.ControlFound = true;
                    report.ControlType = type.FullName;
                    break;
                }
            }
            if (vtk == null) return report;

            Type vtkType = vtk.GetType();
            MethodInfo setSpectrum = vtkType.GetMethod("SetScalarBarColorSpectrum", BindingFlags.Instance | BindingFlags.Public);
            report.MethodFound = setSpectrum != null;
            if (setSpectrum == null) return report;

            controller.Settings.Legend.ColorSpectrum.MinMaxType = vtkControl.vtkColorSpectrumMinMaxType.Automatic;
            setSpectrum.Invoke(vtk, new object[] { controller.Settings.Legend.ColorSpectrum });
            report.MethodInvoked = true;

            FieldInfo internalSpectrumField = vtkType.GetField("_colorSpectrum", BindingFlags.Instance | BindingFlags.NonPublic);
            if (internalSpectrumField == null) return report;
            object internalSpectrum = internalSpectrumField.GetValue(vtk);
            if (internalSpectrum == null) return report;

            PropertyInfo minMaxType = internalSpectrum.GetType().GetProperty("MinMaxType", BindingFlags.Instance | BindingFlags.Public);
            if (minMaxType == null) return report;
            object value = minMaxType.GetValue(internalSpectrum, null);
            report.InternalSpectrumAutomatic = value != null &&
                String.Equals(value.ToString(), "Automatic", StringComparison.OrdinalIgnoreCase);
            return report;
        }
    }
}

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Fail-closed runtime proof for the pinned native VTK scalar bar.
    /// C8.35 proved the live Results workspace accepts the Legend.ColorSpectrum contract.
    /// C8.36 additionally reads the vtkMaxScalarBarWidget lookup-table range that generates
    /// the native labels and requires it to match the admitted STRESS/MISES Field range.
    /// </summary>
    public static class NativeScalarBarGate
    {
        public sealed class Report
        {
            public bool ControlFound;
            public bool MethodFound;
            public bool MethodInvoked;
            public bool InternalSpectrumAutomatic;
            public bool ScalarBarWidgetFound;
            public bool LookupTableFound;
            public bool LookupTableRangeReadable;
            public bool RangeMatchesField;
            public double NativeRangeMin;
            public double NativeRangeMax;
            public double FieldRangeMin;
            public double FieldRangeMax;
            public string ControlType;
            public string RangeSource;

            public override string ToString()
            {
                return "control=" + ControlFound +
                       ", method=" + MethodFound +
                       ", invoked=" + MethodInvoked +
                       ", automatic=" + InternalSpectrumAutomatic +
                       ", widget=" + ScalarBarWidgetFound +
                       ", lut=" + LookupTableFound +
                       ", readable=" + LookupTableRangeReadable +
                       ", rangeMatchesField=" + RangeMatchesField +
                       ", native=[" + NativeRangeMin.ToString("R", CultureInfo.InvariantCulture) +
                       "," + NativeRangeMax.ToString("R", CultureInfo.InvariantCulture) + "]" +
                       ", field=[" + FieldRangeMin.ToString("R", CultureInfo.InvariantCulture) +
                       "," + FieldRangeMax.ToString("R", CultureInfo.InvariantCulture) + "]" +
                       ", source=" + (RangeSource ?? "<null>") +
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

        private static FieldInfo FindField(Type type, string name)
        {
            while (type != null)
            {
                FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                if (field != null) return field;
                type = type.BaseType;
            }
            return null;
        }

        private static bool NearlyEqual(double observed, double expected)
        {
            double scale = Math.Max(1.0, Math.Max(Math.Abs(observed), Math.Abs(expected)));
            return Math.Abs(observed - expected) <= 1e-8 * scale;
        }

        public static Report Verify(Controller controller, double fieldRangeMin, double fieldRangeMax)
        {
            if (controller == null) throw new ArgumentNullException("controller");
            if (controller.Form == null) throw new InvalidOperationException("Controller.Form is unavailable.");
            if (controller.Settings == null || controller.Settings.Legend == null || controller.Settings.Legend.ColorSpectrum == null)
                throw new InvalidOperationException("Legend color spectrum is unavailable.");
            if (Double.IsNaN(fieldRangeMin) || Double.IsInfinity(fieldRangeMin) ||
                Double.IsNaN(fieldRangeMax) || Double.IsInfinity(fieldRangeMax) || fieldRangeMin > fieldRangeMax)
                throw new ArgumentOutOfRangeException("fieldRangeMin", "Field scalar range is invalid.");

            Report report = new Report();
            report.FieldRangeMin = fieldRangeMin;
            report.FieldRangeMax = fieldRangeMax;
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

            FieldInfo internalSpectrumField = FindField(vtkType, "_colorSpectrum");
            if (internalSpectrumField == null) return report;
            object internalSpectrum = internalSpectrumField.GetValue(vtk);
            if (internalSpectrum == null) return report;

            PropertyInfo minMaxType = internalSpectrum.GetType().GetProperty("MinMaxType", BindingFlags.Instance | BindingFlags.Public);
            if (minMaxType == null) return report;
            object value = minMaxType.GetValue(internalSpectrum, null);
            report.InternalSpectrumAutomatic = value != null &&
                String.Equals(value.ToString(), "Automatic", StringComparison.OrdinalIgnoreCase);

            // The pinned vtkMaxScalarBarWidget.GenerateLabels() reads this exact lookup table's
            // GetTableRange(), therefore this is the numerical source of the displayed labels.
            FieldInfo widgetField = FindField(vtkType, "_scalarBarWidget");
            if (widgetField == null) return report;
            object widget = widgetField.GetValue(vtk);
            report.ScalarBarWidgetFound = widget != null;
            if (widget == null) return report;

            FieldInfo lookupField = FindField(widget.GetType(), "_lookupTable");
            if (lookupField == null) return report;
            object lookupTable = lookupField.GetValue(widget);
            report.LookupTableFound = lookupTable != null;
            if (lookupTable == null) return report;

            MethodInfo getTableRange = lookupTable.GetType().GetMethod("GetTableRange", BindingFlags.Instance | BindingFlags.Public);
            if (getTableRange == null) return report;
            object rawRange = getTableRange.Invoke(lookupTable, null);
            double[] range = rawRange as double[];
            if (range == null || range.Length < 2 ||
                Double.IsNaN(range[0]) || Double.IsInfinity(range[0]) ||
                Double.IsNaN(range[1]) || Double.IsInfinity(range[1])) return report;

            report.LookupTableRangeReadable = true;
            report.NativeRangeMin = range[0];
            report.NativeRangeMax = range[1];
            report.RangeSource = "vtkMaxScalarBarWidget._lookupTable.GetTableRange()";
            report.RangeMatchesField = NearlyEqual(report.NativeRangeMin, fieldRangeMin) &&
                                       NearlyEqual(report.NativeRangeMax, fieldRangeMax);
            return report;
        }
    }
}

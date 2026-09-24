using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private readonly List<int> _c10216ObservedDpi = new List<int>();
        private readonly JArray _c10216DpiObservations = new JArray();
        private bool _c10216DpiInitialized;
        [DllImport("user32.dll", EntryPoint="GetDpiForWindow")]
        private static extern uint C10216NativeWindowDpi(IntPtr window);

        private void C10216InitializeDpiObserver()
        {
            if (_c10216DpiInitialized) return;
            _c10216DpiInitialized = true;
            DpiChanged += (sender, args) => {
                // Framework scaling completes after the event. Never scale the
                // live VTK control a second time or synthesize WM_DPICHANGED.
                if (!IsDisposed && IsHandleCreated)
                    BeginInvoke(new Action(() => C10216CompleteDpiLayout("DpiChanged")));
            };
            BeginInvoke(new Action(() => C10216CompleteDpiLayout("initial")));
        }

        private void C10216CompleteDpiLayout(string cause)
        {
            if (IsDisposed || Disposing) return;
            Rectangle work = Screen.FromControl(this).WorkingArea;
            MinimumSize = new Size(Math.Min(LogicalToDeviceUnits(1040), work.Width),
                                   Math.Min(LogicalToDeviceUnits(680), work.Height));
            if (WindowState == FormWindowState.Normal)
            {
                Size = new Size(Math.Min(Width, work.Width), Math.Min(Height, work.Height));
                Location = new Point(Math.Max(work.Left, Math.Min(Left, work.Right - Width)),
                                     Math.Max(work.Top, Math.Min(Top, work.Bottom - Height)));
            }
            PerformLayout();
            Invalidate(true);
            Update();
            string prefix = "--astermax-dpi-audit=";
            string option = Environment.GetCommandLineArgs().FirstOrDefault(a => a.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
            string directory = option == null ? Environment.GetEnvironmentVariable("ASTERMAX_C1020_AUDIT_DIR") : option.Substring(prefix.Length).Trim('"');
            if (String.IsNullOrWhiteSpace(directory)) return;
            try
            {
                Directory.CreateDirectory(directory);
                int nativeDpi = (int)C10216NativeWindowDpi(Handle);
                Control ribbon = Controls["asterMaxRibbon"];
                bool consistent = nativeDpi == DeviceDpi && nativeDpi > 0;
                bool layout = ribbon != null && Math.Abs(ribbon.Height - LogicalToDeviceUnits(132)) <= 2 &&
                    MinimumSize.Width <= work.Width && MinimumSize.Height <= work.Height &&
                    splitContainer2.Panel1.ClientSize.Width > 0 && splitContainer2.Panel1.ClientSize.Height > 0;
                if (consistent && !_c10216ObservedDpi.Contains(nativeDpi)) _c10216ObservedDpi.Add(nativeDpi);
                _c10216DpiObservations.Add(new JObject {
                    ["cause"] = cause, ["native_window_dpi"] = nativeDpi, ["winforms_device_dpi"] = DeviceDpi,
                    ["native_dpi_matches"] = consistent, ["layout_valid"] = layout,
                    ["ribbon_height_px"] = ribbon == null ? 0 : ribbon.Height,
                    ["expected_ribbon_height_px"] = LogicalToDeviceUnits(132),
                    ["minimum_width_px"] = MinimumSize.Width, ["minimum_height_px"] = MinimumSize.Height,
                    ["work_width_px"] = work.Width, ["work_height_px"] = work.Height
                });
                bool allValid = _c10216DpiObservations.All(x => (bool)x["native_dpi_matches"] && (bool)x["layout_valid"]);
                string status = !allValid ? "FAIL" : _c10216ObservedDpi.Count >= 2 ? "PASS" : "NOT_EXERCISED";
                File.WriteAllText(Path.Combine(directory, "dpi-native-layout.json"), new JObject {
                    ["status"] = status, ["initial_layout_valid"] = allValid,
                    ["real_dpi_transition_observed"] = _c10216ObservedDpi.Count >= 2,
                    ["synthetic_dpi_messages_used"] = false,
                    ["observations"] = _c10216DpiObservations
                }.ToString(Formatting.Indented));
            }
            catch (Exception ex)
            {
                // A user-selected diagnostics path must not crash normal UI use.
                System.Diagnostics.Trace.WriteLine("AsterMax DPI evidence: " + ex);
            }
        }
    }
}

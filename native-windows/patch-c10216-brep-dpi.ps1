param([string]$Root)
$ErrorActionPreference='Stop'
function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $Text=$Text.Replace("`r`n","`n");$Old=$Old.Replace("`r`n","`n");$New=$New.Replace("`r`n","`n")
    if(-not $Text.Contains($Old)){ throw "C10216 anchor missing: $Old" }
    $Text.Replace($Old,$New)
}
# Isolate the modern OCC kernel in packaged Python. Legacy NetGen remains the CAD
# import/STL adapter; only the BREP volume meshing command changes engine.
$path=Join-Path $Root 'PrePoMax/Controller.cs'
$c=Get-Content $path -Raw
$start=$c.IndexOf('        private bool CreateMeshFromBrep(GeometryPart part)')
$end=$c.IndexOf('        private void CreateMeshRefinementFile', $start)
if($start -lt 0 -or $end -lt 0){throw 'BREP method bounds missing'}
$method=$c.Substring($start,$end-$start)
$method=Replace-Required $method '            string executable = Application.StartupPath + Globals.NetGenMesher;' @'
            string executable = Path.Combine(Application.StartupPath, "AsterMaxRuntime", "Python", "python.exe");
            string brepRunner = Path.Combine(Application.StartupPath, "AsterMaxTools", "brep_mesh.py");
            if (!File.Exists(executable) || !File.Exists(brepRunner))
                throw new FileNotFoundException("The packaged Netgen/OCC BREP runtime is missing. Extract the complete AsterMax ZIP.");
'@
$method=Replace-Required $method '            _netgenJob = new NetgenJob(part.Name, executable, argument, settings.WorkDirectory);' @'
            argument = "\"" + brepRunner + "\" " + argument;
            _netgenJob = new NetgenJob(part.Name, executable, argument, settings.WorkDirectory);
'@
$c=$c.Substring(0,$start)+$method+$c.Substring($end)
Set-Content $path $c -Encoding UTF8

# Opt into the .NET Framework 4.8 dynamic per-monitor implementation, rather than
# setting a manifest DPI flag which overrides WinForms configuration.
$path=Join-Path $Root 'PrePoMax/App.config'
$c=Get-Content $path -Raw
$c=Replace-Required $c '</configuration>' @'
  <System.Windows.Forms.ApplicationConfigurationSection>
    <add key="DpiAwareness" value="PerMonitorV2" />
  </System.Windows.Forms.ApplicationConfigurationSection>
</configuration>
'@
Set-Content $path $c -Encoding UTF8
$manifest=@'
<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <assemblyIdentity version="1.0.0.0" name="AsterMax.Mechanical" />
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
    <requestedExecutionLevel level="asInvoker" uiAccess="false" />
  </requestedPrivileges></security></trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application>
    <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" />
  </application></compatibility>
</assembly>
'@
Set-Content (Join-Path $Root 'PrePoMax/astermax.manifest') $manifest -Encoding UTF8
$path=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$c=Get-Content $path -Raw
$c=Replace-Required $c '<ApplicationIcon>main.ico</ApplicationIcon>' '<ApplicationIcon>main.ico</ApplicationIcon><ApplicationManifest>astermax.manifest</ApplicationManifest>'
Set-Content $path $c -Encoding UTF8
$path=Join-Path $Root 'PrePoMax/Program.cs'
$c=Get-Content $path -Raw
$c=Replace-Required $c 'Application.EnableVisualStyles();' ''
$c=Replace-Required $c "static void Main(string[] args)`n        {" "static void Main(string[] args)`n        {`n            Application.EnableVisualStyles();"
Set-Content $path $c -Encoding UTF8

# The ribbon is constructed after Shown; its initial pixel dimensions otherwise
# bypass the designer's initial scaling. Fonts remain in points (no double scale).
$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$c=Get-Content $path -Raw
$c=[regex]::Replace($c,'(\b(?:Height|Width) = )(\d+)(\s*[,;])','$1LogicalToDeviceUnits($2)$3')
$c=Replace-Required $c 'Width = text.Length > 14 ? 132 : 112,' 'Width = LogicalToDeviceUnits(text.Length > 14 ? 132 : 112),'
$c=Replace-Required $c 'MinimumSize = new Size(1040, 680);' 'MinimumSize = new Size(LogicalToDeviceUnits(1040), LogicalToDeviceUnits(680));'
$c=Replace-Required $c '                WrapContents = false,' "                WrapContents = false,`n                AutoScroll = true,"
Set-Content $path $c -Encoding UTF8

# Assert real process awareness and retain the separate physical-monitor test.
$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceCrossChecks.cs'
$c=Get-Content $path -Raw
$c=Replace-Required $c '                int deviceDpiBefore = DeviceDpi;' @'
                bool perMonitorV2 = C10216DpiContextsEqual(C10216GetWindowDpiAwarenessContext(Handle), new IntPtr(-4));
                if (!perMonitorV2) throw new InvalidOperationException("The native window did not enter PerMonitorV2 DPI awareness.");
                int deviceDpiBefore = DeviceDpi;
'@
$c=Replace-Required $c '                    ["device_dpi_before"] = deviceDpiBefore,' @'
                    ["per_monitor_v2_verified"] = perMonitorV2,
                    ["device_dpi_before"] = deviceDpiBefore,
'@
$c=Replace-Required $c '        private void C1020AttachCrossCuttingToSession(string directory)' @'
        [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint="GetWindowDpiAwarenessContext")]
        private static extern IntPtr C10216GetWindowDpiAwarenessContext(IntPtr window);
        [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint="AreDpiAwarenessContextsEqual")]
        [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
        private static extern bool C10216DpiContextsEqual(IntPtr left, IntPtr right);

        private void C1020AttachCrossCuttingToSession(string directory)
'@
Set-Content $path $c -Encoding UTF8

# An STL fallback must not close the new BREP repair gate.
$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$c=Get-Content $path -Raw
$c=Replace-Required $c '            C10215AssignGeneratedMesh(model);' @'
            if (_controller.AsterMaxLastMeshRoute != "BREP" || _controller.AsterMaxLastBrepExitCode != 0)
                throw new InvalidOperationException("Direct BREP meshing failed; STL fallback does not satisfy the BREP repair gate.");
            C10215AssignGeneratedMesh(model);
'@
Set-Content $path $c -Encoding UTF8
Write-Host 'C10216 native OCC BREP adapter and PerMonitorV2 configuration applied.'

param([string]$Root)
$ErrorActionPreference = 'Stop'

function Replace-IfPresent([string]$Rel,[string]$Old,[string]$New){
  $p = Join-Path $Root $Rel
  if(!(Test-Path $p)){ return }
  $t = Get-Content $p -Raw
  if($t.Contains($Old)){
    $t = $t.Replace($Old,$New)
    Set-Content $p $t -Encoding UTF8
  }
}

# Splash: remove the legacy product and CalculiX identity from startup.
$splash = Join-Path $Root 'PrePoMax/Forms/FrmSplash.Designer.cs'
$st = Get-Content $splash -Raw
$st = $st.Replace('this.labProgramName.Text = "PrePoMax v0.0.0.0";', 'this.labProgramName.Text = "AsterMax Mechanical";')
$st = [regex]::Replace($st, 'this\.labHelp\.Text\s*=\s*"PrePoMax is a graphical pre and post-processor for the free CalculiX FEM solver o"\s*\+\s*\r?\n\s*"n Windows platform\.";', 'this.labHelp.Text = "AsterMax Mechanical — native CAE pre/post environment for Code_Aster workflows.";', [System.Text.RegularExpressions.RegexOptions]::Multiline)
$st = $st.Replace('this.panel1.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("panel1.BackgroundImage")));', 'this.panel1.BackgroundImage = null; this.panel1.BackColor = System.Drawing.Color.FromArgb(0,102,204);')
$st = $st.Replace('this.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("$this.BackgroundImage")));', 'this.BackgroundImage = null;')
Set-Content $splash $st -Encoding UTF8

# Advisor/help strings visible in normal workflows.
Replace-IfPresent 'PrePoMax/Forms/00_Advisor/AdvisorCreator.cs' 'The geometry can be imported into PrePoMax from other CAD programs using .stp/.step or .stl file formats.' 'Geometry can be imported into AsterMax Mechanical from CAD programs using .stp/.step or .stl file formats.'
Replace-IfPresent 'PrePoMax/Forms/00_Advisor/AdvisorCreator.cs' 'to perform any type of analysis in the PrePoMax.' 'to perform an analysis in AsterMax Mechanical.'
Replace-IfPresent 'PrePoMax/Forms/51_Settings/ViewGeneralSettings.cs' 'Save the results in the PrePoMax .pmx file.' 'Save the results in the AsterMax project .pmx file.'

# Replace only user-visible labels and filters, never namespaces/types.
Get-ChildItem (Join-Path $Root 'PrePoMax') -Recurse -Filter '*.cs' | ForEach-Object {
  $p = $_.FullName
  $t = Get-Content $p -Raw
  $before = $t
  $t = $t.Replace('"PrePoMax files', '"AsterMax project files')
  $t = $t.Replace('|PrePoMax files|', '|AsterMax project files|')
  $t = $t.Replace('|PrePoMax history|', '|AsterMax history|')
  $t = $t.Replace('previous PrePoMax session', 'previous AsterMax session')
  $t = $t.Replace('Open the corresponding PrePoMax model', 'Open the corresponding AsterMax model')
  $t = $t.Replace('To run PrePoMax', 'To run AsterMax Mechanical')
  if($t -ne $before){ Set-Content $p $t -Encoding UTF8 }
}

# Home page should belong to the AsterMax project.
Replace-IfPresent 'PrePoMax/Globals.cs' 'public static string HomePage = "https://prepomax.fs.um.si/";' 'public static string HomePage = "https://github.com/MedinaParra/AsterMax-Ubuntu";'

Write-Host 'AsterMax visible branding cleanup applied.' -ForegroundColor Green

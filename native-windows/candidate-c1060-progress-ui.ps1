param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$pre=Join-Path $Root 'PrePoMax'
if(-not(Test-Path $pre)){throw "PrePoMax root missing: $pre"}
$target=Join-Path $pre 'AsterMaxProgressDialog.cs'
@'
using System;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;

namespace PrePoMax
{
    internal sealed class AsterMaxProgressSnapshot
    {
        public string Phase { get; set; }
        public string Detail { get; set; }
        public int? Percent { get; set; }
        public TimeSpan? Remaining { get; set; }
        public bool CanCancel { get; set; }
    }

    internal sealed class AsterMaxProgressDialog : Form
    {
        private readonly Label _phase = new Label();
        private readonly Label _detail = new Label();
        private readonly Label _elapsed = new Label();
        private readonly Label _remaining = new Label();
        private readonly ProgressBar _bar = new ProgressBar();
        private readonly Button _cancel = new Button();
        private readonly Button _detailsButton = new Button();
        private readonly TextBox _details = new TextBox();
        private readonly Stopwatch _clock = Stopwatch.StartNew();
        private readonly Timer _uiTimer = new Timer();
        public event EventHandler CancelRequested;

        public AsterMaxProgressDialog(string title)
        {
            Text=title; Width=590; Height=245; MinimumSize=new Size(500,245);
            StartPosition=FormStartPosition.CenterParent; FormBorderStyle=FormBorderStyle.FixedDialog;
            MaximizeBox=false; MinimizeBox=false; ShowInTaskbar=false;
            _phase.SetBounds(18,18,540,24); _phase.Font=new Font(Font,FontStyle.Bold);
            _detail.SetBounds(18,48,540,22);
            _bar.SetBounds(18,78,540,24); _bar.Minimum=0; _bar.Maximum=100; _bar.Style=ProgressBarStyle.Marquee;
            _elapsed.SetBounds(18,112,250,20); _remaining.SetBounds(300,112,258,20); _remaining.TextAlign=ContentAlignment.MiddleRight;
            _detailsButton.SetBounds(18,145,90,28); _detailsButton.Text="Detalles";
            _cancel.SetBounds(468,145,90,28); _cancel.Text="Cancelar"; _cancel.Enabled=false;
            _details.SetBounds(18,182,540,120); _details.Multiline=true; _details.ScrollBars=ScrollBars.Vertical; _details.ReadOnly=true; _details.Visible=false;
            Controls.AddRange(new Control[]{_phase,_detail,_bar,_elapsed,_remaining,_detailsButton,_cancel,_details});
            _detailsButton.Click+=(s,e)=>ToggleDetails();
            _cancel.Click+=(s,e)=>CancelRequested?.Invoke(this,EventArgs.Empty);
            _uiTimer.Interval=250; _uiTimer.Tick+=(s,e)=>_elapsed.Text="Transcurrido: "+Format(_clock.Elapsed); _uiTimer.Start();
            FormClosing+=(s,e)=>{ if(DialogResult==DialogResult.None){ e.Cancel=true; } };
        }
        private static string Format(TimeSpan t){return t.TotalHours>=1?t.ToString(@"hh\:mm\:ss"):t.ToString(@"mm\:ss");}
        private void ToggleDetails(){_details.Visible=!_details.Visible; Height=_details.Visible?355:245; _detailsButton.Text=_details.Visible?"Ocultar":"Detalles";}
        public void AppendDetail(string line){ if(string.IsNullOrWhiteSpace(line))return; Ui(()=>{_details.AppendText(line+Environment.NewLine);}); }
        public void Report(AsterMaxProgressSnapshot s)
        {
            if(s==null)return;
            Ui(()=>{
                _phase.Text=s.Phase??"Procesando..."; _detail.Text=s.Detail??String.Empty; _cancel.Enabled=s.CanCancel;
                if(s.Percent.HasValue){_bar.Style=ProgressBarStyle.Continuous; _bar.Value=Math.Max(0,Math.Min(100,s.Percent.Value));}
                else {_bar.Style=ProgressBarStyle.Marquee;}
                _remaining.Text=s.Remaining.HasValue?"Restante estimado: "+Format(s.Remaining.Value):"Tiempo restante: calculando...";
            });
        }
        public void Complete(string detail)
        {
            Ui(()=>{_bar.Style=ProgressBarStyle.Continuous;_bar.Value=100;_phase.Text="Completado";_detail.Text=detail??String.Empty;_remaining.Text="";_cancel.Enabled=false;DialogResult=DialogResult.OK;Close();});
        }
        public void Fail(string state,string detail)
        {
            Ui(()=>{_phase.Text=state??"FALLÓ";_detail.Text=detail??String.Empty;_bar.Style=ProgressBarStyle.Continuous;_cancel.Enabled=false;_uiTimer.Stop();});
        }
        private void Ui(Action a){if(IsDisposed)return;if(InvokeRequired)BeginInvoke(a);else a();}
    }
}
'@ | Set-Content $target -Encoding UTF8

$proj=Join-Path $pre 'PrePoMax.csproj'
if(-not(Test-Path $proj)){throw 'PrePoMax.csproj missing'}
$p=Get-Content $proj -Raw
$compileLine='    <Compile Include="AsterMaxProgressDialog.cs" />'
if(-not $p.Contains('AsterMaxProgressDialog.cs')){
  $anchor='<Compile Include="AsterMaxLocalization.cs" />'
  if($p.Contains($anchor)){$p=$p.Replace($anchor,$anchor+"`r`n"+$compileLine)}
  else {
    $anchor='<Compile Include="AsterMaxSpanishChile.cs" />'
    if(-not $p.Contains($anchor)){throw 'No safe Compile anchor found for progress dialog'}
    $p=$p.Replace($anchor,$anchor+"`r`n"+$compileLine)
  }
  Set-Content $proj $p -Encoding UTF8
}
Write-Host 'C10.60 progress UI foundation applied.'
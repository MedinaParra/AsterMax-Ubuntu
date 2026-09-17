using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace PrePoMax
{
    internal sealed partial class AsterMaxResultsViewportForm
    {
        public event Action<string> ResultFieldChanged;
        public Action ValidateModel;
        private bool _axRendering;
        public string LastRenderError { get; private set; }
        public int RenderRevision { get; private set; }
        public string SelectedResultField { get { return (string)_field.SelectedItem; } }
        public bool ContoursVisible { get { return _showContours.Checked; } }
        public bool DeformationVisible { get { return _showDeformed.Checked; } }
        public bool MeshEdgesVisible { get { return _showEdges.Checked; } }

        public Control DetachResultDetails()
        {
            var details = _legend.Parent;
            Controls.Remove(details);
            _legend.Visible = false; // The native VTK scalar bar remains the color authority.
            details.Dock = DockStyle.Top;
            details.Height = 430;
            return details;
        }

        public void SelectResultField(string field)
        {
            if (!_field.Items.Contains(field)) throw new ArgumentException("Result field is unavailable: " + field);
            if (SelectedResultField != field) _field.SelectedItem = field;
            else if (_view == null) RenderScene();
        }

        public void ExecuteResultCommand(string command)
        {
            ValidateModel?.Invoke();
            switch (command)
            {
                case "Contours": _showContours.Checked = !_showContours.Checked; return;
                case "Deformed": _showDeformed.Checked = !_showDeformed.Checked; return;
                case "Edges": _showEdges.Checked = !_showEdges.Checked; return;
            }
            if (_view == null) RenderScene();
            if (_view == null) throw new InvalidOperationException("The result viewport is unavailable: " + LastRenderError);
            switch (command)
            {
                case "Fit": _view.AdjustCameraDistanceAndClipping(); break;
                case "Front": _view.SetFrontBackView(false, true); break;
                case "Top": _view.SetTopBottomView(false, true); break;
                case "Right": _view.SetLeftRightView(false, false); break;
                case "Isometric": _view.SetIsometricView(false, true); break;
                default: throw new ArgumentException("Unknown result command: " + command);
            }
        }
    }

    public partial class FrmMain
    {
        private AsterMaxResultsViewportForm _axEmbeddedResults;
        private AsterMaxResultsBundle _axEmbeddedBundle;
        private Panel _axResultDetailsHost;
        private Control _axResultDetails;
        private TextBox _axSolutionInformation;
        private bool _axSelectingResult;
        private bool _axRefreshingResults;

        private void InitializeAsterMaxIntegratedResults()
        {
            _modelTree.AsterMaxResultRequested += field => InvokeAsterMaxCommand("Result selection", () => ShowAsterMaxIntegratedResult(field));
            _modelTree.AsterMaxModelViewRequested += ShowAsterMaxModelWorkspace;
            _modelTree.AsterMaxModelTreeChanged += RefreshAsterMaxResultAvailability;
            Disposed += (s,e) => ResetAsterMaxIntegratedResults();
        }

        private void RefreshAsterMaxResultAvailability()
        {
            if (_axRefreshingResults || _modelTree == null) return;
            _axRefreshingResults = true;
            try
            {
                if (_asterMaxLoadedResults == null)
                {
                    _modelTree.SetAsterMaxResultFields(new string[0], "Not solved", false);
                    return;
                }
                try
                {
                    _asterMaxLoadedResults.RequireCurrentModel(_controller == null ? null : _controller.Model);
                    _modelTree.SetAsterMaxResultFields(_asterMaxLoadedResults.AvailableFields(), "Current", true);
                }
                catch (Exception ex)
                {
                    ShowAsterMaxModelWorkspace();
                    _modelTree.SetAsterMaxResultFields(_asterMaxLoadedResults.AvailableFields(), "Stale - solve again", false);
                    tsslState.Text = "Results are out of date: " + ex.Message;
                }
            }
            finally { _axRefreshingResults = false; }
        }

        private void ShowAsterMaxIntegratedResult(string field)
        {
            if (_axSelectingResult) return;
            _axSelectingResult = true;
            try
            {
                if (field == "__information__") { ShowAsterMaxSolutionInformation(); return; }
                if (_asterMaxLoadedResults == null)
                {
                    using (var dialog = new OpenFileDialog { Title="Load Code_Aster results for this model", Filter="AsterMax Results (*.json)|*.json" })
                    {
                        if (dialog.ShowDialog(this) != DialogResult.OK) return;
                        var candidate = AsterMaxResultsBundle.Load(dialog.FileName);
                        candidate.RequireCurrentModel(_controller == null ? null : _controller.Model);
                        _asterMaxLoadedResults = candidate;
                    }
                }
                _asterMaxLoadedResults.RequireCurrentModel(_controller == null ? null : _controller.Model);
                if (_axEmbeddedResults == null || _axEmbeddedResults.IsDisposed || !Object.ReferenceEquals(_axEmbeddedBundle, _asterMaxLoadedResults))
                {
                    DisposeAsterMaxResultView();
                    var bundle = _asterMaxLoadedResults;
                    _axEmbeddedBundle = bundle;
                    _axEmbeddedResults = new AsterMaxResultsViewportForm(bundle) {
                        Name="asterMaxIntegratedResults", TopLevel=false, FormBorderStyle=FormBorderStyle.None,
                        ShowInTaskbar=false, Dock=DockStyle.Fill };
                    _axEmbeddedResults.ValidateModel = () => bundle.RequireCurrentModel(_controller == null ? null : _controller.Model);
                    _axEmbeddedResults.ResultFieldChanged += selected => {
                        if (!_axSelectingResult) _modelTree.SelectAsterMaxResultField(selected);
                    };
                    splitContainer2.Panel1.Controls.Add(_axEmbeddedResults);
                    _axResultDetails = _axEmbeddedResults.DetachResultDetails();
                    _axResultDetailsHost = new Panel { Name="asterMaxResultDetails", Dock=DockStyle.Bottom, Height=280, AutoScroll=true, BackColor=Color.White };
                    _axResultDetailsHost.Controls.Add(_axResultDetails);
                    splitContainer1.Panel1.Controls.Add(_axResultDetailsHost);
                    _axResultDetailsHost.SendToBack();
                    _modelTree.BringToFront();
                }
                if (_axSolutionInformation != null) _axSolutionInformation.Hide();
                panelControl.Hide();
                _axEmbeddedResults.Show();
                _axEmbeddedResults.BringToFront();
                _axResultDetailsHost.Show();
                _axEmbeddedResults.SelectResultField(String.IsNullOrEmpty(field) ? _axEmbeddedResults.SelectedResultField : field);
                if (_axEmbeddedResults.LastRenderError != null) throw new InvalidOperationException(_axEmbeddedResults.LastRenderError);
                RefreshAsterMaxResultAvailability();
                _modelTree.RefreshAsterMaxOutline();
                _modelTree.SelectAsterMaxResultField(_axEmbeddedResults.SelectedResultField);
                var ribbon = Controls["asterMaxRibbon"] as TabControl;
                if (ribbon != null) foreach (TabPage page in ribbon.TabPages) if (page.Text == "Results") ribbon.SelectedTab = page;
                tsslState.Text = "Results: " + _axEmbeddedResults.SelectedResultField;
            }
            catch
            {
                ShowAsterMaxModelWorkspace();
                RefreshAsterMaxResultAvailability();
                throw;
            }
            finally { _axSelectingResult = false; }
        }

        private void ShowAsterMaxSolutionInformation()
        {
            ShowAsterMaxModelWorkspace();
            if (_axSolutionInformation == null)
            {
                _axSolutionInformation = new TextBox { Name="asterMaxSolutionInformation", Dock=DockStyle.Fill,
                    Multiline=true, ReadOnly=true, ScrollBars=ScrollBars.Both, Font=new Font("Consolas",10), BackColor=Color.White };
                splitContainer2.Panel1.Controls.Add(_axSolutionInformation);
            }
            string text = "Solution Information\r\n\r\n";
            if (_asterMaxSolveTransaction != null)
            {
                text += _asterMaxSolveTransaction.State + "\r\n" + _asterMaxSolveTransaction.Message + "\r\n\r\n";
                text += "Workspace: " + _asterMaxSolveTransaction.Workspace + "\r\n";
                if (File.Exists(_asterMaxSolveTransaction.MessFile))
                    text += String.Join("\r\n", File.ReadLines(_asterMaxSolveTransaction.MessFile).Reverse().Take(100).Reverse());
            }
            else text += "No solver run recorded in this session.\r\n";
            if (_asterMaxLoadedResults != null) text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;
            _axSolutionInformation.Text = text;
            panelControl.Hide();
            _axSolutionInformation.Show();
            _axSolutionInformation.BringToFront();
        }

        private void ShowAsterMaxModelWorkspace()
        {
            if (_axEmbeddedResults != null && !_axEmbeddedResults.IsDisposed) _axEmbeddedResults.Hide();
            if (_axResultDetailsHost != null) _axResultDetailsHost.Hide();
            if (_axSolutionInformation != null) _axSolutionInformation.Hide();
            if (panelControl != null && !panelControl.IsDisposed) panelControl.Show();
        }

        private void DisposeAsterMaxResultView()
        {
            if (_axEmbeddedResults != null) { _axEmbeddedResults.Dispose(); _axEmbeddedResults=null; }
            if (_axResultDetailsHost != null) { _axResultDetailsHost.Dispose(); _axResultDetailsHost=null; }
            _axResultDetails=null;
            _axEmbeddedBundle=null;
        }

        private void ResetAsterMaxIntegratedResults()
        {
            ShowAsterMaxModelWorkspace();
            DisposeAsterMaxResultView();
            _asterMaxLoadedResults=null;
            _asterMaxSolveTransaction=null;
            if (_axSolutionInformation != null) { _axSolutionInformation.Dispose(); _axSolutionInformation=null; }
            if (_modelTree != null && !_modelTree.IsDisposed) _modelTree.SetAsterMaxResultFields(new string[0], "Not solved", false);
        }

        private bool RouteAsterMaxIntegratedCommand(string caption)
        {
            if (caption == "Results Explorer" || caption == "FEA Viewport") { ShowAsterMaxIntegratedResult(null); return true; }
            bool resultOnly = caption == "Contours" || caption == "Deformed";
            bool camera = new[]{"Fit","Front","Top","Right","Isometric","Edges"}.Contains(caption);
            if (resultOnly && (_axEmbeddedResults == null || !_axEmbeddedResults.Visible)) ShowAsterMaxIntegratedResult(null);
            if ((resultOnly || camera) && _axEmbeddedResults != null && _axEmbeddedResults.Visible)
            {
                _axEmbeddedResults.ExecuteResultCommand(caption);
                return true;
            }
            if (resultOnly) return true; // Loading was cancelled; do not invoke the inherited result command.
            if (!camera && caption != "Result selection" && caption != "Save" && caption != "Auditoria") ShowAsterMaxModelWorkspace();
            return false;
        }
    }
}

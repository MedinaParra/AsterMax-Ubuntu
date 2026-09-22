param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.9 diagnostics anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$a=Get-Content $auditPath -Raw

$signature='        private void C1020RequestAuditExit(string directory, int exitCode)'
$helper=@'
        private void C10209TraceShutdown(string directory, string eventName, FormClosingEventArgs closingArgs = null)
        {
            if (String.IsNullOrWhiteSpace(directory)) return;
            try
            {
                int runningJobs = 0;
                if (_controller != null && _controller.Jobs != null)
                    foreach (var entry in _controller.Jobs)
                        if (entry.Value != null && String.Equals(entry.Value.JobStatus.ToString(), "Running", StringComparison.OrdinalIgnoreCase))
                            runningJobs++;

                string forms = String.Join(";",
                    Application.OpenForms.Cast<Form>().Select(form =>
                        (form.Name ?? "") + ":" + (form.Text ?? "").Replace("|", "/") +
                        ":visible=" + form.Visible + ":modal=" + form.Modal + ":enabled=" + form.Enabled));

                string line = String.Join("|", new [] {
                    DateTime.UtcNow.ToString("O"),
                    eventName,
                    "thread=" + System.Threading.Thread.CurrentThread.ManagedThreadId,
                    "invoke_required=" + InvokeRequired,
                    "audit_mode=" + _asterMaxUiAuditMode,
                    "exit_code=" + Environment.ExitCode,
                    "status=" + (tsslState == null ? "<null>" : (tsslState.Text ?? "").Replace("|", "/")),
                    "ready=" + (Globals.ReadyText ?? "").Replace("|", "/"),
                    "model_changed=" + (_controller == null ? "<null>" : _controller.ModelChanged.ToString()),
                    "saving_file=" + (_controller == null ? "<null>" : _controller.SavingFile.ToString()),
                    "running_jobs=" + runningJobs,
                    "solve_in_progress=" + _asterMaxSolveInProgress,
                    "solve_state=" + (_asterMaxSolveTransaction == null ? "<null>" : _asterMaxSolveTransaction.State.ToString()),
                    "solve_ui_thread=" + _asterMaxSolveUiThreadId,
                    "solve_worker_thread=" + _asterMaxSolveWorkerThreadId,
                    "vtk_present=" + (_vtk != null),
                    "results_present=" + (_axEmbeddedResults != null),
                    "results_visible=" + (_axEmbeddedResults != null && _axEmbeddedResults.Visible),
                    "active_form=" + (Form.ActiveForm == null ? "<null>" : (Form.ActiveForm.Text ?? "").Replace("|", "/")),
                    "closing_cancel=" + (closingArgs == null ? "<null>" : closingArgs.Cancel.ToString()),
                    "close_reason=" + (closingArgs == null ? "<null>" : closingArgs.CloseReason.ToString()),
                    "forms=" + forms
                });
                File.AppendAllText(Path.Combine(directory, "audit-shutdown-trace.log"), line + Environment.NewLine);
            }
            catch (Exception ex)
            {
                try { File.AppendAllText(Path.Combine(directory, "audit-shutdown-trace-errors.log"), ex + Environment.NewLine); }
                catch { }
            }
        }

'@
$a=Replace-Required $a $signature ($helper+$signature)

$a=Replace-Required $a '        {
            try
            {
                File.WriteAllText(Path.Combine(directory, "audit-exit-request.json"),' '        {
            C10209TraceShutdown(directory, "C1020RequestAuditExit.enter");
            try
            {
                File.WriteAllText(Path.Combine(directory, "audit-exit-request.json"),'

$a=Replace-Required $a '            Environment.ExitCode = exitCode;
            BeginInvoke(new Action(() =>
            {
                try
                {
                    _asterMaxUiAuditMode = false;
                    Close();' '            Environment.ExitCode = exitCode;
            C10209TraceShutdown(directory, "C1020RequestAuditExit.before_begininvoke");
            FormClosed += (sender,args) => C10209TraceShutdown(directory, "FormClosed");
            Application.ApplicationExit += (sender,args) => C10209TraceShutdown(directory, "ApplicationExit");
            BeginInvoke(new Action(() =>
            {
                C10209TraceShutdown(directory, "C1020RequestAuditExit.begininvoke_delegate.enter");
                try
                {
                    _asterMaxUiAuditMode = false;
                    C10209TraceShutdown(directory, "C1020RequestAuditExit.before_close");
                    Close();
                    C10209TraceShutdown(directory, "C1020RequestAuditExit.after_close_return");'

$a=Replace-Required $a '                    Application.ExitThread();
                }
            }));
        }' '                    Application.ExitThread();
                }
                finally
                {
                    C10209TraceShutdown(directory, "C1020RequestAuditExit.begininvoke_delegate.exit");
                }
            }));
            C10209TraceShutdown(directory, "C1020RequestAuditExit.exit");
        }'
Set-Content $auditPath $a -Encoding UTF8

$mainPath=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$m=Get-Content $mainPath -Raw

$m=Replace-Required $m '        private async void FrmMain_FormClosing(object sender, FormClosingEventArgs e)
        {
            try' '        private async void FrmMain_FormClosing(object sender, FormClosingEventArgs e)
        {
            string c10209AuditDirectory = AsterMaxC1020WorkflowDirectoryFromCommandLine();
            C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.enter", e);
            try'

$m=Replace-Required $m '                if (tsslState.Text != Globals.ReadyText)
                {
                    response = MessageBoxes.ShowWarningQuestion("There is a task running. Close anyway?");' '                if (tsslState.Text != Globals.ReadyText)
                {
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.task_running_prompt.before", e);
                    response = MessageBoxes.ShowWarningQuestion("There is a task running. Close anyway?");
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.task_running_prompt.after_" + response, e);'

$m=Replace-Required $m '                else if (_controller.ModelChanged)
                {
                    response = MessageBox.Show("Save file before closing?",' '                else if (_controller.ModelChanged)
                {
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.model_changed_prompt.before", e);
                    response = MessageBox.Show("Save file before closing?",'

$m=Replace-Required $m '                                               MessageBoxIcon.Warning);
                    if (response == DialogResult.Yes)' '                                               MessageBoxIcon.Warning);
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.model_changed_prompt.after_" + response, e);
                    if (response == DialogResult.Yes)'

$m=Replace-Required $m '                if (e.Cancel == false && _controller != null)
                {
                    _controller.Settings.General.SaveFormSize(this);' '                if (e.Cancel == false && _controller != null)
                {
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.cleanup.enter", e);
                    _controller.Settings.General.SaveFormSize(this);'

$m=Replace-Required $m '                    _vtk.Clear();
                    _vtk.Dispose();
                    _vtk = null;' '                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.vtk_clear.before", e);
                    _vtk.Clear();
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.vtk_clear.after", e);
                    _vtk.Dispose();
                    _vtk = null;
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.vtk_dispose.after", e);
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.cleanup.exit", e);'

$m=Replace-Required $m '            catch
            { }
        }
        private void FrmMain_Move' '            catch (Exception ex)
            {
                C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.exception_" + ex.GetType().FullName, e);
            }
            finally
            {
                C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.exit", e);
            }
        }
        private void FrmMain_Move'

Set-Content $mainPath $m -Encoding UTF8
Write-Host 'C10.20.9 audit shutdown diagnostics applied without changing close policy.' -ForegroundColor Green

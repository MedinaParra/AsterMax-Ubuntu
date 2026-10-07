param(
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [switch]$ExpectBlockedBaseline
)
$ErrorActionPreference='Stop'
$path=Join-Path $BuildRoot 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$source=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")
$start=$source.IndexOf('            var monotonic=System.Diagnostics.Stopwatch.StartNew();')
if($start -lt 0){throw 'Generated native mesh wait block not found.'}
$end=$source.IndexOf('            bool deadlineExpired=!terminalObserved;',$start)
if($start -lt 0 -or $end -le $start){throw 'Generated native mesh wait block not found.'}
# Execute the actual generated product wait with a short test deadline. Its UI
# callback must be serviced by the calling dispatcher before import can finish.
# This is a dispatcher regression, not native meshing or Windows FEA certification.
$wait=$source.Substring($start,$end-$start).Replace('180000','150')
$harness=@'
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

public sealed class MeshAuditDispatcher : SynchronizationContext
{
    private readonly ConcurrentQueue<Action> queue = new ConcurrentQueue<Action>();
    public override void Post(SendOrPostCallback callback, object state)
    {
        queue.Enqueue(() => callback(state));
    }
    public void PumpOne()
    {
        Action action;
        if (queue.TryDequeue(out action)) action();
    }
}

public sealed class MeshAuditControllerProbe
{
    public readonly ManualResetEventSlim Terminal = new ManualResetEventSlim(false);
    public bool AsterMaxWaitMeshAudit(int milliseconds) { return Terminal.Wait(milliseconds); }
}

public sealed class MeshAuditWaitProbe
{
    private readonly MeshAuditControllerProbe _controller = new MeshAuditControllerProbe();
    private bool working = true;
    private readonly bool deliverImport;
    private readonly MeshAuditDispatcher dispatcher;
    private readonly int ownerThread;
    public MeshAuditWaitProbe(MeshAuditDispatcher dispatcher, bool deliverImport)
    {
        this.dispatcher = dispatcher;
        this.deliverImport = deliverImport;
        ownerThread = Thread.CurrentThread.ManagedThreadId;
    }
    private bool IsStateWorking() { return working; }
    private void C10208ClickRibbonButton(string tab, string caption)
    {
        if (deliverImport) dispatcher.Post(_ => {
            working = false;
            _controller.Terminal.Set();
        }, null);
    }
    private static class Application
    {
        public static void DoEvents()
        {
            ((MeshAuditDispatcher)SynchronizationContext.Current).PumpOne();
        }
    }
    public async Task<bool> ExecuteGeneratedWait()
    {
__GENERATED_WAIT__
        return terminalObserved && !working && Thread.CurrentThread.ManagedThreadId == ownerThread;
    }
    public static bool Run(bool deliverImport)
    {
        SynchronizationContext previous = SynchronizationContext.Current;
        var dispatcher = new MeshAuditDispatcher();
        SynchronizationContext.SetSynchronizationContext(dispatcher);
        try
        {
            var probe = new MeshAuditWaitProbe(dispatcher, deliverImport);
            Task<bool> task = probe.ExecuteGeneratedWait();
            var watch = Stopwatch.StartNew();
            while (!task.IsCompleted && watch.ElapsedMilliseconds < 2000)
            {
                dispatcher.PumpOne();
                Thread.Sleep(1);
            }
            if (!task.IsCompleted) throw new TimeoutException("Generated wait never completed.");
            return task.GetAwaiter().GetResult();
        }
        finally { SynchronizationContext.SetSynchronizationContext(previous); }
    }
}
'@
$harness=$harness.Replace('__GENERATED_WAIT__',$wait)
Add-Type -TypeDefinition $harness -IgnoreWarnings -WarningAction SilentlyContinue
$import=[MeshAuditWaitProbe]::Run($true)
if($ExpectBlockedBaseline){
    if($import){throw 'Baseline unexpectedly completed the UI-dependent import.'}
    Write-Host 'PASS: reproduced baseline dispatcher blockage; terminal wait expired before UI import.'
}else{
    if(-not $import){throw 'UI-dependent import could not complete through the generated wait.'}
    Write-Host 'PASS: generated mesh wait services UI import and resumes on the owning thread.'
}
if([MeshAuditWaitProbe]::Run($false)){throw 'Missing terminal signal was incorrectly admitted.'}
Write-Host 'PASS: missing terminal signal remains a failure within the deadline.'

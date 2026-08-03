namespace AsterMax.MechanicalGui;

internal static class Program
{
    private static bool _smokeTest;
    private static string CrashDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AsterMax",
        "crashes");

    [STAThread]
    private static int Main(string[] args)
    {
        _smokeTest = args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase));
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, eventArgs) => HandleFatal(eventArgs.Exception, "UI thread");
        AppDomain.CurrentDomain.UnhandledException += (_, eventArgs) =>
            HandleFatal(eventArgs.ExceptionObject as Exception ?? new Exception(eventArgs.ExceptionObject?.ToString()), "AppDomain");

        try
        {
            ApplicationConfiguration.Initialize();
            using var form = new MechanicalForm();

            if (_smokeTest)
            {
                var timer = new System.Windows.Forms.Timer { Interval = 2500 };
                timer.Tick += (_, _) =>
                {
                    timer.Stop();
                    form.Close();
                };
                form.Shown += (_, _) => timer.Start();
            }

            Application.Run(form);
            return 0;
        }
        catch (Exception ex)
        {
            HandleFatal(ex, "startup");
            return 1;
        }
    }

    private static void HandleFatal(Exception exception, string stage)
    {
        string? crashFile = null;
        try
        {
            Directory.CreateDirectory(CrashDirectory);
            crashFile = Path.Combine(CrashDirectory, $"astermax-crash-{DateTime.Now:yyyyMMdd-HHmmss}.log");
            File.WriteAllText(crashFile,
                $"AsterMax Mechanical 0.3.1 beta{Environment.NewLine}" +
                $"Stage: {stage}{Environment.NewLine}" +
                $"Windows: {Environment.OSVersion}{Environment.NewLine}" +
                $"64-bit process: {Environment.Is64BitProcess}{Environment.NewLine}" +
                $"Time: {DateTimeOffset.Now:O}{Environment.NewLine}{Environment.NewLine}" +
                exception);
        }
        catch
        {
            // Last-resort handler must never throw another exception.
        }

        if (!_smokeTest)
        {
            try
            {
                MessageBox.Show(
                    $"AsterMax no pudo iniciar.\n\n{exception.Message}\n\n" +
                    (crashFile is null ? "No fue posible crear el registro." : $"Registro: {crashFile}"),
                    "AsterMax — error de inicio",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch
            {
                // Nothing else can be shown safely.
            }
        }

        Environment.ExitCode = 1;
        if (Application.MessageLoop)
            Application.Exit();
    }
}

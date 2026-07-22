using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal sealed class HotkeyWindow : NativeWindow, IDisposable
{
    private const int WmHotkey = 0x0312;
    private const uint Modifiers = 0x0001 | 0x0002 | 0x4000; // Alt + Ctrl + sem repetição
    public event Action<int> Pressed;

    public HotkeyWindow()
    {
        CreateHandle(new CreateParams { Caption = "RF Next Market Monitor" });
        if (!RegisterHotKey(Handle, 1, Modifiers, 0x41) || !RegisterHotKey(Handle, 2, Modifiers, 0x53))
        {
            Dispose();
            throw new InvalidOperationException("Ctrl+Alt+A ou Ctrl+Alt+S já está em uso.");
        }
    }

    protected override void WndProc(ref Message message)
    {
        if (message.Msg == WmHotkey && Pressed != null) Pressed(message.WParam.ToInt32());
        base.WndProc(ref message);
    }

    public void Dispose()
    {
        if (Handle != IntPtr.Zero)
        {
            UnregisterHotKey(Handle, 1);
            UnregisterHotKey(Handle, 2);
            DestroyHandle();
        }
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr window, int id, uint modifiers, uint key);

    [DllImport("user32.dll")]
    private static extern bool UnregisterHotKey(IntPtr window, int id);
}

internal sealed class MarketMonitorContext : ApplicationContext
{
    private readonly string _baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
    private readonly NotifyIcon _tray;
    private readonly ToolStripMenuItem _startItem;
    private readonly ToolStripMenuItem _stopItem;
    private readonly HotkeyWindow _hotkeys;
    private readonly System.Windows.Forms.Timer _timer;
    private Process _capture;
    private string _controlFile;
    private bool _exitRequested;

    public MarketMonitorContext()
    {
        _startItem = new ToolStripMenuItem("Iniciar monitoramento", null, delegate { StartCapture(); });
        _stopItem = new ToolStripMenuItem("Encerrar captura", null, delegate { StopCapture(); });
        var exitItem = new ToolStripMenuItem("Sair do programa", null, delegate { ExitProgram(); });
        var menu = new ContextMenuStrip();
        menu.Items.AddRange(new ToolStripItem[] { _startItem, _stopItem, new ToolStripSeparator(), exitItem });
        _tray = new NotifyIcon { Icon = SystemIcons.Application, Text = "RF Next Mercado — aguardando", ContextMenuStrip = menu, Visible = true };

        _hotkeys = new HotkeyWindow();
        _hotkeys.Pressed += delegate(int id) { if (id == 1) StartCapture(); else StopCapture(); };
        _timer = new System.Windows.Forms.Timer { Interval = 500 };
        _timer.Tick += delegate { CheckCapture(); };
        _timer.Start();
        SetIdle();
    }

    private void StartCapture()
    {
        if (_capture != null && !_capture.HasExited)
        {
            Notify("O monitoramento já está ativo.");
            return;
        }
        string script = Path.Combine(_baseDirectory, "Capturar-Trafego.ps1");
        if (!File.Exists(script))
        {
            Notify("Capturar-Trafego.ps1 não foi encontrado.");
            return;
        }
        _controlFile = Path.Combine(Path.GetTempPath(), "rfnext-market-" + Process.GetCurrentProcess().Id + ".commands");
        File.WriteAllText(_controlFile, "", new UTF8Encoding(false));
        _capture = Process.Start(new ProcessStartInfo
        {
            FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell\\v1.0\\powershell.exe"),
            Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\" -ContinuousMarket -NoHotkeys -ControlFile \"" + _controlFile + "\"",
            WorkingDirectory = _baseDirectory,
            UseShellExecute = false,
            CreateNoWindow = true
        });
        _tray.Text = "RF Next Mercado — monitorando";
        _startItem.Enabled = false;
        _stopItem.Enabled = true;
        Notify("Monitoramento iniciado.");
    }

    private void StopCapture()
    {
        if (_capture == null || _capture.HasExited)
        {
            SetIdle();
            return;
        }
        File.AppendAllText(_controlFile, "ENCERRAR\r\n", new UTF8Encoding(false));
        _tray.Text = "RF Next Mercado — encerrando";
        _stopItem.Enabled = false;
    }

    private void CheckCapture()
    {
        if (_capture == null || !_capture.HasExited) return;
        int exitCode = _capture.ExitCode;
        _capture.Dispose();
        _capture = null;
        if (_controlFile != null && File.Exists(_controlFile)) File.Delete(_controlFile);
        _controlFile = null;
        SetIdle();
        if (_exitRequested) ExitThread();
        else Notify(exitCode == 0 ? "Captura encerrada; o programa continua aguardando." : "A captura encerrou com erro.");
    }

    private void SetIdle()
    {
        _tray.Text = "RF Next Mercado — aguardando";
        _startItem.Enabled = true;
        _stopItem.Enabled = false;
    }

    private void Notify(string text)
    {
        _tray.BalloonTipTitle = "RF Next Mercado";
        _tray.BalloonTipText = text;
        _tray.ShowBalloonTip(2500);
    }

    private void ExitProgram()
    {
        _exitRequested = true;
        if (_capture != null && !_capture.HasExited) StopCapture();
        else ExitThread();
    }

    protected override void ExitThreadCore()
    {
        _timer.Stop();
        _timer.Dispose();
        _hotkeys.Dispose();
        _tray.Visible = false;
        _tray.Dispose();
        base.ExitThreadCore();
    }
}

internal static class RFNextMarketMonitorLauncher
{
    [STAThread]
    private static void Main()
    {
        bool created;
        using (var mutex = new Mutex(true, @"Local\RFNextMarketMonitor", out created))
        {
            if (!created) return;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                Application.Run(new MarketMonitorContext());
            }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, "Monitor do Mercado RF Next", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}

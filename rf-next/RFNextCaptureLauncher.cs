using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class RFNextCaptureLauncher
{
    [STAThread]
    private static void Main()
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(baseDirectory, "Capturar-Trafego.ps1");

        if (!File.Exists(script))
        {
            MessageBox.Show(
                "Arquivo Capturar-Trafego.ps1 não encontrado ao lado do programa.",
                "Capturador RF Next",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        var process = new ProcessStartInfo
        {
            FileName = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell\\v1.0\\powershell.exe"),
            Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File \"" + script + "\" -Gui",
            WorkingDirectory = baseDirectory,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        Process.Start(process);
    }
}

using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace ControlarTela;

sealed record WindowChoice(nint Handle, string Title, string ProcessName)
{
    public string Display => $"{Title}  [{ProcessName}, 0x{Handle:X}]";
    public override string ToString() => Display;
}

static class NativeMethods
{
    const uint InputMouse = 0;
    const uint MouseMove = 0x0001;
    const uint MouseLeftDown = 0x0002;
    const uint MouseLeftUp = 0x0004;
    const uint MouseVirtualDesk = 0x4000;
    const uint MouseAbsolute = 0x8000;
    const uint WindowMessageMouseMove = 0x0200;
    const uint WindowMessageLeftButtonDown = 0x0201;
    const uint WindowMessageLeftButtonUp = 0x0202;
    const uint MouseKeyLeftButton = 0x0001;
    const uint GetAncestorRoot = 2;
    const uint ExtendedFrameBounds = 9;
    const int VirtualScreenLeft = 76;
    const int VirtualScreenTop = 77;
    const int VirtualScreenWidth = 78;
    const int VirtualScreenHeight = 79;

    delegate bool EnumWindowsProc(nint handle, nint parameter);

    [DllImport("user32.dll")]
    static extern bool EnumWindows(EnumWindowsProc callback, nint parameter);

    [DllImport("user32.dll")]
    static extern bool IsWindowVisible(nint handle);

    [DllImport("user32.dll")]
    public static extern bool IsWindow(nint handle);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(nint handle);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetWindowText(nint handle, StringBuilder text, int count);

    [DllImport("user32.dll")]
    static extern int GetWindowTextLength(nint handle);

    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(nint handle, out uint processId);

    [DllImport("user32.dll")]
    static extern bool GetClientRect(nint handle, out RECT rectangle);

    [DllImport("user32.dll")]
    static extern bool GetWindowRect(nint handle, out RECT rectangle);

    [DllImport("dwmapi.dll")]
    static extern int DwmGetWindowAttribute(nint handle, uint attribute, out RECT value, int size);

    [DllImport("user32.dll")]
    static extern bool ClientToScreen(nint handle, ref POINT point);

    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(nint handle);

    [DllImport("user32.dll")]
    static extern uint SendInput(uint count, INPUT[] inputs, int size);

    [DllImport("user32.dll")]
    static extern int GetSystemMetrics(int index);

    [DllImport("user32.dll")]
    static extern nint WindowFromPoint(POINT point);

    [DllImport("user32.dll")]
    static extern nint GetAncestor(nint handle, uint flags);

    [DllImport("user32.dll", SetLastError = true)]
    static extern bool PostMessage(nint handle, uint message, nint wParam, nint lParam);

    public static List<WindowChoice> ListWindows()
    {
        var result = new List<WindowChoice>();
        var ownProcessId = Environment.ProcessId;

        EnumWindows((handle, _) =>
        {
            if (!IsWindowVisible(handle))
                return true;

            var length = GetWindowTextLength(handle);
            if (length == 0)
                return true;

            var title = new StringBuilder(length + 1);
            GetWindowText(handle, title, title.Capacity);
            GetWindowThreadProcessId(handle, out var processId);
            if (processId == ownProcessId)
                return true;

            try
            {
                var process = Process.GetProcessById((int)processId);
                result.Add(new WindowChoice(handle, title.ToString(), process.ProcessName));
            }
            catch
            {
                // A janela pode desaparecer durante a enumeração.
            }
            return true;
        }, 0);

        return result.OrderBy(item => item.Title, StringComparer.CurrentCultureIgnoreCase).ToList();
    }

    public static bool TryGetClientScreenBounds(nint handle, out Rectangle bounds)
    {
        bounds = Rectangle.Empty;
        if (!IsWindow(handle) || !GetClientRect(handle, out var client))
            return false;

        var topLeft = new POINT { X = client.Left, Y = client.Top };
        if (!ClientToScreen(handle, ref topLeft))
            return false;

        var width = client.Right - client.Left;
        var height = client.Bottom - client.Top;
        if (width <= 0 || height <= 0)
            return false;

        bounds = new Rectangle(topLeft.X, topLeft.Y, width, height);
        return true;
    }

    public static bool TryGetClientAreaInCapture(nint handle, Size captureSize, out Rectangle area)
    {
        area = Rectangle.Empty;
        if (!GetClientRect(handle, out var client))
            return false;
        var width = client.Right - client.Left;
        var height = client.Bottom - client.Top;
        if (width <= 0 || height <= 0 || width > captureSize.Width || height > captureSize.Height)
            return false;
        if (width == captureSize.Width && height == captureSize.Height)
        {
            area = new Rectangle(0, 0, width, height);
            return true;
        }

        var topLeft = new POINT();
        if (!ClientToScreen(handle, ref topLeft))
            return false;
        RECT captureBounds;
        if (DwmGetWindowAttribute(handle, ExtendedFrameBounds, out captureBounds, Marshal.SizeOf<RECT>()) < 0
            || captureBounds.Right - captureBounds.Left != captureSize.Width
            || captureBounds.Bottom - captureBounds.Top != captureSize.Height)
        {
            if (!GetWindowRect(handle, out captureBounds))
                return false;
        }
        return TryResolveClientArea(
            captureSize,
            new Size(width, height),
            new Point(topLeft.X, topLeft.Y),
            Rectangle.FromLTRB(captureBounds.Left, captureBounds.Top, captureBounds.Right, captureBounds.Bottom),
            out area);
    }

    static bool TryResolveClientArea(
        Size captureSize,
        Size clientSize,
        Point clientScreenTopLeft,
        Rectangle captureScreenBounds,
        out Rectangle area)
    {
        var x = clientScreenTopLeft.X - captureScreenBounds.Left;
        var y = clientScreenTopLeft.Y - captureScreenBounds.Top;
        area = new Rectangle(x, y, clientSize.Width, clientSize.Height);
        return x >= 0 && y >= 0 && area.Right <= captureSize.Width && area.Bottom <= captureSize.Height;
    }

    public static bool TryActivate(nint handle)
    {
        if (!IsWindow(handle) || IsIconic(handle) || !SetForegroundWindow(handle))
            return false;
        Thread.Sleep(150);
        return true;
    }

    public static bool TryClick(nint handle, int clientX, int clientY, out string error)
    {
        error = "";
        if (IsIconic(handle))
        {
            error = "janela minimizada";
            return false;
        }

        if (!TryGetClientScreenBounds(handle, out var client)
            || clientX < 0 || clientY < 0 || clientX >= client.Width || clientY >= client.Height)
        {
            error = "ponto de clique fora da janela";
            return false;
        }

        if (!TryActivate(handle))
        {
            error = "não foi possível ativar a janela";
            return false;
        }
        var point = new POINT { X = client.Left + clientX, Y = client.Top + clientY };

        // Evita clicar em outra janela caso o alvo não tenha vindo para frente.
        if (GetAncestor(WindowFromPoint(point), GetAncestorRoot) != handle)
        {
            error = "janela coberta no ponto do clique";
            return false;
        }

        var virtualLeft = GetSystemMetrics(VirtualScreenLeft);
        var virtualTop = GetSystemMetrics(VirtualScreenTop);
        var virtualWidth = GetSystemMetrics(VirtualScreenWidth);
        var virtualHeight = GetSystemMetrics(VirtualScreenHeight);
        if (virtualWidth <= 1 || virtualHeight <= 1)
        {
            error = "não foi possível obter o tamanho da área de trabalho";
            return false;
        }

        var inputs = new[]
        {
            MouseInput(
                MouseMove | MouseAbsolute | MouseVirtualDesk,
                NormalizeAbsolute(point.X, virtualLeft, virtualWidth),
                NormalizeAbsolute(point.Y, virtualTop, virtualHeight)),
            MouseInput(MouseLeftDown),
            MouseInput(MouseLeftUp)
        };
        if (SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>()) != inputs.Length)
        {
            error = "Windows ou o jogo recusou o clique; execute os dois no mesmo nível de permissão";
            return false;
        }

        return true;
    }

    public static bool TryBackgroundClick(nint handle, int clientX, int clientY, out string error)
    {
        error = "";
        if (!IsWindow(handle) || !GetClientRect(handle, out var client)
            || clientX < 0 || clientY < 0
            || clientX >= client.Right - client.Left
            || clientY >= client.Bottom - client.Top)
        {
            error = "janela indisponível ou ponto fora da área útil";
            return false;
        }

        var point = PackClientPoint(clientX, clientY);
        if (!PostMessage(handle, WindowMessageMouseMove, 0, point)
            || !PostMessage(handle, WindowMessageLeftButtonDown, (nint)MouseKeyLeftButton, point))
        {
            error = $"Windows recusou a mensagem (erro {Marshal.GetLastWin32Error()})";
            return false;
        }
        Thread.Sleep(80);
        if (!PostMessage(handle, WindowMessageLeftButtonUp, 0, point))
        {
            error = $"Windows recusou a soltura do botão (erro {Marshal.GetLastWin32Error()})";
            return false;
        }
        return true;
    }

    static nint PackClientPoint(int x, int y) => unchecked((nint)((y << 16) | (x & 0xFFFF)));

    static int NormalizeAbsolute(int value, int origin, int size) =>
        (int)Math.Round(Math.Clamp((value - origin) / (double)(size - 1), 0, 1) * 65535);

    static INPUT MouseInput(uint flags, int x = 0, int y = 0) => new()
    {
        Type = InputMouse,
        Data = new InputUnion { Mouse = new MOUSEINPUT { X = x, Y = y, Flags = flags } }
    };

    public static void RunSelfTest()
    {
        if (!TryResolveClientArea(
                new Size(800, 600),
                new Size(780, 560),
                new Point(110, 130),
                new Rectangle(100, 100, 800, 600),
                out var clientArea)
            || clientArea != new Rectangle(10, 30, 780, 560))
            throw new InvalidOperationException("Falha ao localizar a área cliente na captura da janela.");
        if (NormalizeAbsolute(-1920, -1920, 3840) != 0
            || NormalizeAbsolute(1919, -1920, 3840) != 65535
            || NormalizeAbsolute(0, -1920, 3840) is < 32770 or > 32776
            || (long)PackClientPoint(123, 456) != (456L << 16 | 123))
            throw new InvalidOperationException("Falha ao normalizar coordenadas do desktop virtual.");
    }

    [StructLayout(LayoutKind.Sequential)]
    struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct INPUT
    {
        public uint Type;
        public InputUnion Data;
    }

    [StructLayout(LayoutKind.Explicit)]
    struct InputUnion
    {
        [FieldOffset(0)] public MOUSEINPUT Mouse;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct MOUSEINPUT
    {
        public int X;
        public int Y;
        public uint MouseData;
        public uint Flags;
        public uint Time;
        public nint ExtraInfo;
    }
}

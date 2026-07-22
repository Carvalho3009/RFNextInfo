using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;
using WinRT;

namespace ControlarTela;

sealed class WindowCapture : IDisposable
{
    readonly nint _window;
    readonly object _sync = new();
    readonly TaskCompletionSource _firstFrame = new(TaskCreationOptions.RunContinuationsAsynchronously);
    IDirect3DDevice? _device;
    GraphicsCaptureItem? _item;
    Direct3D11CaptureFramePool? _pool;
    GraphicsCaptureSession? _session;
    Bitmap? _latest;
    DateTimeOffset _latestAt;
    int _reading;
    bool _closed;

    WindowCapture(nint window) => _window = window;

    public static async Task<(WindowCapture? Capture, string Error)> StartAsync(nint window, int timeoutMs = 4000)
    {
        var capture = new WindowCapture(window);
        try
        {
            capture.Start();
            if (await Task.WhenAny(capture._firstFrame.Task, Task.Delay(timeoutMs)) != capture._firstFrame.Task)
                throw new InvalidOperationException("nenhum quadro recebido em 4 segundos");
            await capture._firstFrame.Task;
            return (capture, "");
        }
        catch (Exception error)
        {
            capture.Dispose();
            return (null, $"Captura em segundo plano indisponível: {error.Message}");
        }
    }

    void Start()
    {
        if (!GraphicsCaptureSession.IsSupported())
            throw new NotSupportedException("Windows.Graphics.Capture não é compatível com este computador");
        if (NativeMethods.IsIconic(_window))
            throw new InvalidOperationException("A janela do jogo está minimizada. Restaure-a e deixe-a aberta; ela pode ficar coberta.");

        _device = CreateDevice();
        _item = CreateItem(_window);
        _item.Closed += OnClosed;
        _pool = Direct3D11CaptureFramePool.CreateFreeThreaded(
            _device,
            DirectXPixelFormat.B8G8R8A8UIntNormalized,
            2,
            _item.Size);
        _pool.FrameArrived += OnFrameArrived;
        _session = _pool.CreateCaptureSession(_item);
        _session.IsCursorCaptureEnabled = false;
        _session.StartCapture();
    }

    public bool TryGetRegion(ScreenRegion region, out Bitmap bitmap, out string error)
    {
        bitmap = null!;
        error = "";
        if (_closed || !NativeMethods.IsWindow(_window))
        {
            error = "A janela ou a captura foi encerrada.";
            return false;
        }
        if (NativeMethods.IsIconic(_window))
        {
            error = "A janela do jogo está minimizada. Restaure-a e deixe-a aberta; ela pode ficar coberta.";
            return false;
        }

        lock (_sync)
        {
            if (_latest is null || DateTimeOffset.Now - _latestAt > TimeSpan.FromSeconds(2))
            {
                error = "Captura sem quadros recentes; o jogo pode ter parado de renderizar.";
                return false;
            }
            if (!NativeMethods.TryGetClientAreaInCapture(_window, _latest.Size, out var clientArea))
            {
                error = "Não foi possível localizar a área útil na captura.";
                return false;
            }
            var source = new Rectangle(clientArea.X + region.X, clientArea.Y + region.Y, region.Width, region.Height);
            if (!region.IsConfigured || source.X < 0 || source.Y < 0
                || source.Right > _latest.Width || source.Bottom > _latest.Height)
            {
                error = "A região marcada ficou fora da imagem capturada.";
                return false;
            }
            bitmap = _latest.Clone(source, PixelFormat.Format24bppRgb);
        }

        if (Recognition.ContentPercent(bitmap) >= 1)
            return true;
        bitmap.Dispose();
        bitmap = null!;
        error = "Captura preta; o jogo não está fornecendo imagem em segundo plano.";
        return false;
    }

    async void OnFrameArrived(Direct3D11CaptureFramePool sender, object args)
    {
        if (_closed || Interlocked.Exchange(ref _reading, 1) != 0)
            return;
        try
        {
            using var frame = sender.TryGetNextFrame();
            using var source = await SoftwareBitmap.CreateCopyFromSurfaceAsync(frame.Surface);
            using var converted = SoftwareBitmap.Convert(source, BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore);
            var bitmap = ToBitmap(converted);
            lock (_sync)
            {
                if (_closed)
                    bitmap.Dispose();
                else
                {
                    _latest?.Dispose();
                    _latest = bitmap;
                    _latestAt = DateTimeOffset.Now;
                }
            }
            _firstFrame.TrySetResult();
        }
        catch (Exception error)
        {
            _firstFrame.TrySetException(error);
        }
        finally
        {
            Volatile.Write(ref _reading, 0);
        }
    }

    void OnClosed(GraphicsCaptureItem sender, object args)
    {
        _closed = true;
        _firstFrame.TrySetException(new InvalidOperationException("a janela foi fechada"));
    }

    static Bitmap ToBitmap(SoftwareBitmap source)
    {
        var bytes = new byte[checked(source.PixelWidth * source.PixelHeight * 4)];
        var buffer = new Windows.Storage.Streams.Buffer((uint)bytes.Length);
        source.CopyToBuffer(buffer);
        using (var reader = DataReader.FromBuffer(buffer))
            reader.ReadBytes(bytes);

        var bitmap = new Bitmap(source.PixelWidth, source.PixelHeight, PixelFormat.Format32bppArgb);
        var data = bitmap.LockBits(
            new Rectangle(0, 0, bitmap.Width, bitmap.Height),
            ImageLockMode.WriteOnly,
            PixelFormat.Format32bppArgb);
        try
        {
            Marshal.Copy(bytes, 0, data.Scan0, bytes.Length);
        }
        finally
        {
            bitmap.UnlockBits(data);
        }
        return bitmap;
    }

    static IDirect3DDevice CreateDevice()
    {
        var result = D3D11CreateDevice(0, 1, 0, 0x20, 0, 0, 7, out var d3dDevice, out _, out var context);
        if (result < 0)
            Marshal.ThrowExceptionForHR(result);
        try
        {
            var iid = new Guid("54ec77fa-1377-44e6-8c32-88fd5f44c84c");
            result = Marshal.QueryInterface(d3dDevice, ref iid, out var dxgiDevice);
            if (result < 0)
                Marshal.ThrowExceptionForHR(result);
            try
            {
                result = CreateDirect3D11DeviceFromDXGIDevice(dxgiDevice, out var inspectable);
                if (result < 0)
                    Marshal.ThrowExceptionForHR(result);
                try
                {
                    return MarshalInterface<IDirect3DDevice>.FromAbi(inspectable);
                }
                finally
                {
                    Marshal.Release(inspectable);
                }
            }
            finally
            {
                Marshal.Release(dxgiDevice);
            }
        }
        finally
        {
            Marshal.Release(context);
            Marshal.Release(d3dDevice);
        }
    }

    static GraphicsCaptureItem CreateItem(nint window)
    {
        var interop = GraphicsCaptureItem.As<IGraphicsCaptureItemInterop>();
        var iid = new Guid("79c3f95b-31f7-4ec2-a464-632ef5d30760");
        var result = interop.CreateForWindow(window, ref iid, out var itemPointer);
        if (result < 0)
            Marshal.ThrowExceptionForHR(result);
        try
        {
            return MarshalInspectable<GraphicsCaptureItem>.FromAbi(itemPointer);
        }
        finally
        {
            Marshal.Release(itemPointer);
        }
    }

    public void Dispose()
    {
        _closed = true;
        if (_item is not null)
            _item.Closed -= OnClosed;
        if (_pool is not null)
            _pool.FrameArrived -= OnFrameArrived;
        _session?.Dispose();
        _pool?.Dispose();
        _item = null;
        _device?.Dispose();
        _device = null;
        lock (_sync)
        {
            _latest?.Dispose();
            _latest = null;
        }
    }

    [ComImport, Guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IGraphicsCaptureItemInterop
    {
        [PreserveSig]
        int CreateForWindow(nint window, ref Guid iid, out nint result);

        [PreserveSig]
        int CreateForMonitor(nint monitor, ref Guid iid, out nint result);
    }

    [DllImport("d3d11.dll", ExactSpelling = true)]
    static extern int D3D11CreateDevice(
        nint adapter,
        int driverType,
        nint software,
        uint flags,
        nint featureLevels,
        uint featureLevelCount,
        uint sdkVersion,
        out nint device,
        out uint featureLevel,
        out nint immediateContext);

    [DllImport("d3d11.dll", ExactSpelling = true)]
    static extern int CreateDirect3D11DeviceFromDXGIDevice(nint dxgiDevice, out nint graphicsDevice);
}

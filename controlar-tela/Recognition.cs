using System.Drawing.Imaging;

namespace ControlarTela;

static class Recognition
{
    public static Bitmap Capture(Rectangle clientBounds, ScreenRegion region)
    {
        var bitmap = new Bitmap(region.Width, region.Height, PixelFormat.Format24bppRgb);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.CopyFromScreen(
            clientBounds.Left + region.X,
            clientBounds.Top + region.Y,
            0,
            0,
            bitmap.Size,
            CopyPixelOperation.SourceCopy);
        return bitmap;
    }

    public static double LifePercent(Bitmap bitmap, int fullRedWidth) =>
        fullRedWidth <= 0 ? 0 : Math.Clamp(RedWidth(bitmap) * 100d / fullRedWidth, 0, 100);

    public static double DifferencePercent(Bitmap first, Bitmap second)
    {
        EnsureSameSize(first, second);
        var step = SampleStep(first);
        var total = 0;
        var changed = 0;

        for (var y = 0; y < first.Height; y += step)
        for (var x = 0; x < first.Width; x += step)
        {
            total++;
            if (ColorDelta(first.GetPixel(x, y), second.GetPixel(x, y)) >= 20)
                changed++;
        }

        return total == 0 ? 0 : changed * 100d / total;
    }

    public static double ContentPercent(Bitmap bitmap)
    {
        var step = SampleStep(bitmap);
        var total = 0;
        var visible = 0;
        for (var y = 0; y < bitmap.Height; y += step)
        for (var x = 0; x < bitmap.Width; x += step)
        {
            total++;
            if (Luma(bitmap.GetPixel(x, y)) >= 5)
                visible++;
        }
        return total == 0 ? 0 : visible * 100d / total;
    }

    public static bool LooksLikeBar(Bitmap bitmap)
    {
        return RedWidth(bitmap) >= Math.Max(3, bitmap.Width / 20);
    }

    public static int RedWidth(Bitmap bitmap)
    {
        var first = -1;
        var last = -1;
        var minimumRedPixels = Math.Max(2, (bitmap.Height + 5) / 6);
        for (var x = 0; x < bitmap.Width; x++)
        {
            var redPixels = 0;
            for (var y = 0; y < bitmap.Height; y++)
                if (IsRed(bitmap.GetPixel(x, y)))
                    redPixels++;
            if (redPixels < minimumRedPixels)
                continue;
            if (first < 0)
                first = x;
            last = x;
        }
        return first < 0 ? 0 : last - first + 1;
    }

    static bool IsRed(Color color) =>
        color.R >= 60 && color.R - color.G >= 25 && color.R - color.B >= 20;

    static int SampleStep(Bitmap bitmap) =>
        Math.Max(1, (int)Math.Sqrt(bitmap.Width * bitmap.Height / 20_000d));

    static int ColorDelta(Color first, Color second) =>
        (Math.Abs(first.R - second.R) + Math.Abs(first.G - second.G) + Math.Abs(first.B - second.B)) / 3;

    static int Luma(Color color) => (299 * color.R + 587 * color.G + 114 * color.B) / 1000;
    static void EnsureSameSize(Bitmap first, Bitmap second)
    {
        if (first.Size != second.Size)
            throw new ArgumentException("As capturas da barra têm tamanhos diferentes.");
    }

    public static void RunSelfTest()
    {
        using var full = new Bitmap(100, 10);
        using (var graphics = Graphics.FromImage(full))
            graphics.Clear(Color.Red);

        using var reduced = new Bitmap(100, 10);
        using (var graphics = Graphics.FromImage(reduced))
        {
            graphics.Clear(Color.Black);
            graphics.FillRectangle(Brushes.Red, 0, 0, 70, 10);
        }

        var difference = DifferencePercent(full, reduced);

        using var decoratedFull = DecoratedBar(100, 20);
        using var decoratedReduced = DecoratedBar(70, 5);
        using var blue = new Bitmap(100, 10);
        using (var graphics = Graphics.FromImage(blue))
            graphics.Clear(Color.DeepSkyBlue);

        if (LifePercent(reduced, RedWidth(full)) is < 69 or > 71
            || LifePercent(decoratedReduced, RedWidth(decoratedFull)) is < 69 or > 71
            || difference < 29 || difference > 31
            || !LooksLikeBar(full) || !LooksLikeBar(decoratedFull) || LooksLikeBar(blue)
            || ContentPercent(full) != 100
            || ContentPercent(reduced) is < 69 or > 71
            || DifferencePercent(full, full) != 0)
            throw new InvalidOperationException("Falha no autoteste da barra de vida.");

        static Bitmap DecoratedBar(int width, int textX)
        {
            var bitmap = new Bitmap(100, 10);
            using var graphics = Graphics.FromImage(bitmap);
            using var red = new SolidBrush(Color.FromArgb(226, 71, 68));
            graphics.Clear(Color.FromArgb(25, 25, 25));
            graphics.FillRectangle(red, 0, 0, width, 8);
            graphics.FillRectangle(Brushes.White, textX, 2, 30, 4);
            graphics.FillRectangle(Brushes.DeepSkyBlue, 0, 8, 100, 2);
            return bitmap;
        }
    }
}

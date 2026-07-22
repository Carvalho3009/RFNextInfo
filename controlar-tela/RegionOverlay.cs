namespace ControlarTela;

sealed class RegionOverlay : Form
{
    readonly bool _pointMode;
    readonly bool _displayMode;
    readonly string _instruction;
    readonly IReadOnlyList<(Rectangle Region, string Label, Color Color)> _regions;
    readonly IReadOnlyList<(Point Point, string Label, Color Color)> _points;
    readonly System.Windows.Forms.Timer? _closeTimer;
    Point _start;
    Point _current;
    bool _dragging;

    public Rectangle SelectedRegion { get; private set; }
    public Point SelectedPoint { get; private set; }

    public RegionOverlay(
        Rectangle targetBounds,
        bool pointMode = false,
        string? instruction = null,
        IReadOnlyList<(Rectangle Region, string Label, Color Color)>? regions = null,
        IReadOnlyList<(Point Point, string Label, Color Color)>? points = null)
    {
        _pointMode = pointMode;
        _displayMode = regions is not null || points is not null;
        _regions = regions ?? [];
        _points = points ?? [];
        _instruction = instruction ?? (_pointMode
            ? "Clique no ponto desejado — Esc cancela"
            : "Arraste sobre toda a barra de vida — Esc cancela");
        Bounds = targetBounds;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        ShowInTaskbar = false;
        TopMost = true;
        BackColor = Color.Black;
        Opacity = _displayMode ? 0.65 : 0.35;
        Cursor = _displayMode ? Cursors.Default : Cursors.Cross;
        KeyPreview = true;
        DoubleBuffered = true;

        MouseMove += (_, eventArgs) =>
        {
            if (_displayMode)
                return;
            _current = eventArgs.Location;
            if (_dragging || _pointMode)
                Invalidate();
        };
        MouseDown += (_, eventArgs) =>
        {
            if (_displayMode)
            {
                Close();
                return;
            }
            if (_pointMode)
            {
                SelectedPoint = eventArgs.Location;
                DialogResult = DialogResult.OK;
                return;
            }
            _start = eventArgs.Location;
            _current = eventArgs.Location;
            _dragging = true;
            Invalidate();
        };
        MouseUp += (_, eventArgs) =>
        {
            if (_displayMode || _pointMode || !_dragging)
                return;
            _dragging = false;
            _current = eventArgs.Location;
            SelectedRegion = Normalize(_start, _current);
            if (SelectedRegion.Width >= 2 && SelectedRegion.Height >= 2)
                DialogResult = DialogResult.OK;
        };
        KeyDown += (_, eventArgs) =>
        {
            if (eventArgs.KeyCode == Keys.Escape)
                Close();
        };

        if (_displayMode)
        {
            _closeTimer = new System.Windows.Forms.Timer { Interval = 8000 };
            _closeTimer.Tick += (_, _) => Close();
            Shown += (_, _) => _closeTimer.Start();
            FormClosed += (_, _) => _closeTimer.Dispose();
        }
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        base.OnPaint(eventArgs);
        using var font = new Font(Font.FontFamily, 14, FontStyle.Bold);
        eventArgs.Graphics.DrawString(
            _instruction,
            font,
            Brushes.White,
            12,
            12);

        if (_displayMode)
        {
            DrawMarks(eventArgs.Graphics);
            return;
        }

        using var pen = new Pen(Color.Red, 5);
        if (_pointMode)
        {
            eventArgs.Graphics.DrawLine(pen, _current.X - 14, _current.Y, _current.X + 14, _current.Y);
            eventArgs.Graphics.DrawLine(pen, _current.X, _current.Y - 14, _current.X, _current.Y + 14);
        }
        else if (_dragging)
        {
            eventArgs.Graphics.DrawRectangle(pen, Normalize(_start, _current));
        }
    }

    void DrawMarks(Graphics graphics)
    {
        using var font = new Font(Font.FontFamily, 11, FontStyle.Bold);
        foreach (var (region, label, color) in _regions)
        {
            using var pen = new Pen(color, 4);
            graphics.DrawRectangle(pen, region);
            graphics.DrawString(label, font, Brushes.White, region.X + 4, Math.Max(45, region.Y + 4));
        }

        foreach (var (point, label, color) in _points)
        {
            var marker = new Rectangle(point.X - 10, point.Y - 10, 20, 20);
            using var brush = new SolidBrush(color);
            graphics.FillEllipse(brush, marker);
            graphics.DrawEllipse(Pens.White, marker);
            graphics.DrawString(label, font, Brushes.White, point.X + 14, point.Y - 12);
        }
    }

    static Rectangle Normalize(Point first, Point second) => Rectangle.FromLTRB(
        Math.Min(first.X, second.X),
        Math.Min(first.Y, second.Y),
        Math.Max(first.X, second.X),
        Math.Max(first.Y, second.Y));
}

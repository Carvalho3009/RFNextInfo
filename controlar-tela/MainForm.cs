namespace ControlarTela;

sealed class MainForm : Form
{
    const int BarSearchIntervalSeconds = 5;
    static readonly Color Ink = Color.FromArgb(7, 9, 9);
    static readonly Color InkSoft = Color.FromArgb(13, 17, 16);
    static readonly Color Bone = Color.FromArgb(244, 242, 235);
    static readonly Color Muted = Color.FromArgb(185, 181, 170);
    static readonly Color Gold = Color.FromArgb(212, 166, 77);
    static readonly Color Acid = Color.FromArgb(168, 255, 22);
    static readonly Color Coral = Color.FromArgb(255, 101, 71);
    static readonly Color Water = Color.FromArgb(99, 185, 243);
    readonly AppConfig _config;
    readonly List<ProfileUi> _profiles = [];
    readonly Dictionary<WindowProfile, OverviewUi> _overviews = [];
    readonly System.Windows.Forms.Timer _timer = new();
    readonly Button _startStop = new();
    readonly Button _updateStatus = new();
    readonly Label _status = new();
    bool _running;
    bool _busy;
    bool _loading;
    bool _checkingUpdate;

    public MainForm(bool checkForUpdates = true)
    {
        _config = ConfigStore.Load(out var warning);
        Text = "Ronaldinho • Proteção por Barra de Vida";
        var workArea = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1600, 900);
        Size = new Size(Math.Min(1600, workArea.Width - 40), Math.Min(960, workArea.Height - 40));
        MinimumSize = new Size(1100, 680);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Ink;
        ForeColor = Bone;
        Font = new Font("Bahnschrift Condensed", 9.5F);

        BuildInterface();
        ApplyBrandTheme(this);
        RefreshWindows();
        if (checkForUpdates)
            Shown += async (_, _) => await CheckForUpdatesAsync();
        if (warning is not null)
            SetStatus(warning, true);

        _timer.Interval = _config.CaptureIntervalMs;
        _timer.Tick += MonitorTick;
        FormClosing += (_, _) =>
        {
            _timer.Stop();
            TrySave();
            foreach (var profile in _profiles)
                profile.Dispose();
        };
    }

    void BuildInterface()
    {
        var sidebar = new Panel
        {
            Name = "Sidebar",
            Dock = DockStyle.Fill,
            BackColor = Color.FromArgb(9, 13, 14),
            Padding = new Padding(14, 18, 14, 18)
        };
        var sidebarLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            Margin = Padding.Empty,
            BackColor = sidebar.BackColor
        };
        sidebarLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 118));
        sidebarLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
        sidebarLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var logo = new PictureBox
        {
            Dock = DockStyle.Fill,
            SizeMode = PictureBoxSizeMode.Zoom,
            Image = LoadBrandLogo(),
            Margin = Padding.Empty
        };
        var slogan = new Label
        {
            Text = "D I B R E   A   C O N C O R R Ê N C I A",
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = Gold,
            Font = new Font("Bahnschrift Condensed", 7.5F, FontStyle.Bold)
        };
        var nav = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            Padding = new Padding(0, 26, 0, 0),
            BackColor = sidebar.BackColor
        };
        sidebarLayout.Controls.Add(logo, 0, 0);
        slogan.Visible = false;
        sidebarLayout.Controls.Add(slogan, 0, 1);
        sidebarLayout.Controls.Add(nav, 0, 2);
        sidebar.Controls.Add(sidebarLayout);

        var content = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            Margin = Padding.Empty,
            BackColor = Ink
        };
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 184));
        content.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));

        var header = new TableLayoutPanel
        {
            Name = "Header",
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
            Padding = new Padding(18, 12, 18, 4),
            BackColor = Ink
        };
        header.RowStyles.Add(new RowStyle(SizeType.Absolute, 70));
        header.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var topActions = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 5, RowCount = 1 };
        topActions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        topActions.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        topActions.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        topActions.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        topActions.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        var tabBar = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, Margin = Padding.Empty };
        topActions.Controls.Add(tabBar, 0, 0);

        _updateStatus.Text = "ATUALIZADO";
        _updateStatus.AutoSize = true;
        _updateStatus.MinimumSize = new Size(115, 42);
        _updateStatus.Font = new Font("Arial Narrow", 9F, FontStyle.Bold);
        _updateStatus.Tag = "badge";
        _updateStatus.Anchor = AnchorStyles.Right | AnchorStyles.Top;
        _updateStatus.Click += async (_, _) => await CheckForUpdatesAsync(true);
        topActions.Controls.Add(_updateStatus, 1, 0);

        topActions.Controls.Add(new Label
        {
            Text = $"v{typeof(MainForm).Assembly.GetName().Version?.ToString(3)}",
            AutoSize = true,
            ForeColor = Muted,
            Anchor = AnchorStyles.Right | AnchorStyles.Top,
            Margin = new Padding(8, 0, 14, 0)
        }, 2, 0);
        var refresh = new Button { Name = "RefreshWindows", Text = "↻  ATUALIZAR JANELAS", AutoSize = true, Anchor = AnchorStyles.Right | AnchorStyles.Top };
        refresh.Tag = "secondary";
        refresh.Click += (_, _) => RefreshWindows();
        topActions.Controls.Add(refresh, 3, 0);

        _startStop.Text = "⛨  INICIAR PROTEÇÃO";
        _startStop.Name = "StartStop";
        _startStop.AutoSize = true;
        _startStop.Anchor = AnchorStyles.Right | AnchorStyles.Top;
        _startStop.Tag = "primary";
        _startStop.BackColor = Acid;
        _startStop.Click += async (_, _) =>
        {
            if (_running)
                StopProtection();
            else
                await StartProtectionAsync();
        };
        topActions.Controls.Add(_startStop, 4, 0);
        header.Controls.Add(topActions, 0, 0);

        var windowHeaderHost = new Panel { Dock = DockStyle.Fill, BackColor = Ink };
        header.Controls.Add(windowHeaderHost, 0, 1);
        var pageHost = new Panel { Name = "TabHost", Dock = DockStyle.Fill, BackColor = Ink };
        var overviewHost = new TableLayoutPanel
        {
            Name = "GlobalOverview",
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 1,
            Padding = new Padding(18, 8, 18, 8),
            BackColor = Ink
        };
        overviewHost.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        overviewHost.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        var pages = new List<Panel>();
        var windowHeaders = new List<Control>();
        var tabButtons = new List<Button>();
        var navButtons = new List<Button>();
        var selectedPage = 0;
        foreach (var profile in _config.Windows)
        {
            var (page, windowHeader) = BuildProfilePage(profile);
            page.Visible = false;
            windowHeader.Visible = false;
            pages.Add(page);
            windowHeaders.Add(windowHeader);
            pageHost.Controls.Add(page);
            windowHeaderHost.Controls.Add(windowHeader);

            var index = pages.Count - 1;
            var tab = new Button
            {
                Text = profile.Name.ToUpperInvariant(),
                Width = 145,
                Height = 48,
                Margin = new Padding(0, 0, 8, 0),
                Tag = "tab"
            };
            tab.Click += (_, _) => SelectPage(index);
            tabButtons.Add(tab);
            tabBar.Controls.Add(tab);
        }
        for (var index = 0; index < _profiles.Count; index++)
            overviewHost.Controls.Add(BuildOverviewCard(_profiles[index]), index, 0);
        pageHost.Controls.Add(overviewHost);
        SelectPage(0);

        _status.Name = "StatusBar";
        _status.Dock = DockStyle.Fill;
        _status.Padding = new Padding(18, 6, 18, 0);
        _status.BackColor = InkSoft;
        _status.ForeColor = Muted;
        _status.Text = "Configure ao menos uma janela.";

        content.Controls.Add(header, 0, 0);
        content.Controls.Add(pageHost, 0, 1);
        content.Controls.Add(_status, 0, 2);
        var shell = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Margin = Padding.Empty };
        shell.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 300));
        shell.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        shell.Controls.Add(sidebar, 0, 0);
        shell.Controls.Add(content, 1, 0);
        Controls.Add(shell);

        AddNav("⌂", "VISÃO GERAL", null);
        AddNav("▣", "JANELA", "WindowHeader");
        AddNav("♡", "BARRA DE VIDA", "LifeModule");
        AddNav("◉", "TELEPORTE", "TeleportModule");
        AddNav("⌖", "ROTA DE SPOTS", "SpotsModule");
        AddNav("⌁", "SESSÃO", "SessionGroup");
        AddNav("⚙", "CONFIGURAÇÕES", "AdvancedGroup");
        SelectNavigation(navButtons[0]);
        SizeChanged += (_, _) => ApplyResponsiveShell();
        ApplyResponsiveShell();

        void ApplyResponsiveShell()
        {
            var compact = ClientSize.Width < 1450;
            shell.ColumnStyles[0].Width = compact ? 230 : 300;
            sidebar.Padding = compact ? new Padding(10, 14, 10, 14) : new Padding(14, 18, 14, 18);
            sidebarLayout.RowStyles[0].Height = compact ? 96 : 118;
            nav.Padding = new Padding(0, compact ? 18 : 26, 0, 0);
            foreach (var button in navButtons)
            {
                button.Width = compact ? 208 : 268;
                button.Height = compact ? 58 : 68;
            }
        }

        void SelectPage(int selected)
        {
            selectedPage = selected;
            for (var index = 0; index < pages.Count; index++)
            {
                pages[index].Visible = false;
                windowHeaders[index].Visible = false;
                tabButtons[index].Tag = index == selected ? "tabSelected" : "tab";
                StyleButton(tabButtons[index]);
            }
            ShowOverview(pages[selected]);
            overviewHost.Visible = true;
            overviewHost.BringToFront();
            foreach (var ui in _profiles)
                RefreshOverview(ui);
            SetWindowSettings(false);
            ActiveViewport().AutoScrollPosition = Point.Empty;
            SelectNavigation(navButtons.FirstOrDefault() ?? new Button());
        }

        void AddNav(string icon, string label, string? target)
        {
            var button = new Button
            {
                Text = $"{icon}   {label}",
                Width = 268,
                Height = 68,
                TextAlign = ContentAlignment.MiddleLeft,
                Margin = new Padding(0, 0, 0, 8),
                Tag = "nav"
            };
            button.Click += (_, _) =>
            {
                SelectNavigation(button);
                var activePage = pages[selectedPage];
                var activeAdvancedToggle = activePage.Controls.Find("AdvancedToggle", true).OfType<CheckBox>().First();
                ActiveViewport().AutoScrollPosition = Point.Empty;
                if (target != "AdvancedGroup" && activeAdvancedToggle.Checked)
                    activeAdvancedToggle.Checked = false;
                if (target is null)
                {
                    ShowOverview(activePage);
                    activePage.Visible = false;
                    overviewHost.Visible = true;
                    overviewHost.BringToFront();
                    foreach (var ui in _profiles)
                        RefreshOverview(ui);
                    SetWindowSettings(false);
                    return;
                }
                overviewHost.Visible = false;
                activePage.Visible = true;
                activePage.BringToFront();
                if (target == "WindowHeader")
                {
                    SetWindowSettings(true);
                    HideModules(activePage);
                    SetModuleSettings(activePage, null);
                    return;
                }
                SetWindowSettings(false);
                if (target == "AdvancedGroup")
                {
                    SetModuleSettings(activePage, null);
                    HideModules(activePage);
                    activeAdvancedToggle.Checked = true;
                    var root = activePage.Controls.Find("ProfileLayout", true).OfType<TableLayoutPanel>().First();
                    root.RowStyles[0].Height = 0;
                    root.RowStyles[1].Height = 0;
                    root.RowStyles[2].Height = 610;
                    root.Height = 610;
                    var advanced = activePage.Controls.Find(target, true).FirstOrDefault();
                    if (advanced is not null)
                        ActiveViewport().ScrollControlIntoView(advanced);
                    return;
                }
                FocusModule(activePage, target);
            };
            navButtons.Add(button);
            nav.Controls.Add(button);
        }

        Panel ActiveViewport() => pages[selectedPage].Controls.Find("Viewport", true).OfType<Panel>().First();

        void SetWindowSettings(bool visible)
        {
            content.RowStyles[0].Height = visible ? 184 : 90;
            for (var index = 0; index < windowHeaders.Count; index++)
                windowHeaders[index].Visible = visible && pages[index].Visible;
        }

        static void ShowOverview(Panel page)
        {
            var advancedToggle = page.Controls.Find("AdvancedToggle", true).OfType<CheckBox>().First();
            if (advancedToggle.Checked)
                advancedToggle.Checked = false;
            RestoreModules(page);
            SetModuleSettings(page, null);
        }

        static void RestoreModules(Panel page)
        {
            var root = page.Controls.Find("ProfileLayout", true).OfType<TableLayoutPanel>().First();
            var placements = new[]
            {
                (Name: "LifeModule", Column: 0, Row: 0),
                (Name: "SpotsModule", Column: 1, Row: 0),
                (Name: "TeleportModule", Column: 0, Row: 1),
                (Name: "SessionGroup", Column: 1, Row: 1)
            };
            root.SuspendLayout();
            foreach (var placement in placements)
            {
                var module = page.Controls.Find(placement.Name, true).First();
                module.Visible = true;
                root.SetCellPosition(module, new TableLayoutPanelCellPosition(placement.Column, placement.Row));
                root.SetColumnSpan(module, 1);
            }
            root.RowStyles[0].Height = 410;
            root.RowStyles[1].Height = 270;
            if (root.RowStyles[2].Height == 0)
                root.Height = 680;
            root.ResumeLayout(true);
        }

        static void FocusModule(Panel page, string target)
        {
            RestoreModules(page);
            SetModuleSettings(page, target);
            var root = page.Controls.Find("ProfileLayout", true).OfType<TableLayoutPanel>().First();
            var modules = new[] { "LifeModule", "SpotsModule", "TeleportModule", "SessionGroup" }
                .Select(name => page.Controls.Find(name, true).First())
                .ToArray();
            var selected = modules.First(module => module.Name == target);
            root.SuspendLayout();
            foreach (var module in modules)
                module.Visible = module == selected;
            root.SetCellPosition(selected, new TableLayoutPanelCellPosition(0, 0));
            root.SetColumnSpan(selected, 2);
            var height = target == "SpotsModule" ? 540 : 450;
            root.RowStyles[0].Height = height;
            root.RowStyles[1].Height = 0;
            root.Height = height;
            root.ResumeLayout(true);
        }

        static void HideModules(Panel page)
        {
            var root = page.Controls.Find("ProfileLayout", true).OfType<TableLayoutPanel>().First();
            foreach (var name in new[] { "LifeModule", "SpotsModule", "TeleportModule", "SessionGroup" })
                page.Controls.Find(name, true).First().Visible = false;
            root.RowStyles[0].Height = 0;
            root.RowStyles[1].Height = 0;
            root.Height = root.RowStyles[2].Height > 0 ? (int)root.RowStyles[2].Height : 0;
        }

        static void SetModuleSettings(Panel page, string? module)
        {
            var settings = new[]
            {
                (Name: "LifeThresholdSettings", Module: "LifeModule"),
                (Name: "LifeActions", Module: "LifeModule"),
                (Name: "SpotsToggleSettings", Module: "SpotsModule"),
                (Name: "SpotsMarkerSettings", Module: "SpotsModule"),
                (Name: "SpotsMarkerTools", Module: "SpotsModule"),
                (Name: "SpotsActionSettings", Module: "SpotsModule"),
                (Name: "SpotsCycleSettings", Module: "SpotsModule"),
                (Name: "TeleportSettings", Module: "TeleportModule"),
                (Name: "SessionSettings", Module: "SessionGroup")
            };
            foreach (var setting in settings)
                page.Controls.Find(setting.Name, true).First().Visible = module == setting.Module;
        }

        void SelectNavigation(Button selected)
        {
            foreach (var button in navButtons)
            {
                button.Tag = button == selected ? "navSelected" : "nav";
                StyleButton(button);
            }
        }
    }

    Control BuildOverviewCard(ProfileUi ui)
    {
        var card = Group(ui.Profile.Name.ToUpperInvariant());
        card.Name = "OverviewCard";
        var target = new Label { AutoSize = true, ForeColor = Muted, AutoEllipsis = true, Dock = DockStyle.Fill };
        var protection = new Label { AutoSize = true, Font = new Font("Arial Narrow", 11F, FontStyle.Bold) };
        var life = new Label { AutoSize = true, ForeColor = Coral, Font = new Font("Arial Narrow", 28F, FontStyle.Bold) };
        var loss = new Label { AutoSize = true, ForeColor = Muted };
        var state = new Label { AutoSize = true, Font = new Font("Arial Narrow", 15F, FontStyle.Bold) };
        var detail = new Label { AutoSize = true, ForeColor = Acid, MaximumSize = new Size(420, 0) };
        var next = new Label { AutoSize = true, ForeColor = Water, MaximumSize = new Size(420, 0) };
        var time = new Label { AutoSize = true, ForeColor = Water, Font = new Font("Arial Narrow", 11F, FontStyle.Bold) };
        var remaining = new Label { AutoSize = true, ForeColor = Water, Font = new Font("Arial Narrow", 11F, FontStyle.Bold) };
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 3,
            Padding = new Padding(12, 10, 12, 10)
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 64));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
        var header = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        header.Controls.Add(protection);
        header.Controls.Add(target);
        layout.Controls.Add(header, 0, 0);
        layout.SetColumnSpan(header, 2);
        layout.Controls.Add(MetricCell("STATUS", state, detail), 0, 1);
        layout.Controls.Add(MetricCell("VIDA", life, loss), 1, 1);
        layout.Controls.Add(MetricCell("PRÓXIMA REAÇÃO", next), 0, 2);
        layout.Controls.Add(MetricCell("TEMPO", time, remaining), 1, 2);
        card.Controls.Add(layout);
        _overviews[ui.Profile] = new OverviewUi(target, protection, life, loss, state, detail, next, time, remaining);
        RefreshOverview(ui);
        return card;
    }

    void RefreshOverview(ProfileUi ui)
    {
        if (!_overviews.TryGetValue(ui.Profile, out var overview))
            return;
        overview.Target.Text = ui.Window.SelectedItem is WindowChoice choice ? choice.Title : "Janela não selecionada";
        overview.Protection.Text = $"● {(ui.Profile.ProtectionEnabled ? "PROTEÇÃO ATIVA" : "PROTEÇÃO DESATIVADA")} • {(UsesRandomTeleport(ui.Profile) ? "RANDOM" : "SAFE")}";
        overview.Protection.ForeColor = ui.Profile.ProtectionEnabled ? Acid : Coral;
        overview.Life.Text = ui.LifePercent.Text;
        overview.Loss.Text = ui.LifeLoss.Text;
        overview.State.Text = ui.StateLabel.Text;
        overview.State.ForeColor = ui.StateLabel.ForeColor;
        overview.Detail.Text = ui.Detected.Text;
        overview.Next.Text = ui.Progress.Text;
        overview.Time.Text = $"Ativo {ui.TimeLabel.Text}";
        overview.Remaining.Text = $"Restante {ui.RemainingTimeLabel.Text}";
    }

    (Panel Page, Control WindowHeader) BuildProfilePage(WindowProfile profile)
    {
        var page = new Panel { Name = "WindowPage", Dock = DockStyle.Fill, BackColor = Ink, ForeColor = Bone };
        var viewport = new Panel { Name = "Viewport", Dock = DockStyle.Fill, AutoScroll = true, BackColor = Ink };
        var root = new TableLayoutPanel
        {
            Name = "ProfileLayout",
            Dock = DockStyle.Top,
            Height = 680,
            ColumnCount = 2,
            RowCount = 3,
            Padding = new Padding(18, 8, 18, 8),
            BackColor = Ink
        };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 410));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 270));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));

        var windowGroup = new RoundedPanel
        {
            Name = "WindowHeader",
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 2, 0, 2),
            Padding = new Padding(4),
            BackColor = InkSoft,
            BorderColor = Color.FromArgb(47, 57, 55)
        };
        var windowCombo = new BrandComboBox
        {
            Name = "WindowSelector",
            DropDownStyle = ComboBoxStyle.DropDownList,
            Dock = DockStyle.Fill,
            Margin = new Padding(0),
            Height = 30
        };
        var windowLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 3,
            RowCount = 1,
            Padding = new Padding(12, 8, 12, 3)
        };
        windowLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 40));
        windowLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 27));
        windowLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33));
        windowLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var windowSelector = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(8, 0, 20, 0), RowCount = 2, ColumnCount = 1 };
        windowSelector.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        windowSelector.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        windowSelector.Controls.Add(new Label
        {
            Text = "JANELA DO JOGO SELECIONADA",
            Dock = DockStyle.Fill,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 8.5F, FontStyle.Bold)
        }, 0, 0);
        windowSelector.Controls.Add(windowCombo, 0, 1);
        var backgroundMode = new BrandToggle
        {
            Text = "SEGUNDO PLANO",
            Checked = profile.BackgroundMode,
            Dock = DockStyle.None,
            Width = 210,
            Anchor = AnchorStyles.Left
        };
        var protectionEnabled = new BrandToggle
        {
            Name = "ProtectionEnabled",
            Text = "PROTEÇÃO ATIVA",
            Checked = profile.ProtectionEnabled,
            Dock = DockStyle.None,
            Width = 210,
            Anchor = AnchorStyles.Left
        };
        windowLayout.Controls.Add(windowSelector, 0, 0);
        windowLayout.Controls.Add(protectionEnabled, 1, 0);
        windowLayout.Controls.Add(backgroundMode, 2, 0);
        windowGroup.Controls.Add(windowLayout);

        var barGroup = Group("♡  BARRA DE VIDA");
        barGroup.Name = "LifeModule";
        var barLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 3,
            Padding = new Padding(10, 14, 10, 7)
        };
        barLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 58));
        barLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 42));
        barLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
        barLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        barLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 82));

        var selectBar = new Button
        {
            Text = "⌖  MARCAR BARRA",
            AutoSize = true,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold)
        };
        var barStatus = StepStatus();
        var preview = new PictureBox
        {
            Dock = DockStyle.Fill,
            Name = "HealthPreview",
            BorderStyle = BorderStyle.FixedSingle,
            SizeMode = PictureBoxSizeMode.Zoom,
            BackColor = Color.FromArgb(18, 22, 21),
            Margin = new Padding(4, 3, 20, 5)
        };
        barLayout.Controls.Add(preview, 0, 1);

        var lifePanel = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 4, ColumnCount = 1 };
        lifePanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 22));
        lifePanel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        lifePanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 20));
        lifePanel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        lifePanel.Controls.Add(new Label
        {
            Text = "VIDA",
            Dock = DockStyle.Fill,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold)
        }, 0, 0);
        var lifePercent = new Label
        {
            Name = "LifePercent",
            Text = "--%",
            AutoSize = true,
            Dock = DockStyle.Fill,
            ForeColor = Coral,
            Font = new Font("Arial Narrow", 40F, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleLeft
        };
        var lifeLoss = new Label { Text = "Queda --", Dock = DockStyle.Fill, ForeColor = Muted };
        var lifeMeter = new BrandProgressBar { Dock = DockStyle.Top, Height = 14, Value = 0 };
        lifePanel.Controls.Add(lifePercent, 0, 1);
        lifePanel.Controls.Add(lifeLoss, 0, 2);
        lifePanel.Controls.Add(lifeMeter, 0, 3);
        barLayout.Controls.Add(lifePanel, 1, 1);

        var thresholdLine = new FlowLayoutPanel
        {
            Name = "LifeThresholdSettings",
            Dock = DockStyle.Fill,
            WrapContents = false,
            FlowDirection = FlowDirection.LeftToRight,
            Padding = new Padding(2, 8, 0, 0)
        };
        thresholdLine.Controls.Add(new Label
        {
            Text = "REAGIR AO CAIR",
            AutoSize = true,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold),
            Margin = new Padding(3, 7, 6, 0)
        });
        var threshold = Number(profile.DropLimitPercent, 1, 90, 1, 70);
        thresholdLine.Controls.Add(threshold);
        thresholdLine.Controls.Add(new Label { Text = "%", AutoSize = true, Margin = new Padding(0, 7, 3, 0) });
        barLayout.Controls.Add(thresholdLine, 0, 2);

        var readNow = new Button
        {
            Text = "↻  ATUALIZAR",
            AutoSize = false,
            Dock = DockStyle.Fill,
            Margin = new Padding(4, 3, 4, 3),
            Font = new Font("Arial Narrow", 8.5F, FontStyle.Bold)
        };
        readNow.Tag = "water";
        var barActions = new TableLayoutPanel
        {
            Name = "LifeActions",
            Dock = DockStyle.None,
            Width = 260,
            Height = 78,
            ColumnCount = 1,
            RowCount = 2,
            Margin = new Padding(4, 1, 4, 1),
            Anchor = AnchorStyles.Left | AnchorStyles.Top
        };
        barActions.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
        barActions.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
        selectBar.Dock = DockStyle.Fill;
        selectBar.AutoSize = false;
        barActions.Controls.Add(selectBar, 0, 0);
        barActions.Controls.Add(readNow, 0, 1);
        barLayout.Controls.Add(barActions, 1, 2);
        thresholdLine.VisibleChanged += (_, _) =>
            barLayout.RowStyles[2].Height = thresholdLine.Visible ? 82 : 0;
        barLayout.SizeChanged += (_, _) =>
            barActions.Width = Math.Min(260, Math.Max(150, barLayout.GetColumnWidths()[1] - 12));
        barGroup.Controls.Add(barLayout);
        root.Controls.Add(barGroup, 0, 0);

        var teleportGroup = Group("◉  TELEPORTE");
        teleportGroup.Name = "TeleportModule";
        var teleportLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
            Padding = new Padding(10, 8, 10, 8)
        };
        teleportLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        teleportLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 92));
        var teleportLine = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(0, 3, 0, 0) };
        teleportLine.Controls.Add(new Label
        {
            Text = "STATUS",
            AutoSize = true,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold),
            Margin = new Padding(3, 8, 14, 0)
        });
        var teleportStatus = StepStatus();
        teleportStatus.Font = new Font("Arial Narrow", 12F, FontStyle.Bold);
        teleportLine.Controls.Add(teleportStatus);
        var teleportMode = new BrandComboBox
        {
            Name = "TeleportMode",
            DropDownStyle = ComboBoxStyle.DropDownList,
            Width = 150
        };
        teleportMode.Items.AddRange(["SAFE", "RANDOM"]);
        teleportMode.SelectedIndex = string.Equals(profile.TeleportMode, "Random", StringComparison.OrdinalIgnoreCase) ? 1 : 0;
        var selectSafeTeleport = MarkerButton("MARCAR SAFE");
        var safeTeleportStatus = StepStatus();
        var selectRandomTeleport = MarkerButton("MARCAR RANDOM");
        var randomTeleportStatus = StepStatus();
        var teleportAction = new TableLayoutPanel
        {
            Name = "TeleportSettings",
            Dock = DockStyle.Fill,
            ColumnCount = 3,
            RowCount = 1,
            Margin = Padding.Empty
        };
        teleportAction.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 28));
        teleportAction.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 36));
        teleportAction.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 36));
        var modeLine = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false };
        modeLine.Controls.Add(new Label
        {
            Text = "USAR TELEPORTE",
            AutoSize = true,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold)
        });
        modeLine.Controls.Add(teleportMode);
        var safeLine = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false };
        safeLine.Controls.Add(selectSafeTeleport);
        safeLine.Controls.Add(safeTeleportStatus);
        var randomLine = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false };
        randomLine.Controls.Add(selectRandomTeleport);
        randomLine.Controls.Add(randomTeleportStatus);
        teleportAction.Controls.Add(modeLine, 0, 0);
        teleportAction.Controls.Add(safeLine, 1, 0);
        teleportAction.Controls.Add(randomLine, 2, 0);
        teleportAction.Height = 88;
        teleportLayout.SizeChanged += (_, _) =>
            teleportAction.Width = Math.Min(940, Math.Max(560, teleportLayout.ClientSize.Width - 20));
        teleportAction.Dock = DockStyle.None;
        teleportAction.Anchor = AnchorStyles.Left | AnchorStyles.Top;
        teleportLayout.Controls.Add(teleportLine, 0, 0);
        teleportLayout.Controls.Add(teleportAction, 0, 1);
        teleportAction.VisibleChanged += (_, _) =>
            teleportLayout.RowStyles[1].Height = teleportAction.Visible ? 92 : 0;
        teleportGroup.Controls.Add(teleportLayout);
        root.Controls.Add(teleportGroup, 0, 1);

        var advancedToggle = new CheckBox
        {
            Name = "AdvancedToggle",
            Text = "⚙  OPÇÕES AVANÇADAS",
            AutoSize = true,
            Margin = new Padding(8, 12, 3, 3),
            Visible = false
        };
        var advancedGroup = Group("Opções avançadas");
        advancedGroup.Name = "AdvancedGroup";
        advancedGroup.Dock = DockStyle.None;
        advancedGroup.Height = 560;
        advancedGroup.Visible = false;
        var advancedContent = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 1,
            Padding = new Padding(8, 12, 8, 6),
            Margin = Padding.Empty
        };
        advancedContent.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 42));
        advancedContent.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 58));
        var advanced = VerticalPanel(false);
        advanced.Padding = new Padding(8, 4, 18, 4);
        var advancedRoute = VerticalPanel(false);
        advancedRoute.Padding = new Padding(18, 4, 8, 4);
        var delay = Number(profile.TeleportToSpotDelayMs, 100, 10_000, 100, 90);
        var teleportRetries = Number(profile.TeleportRetryCount, 1, 20, 1, 90);
        var rearmDelay = Number(profile.RearmDelayMs, 1000, 60_000, 500, 90);
        var stableTime = Number(profile.StableTimeMs, 500, 10_000, 500, 90);
        var spotSimilarity = Number(profile.SpotWindowMinimumSimilarity, 50, 100, 1, 90);
        advanced.Controls.Add(OptionLine("Intervalo entre cliques (ms):", delay));
        advanced.Controls.Add(OptionLine("Tentativas no botão Teleportar:", teleportRetries));
        advanced.Controls.Add(OptionLine("Semelhança mínima da janela de spots (%):", spotSimilarity));
        advanced.Controls.Add(OptionLine("Espera mínima após reação (ms):", rearmDelay));
        advanced.Controls.Add(OptionLine("Barra estável por (ms):", stableTime));
        advanced.Controls.Add(new Label { Text = "BARRA DE VIDA", AutoSize = true, ForeColor = Gold, Margin = new Padding(3, 10, 3, 2) });
        advanced.Controls.Add(barStatus);
        advancedContent.Controls.Add(advanced, 0, 0);
        advancedContent.Controls.Add(advancedRoute, 1, 0);
        advancedGroup.Controls.Add(advancedContent);
        var advancedArea = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            AutoSize = true,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            Padding = new Padding(4, 0, 4, 0)
        };
        advancedArea.Controls.Add(advancedToggle);
        advancedArea.Controls.Add(advancedGroup);

        var spotsGroup = Group("⌖  ROTA DE SPOTS");
        spotsGroup.Name = "SpotsModule";
        var spotsLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 7,
            Padding = new Padding(10, 4, 10, 1)
        };
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        spotsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        var useSpots = new BrandToggle
        {
            Name = "UseSpots",
            Text = "SPOTS",
            Checked = profile.UseSpots,
            Dock = DockStyle.None,
            Width = 155,
            Height = 34,
            Margin = new Padding(3, 1, 3, 1)
        };

        var markers = new TableLayoutPanel { Name = "SpotsMarkerSettings", Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Margin = Padding.Empty };
        markers.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 34));
        markers.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33));
        markers.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33));
        markers.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var spotWindowLine = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Margin = Padding.Empty };
        var selectSpotWindow = MarkerButton("JANELA DE SPOTS");
        var spotWindowStatus = StepStatus();
        spotWindowStatus.Margin = new Padding(3, 2, 3, 0);
        spotWindowLine.Controls.Add(selectSpotWindow);
        spotWindowLine.Controls.Add(spotWindowStatus);

        var spotMenuLine = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Margin = Padding.Empty };
        var selectSpotMenu = MarkerButton("ABRIR MENU");
        var spotMenuStatus = StepStatus();
        spotMenuStatus.Margin = new Padding(3, 2, 3, 0);
        spotMenuLine.Controls.Add(selectSpotMenu);
        spotMenuLine.Controls.Add(spotMenuStatus);

        var confirmTeleportLine = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Margin = Padding.Empty };
        var selectConfirmTeleport = MarkerButton("BOTÃO TELEPORTAR");
        var confirmTeleportStatus = StepStatus();
        confirmTeleportStatus.Margin = new Padding(3, 2, 3, 0);
        confirmTeleportLine.Controls.Add(selectConfirmTeleport);
        confirmTeleportLine.Controls.Add(confirmTeleportStatus);
        markers.Controls.Add(spotWindowLine, 0, 0);
        markers.Controls.Add(spotMenuLine, 1, 0);
        markers.Controls.Add(confirmTeleportLine, 2, 0);
        var markerTools = new TableLayoutPanel { Name = "SpotsMarkerTools", Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Margin = Padding.Empty };
        markerTools.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 40));
        markerTools.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 35));
        markerTools.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25));
        var spotMatch = new Label
        {
            Text = "Semelhança atual: --",
            Dock = DockStyle.Fill,
            AutoEllipsis = true,
            TextAlign = ContentAlignment.MiddleLeft,
            Margin = new Padding(3, 0, 6, 0)
        };
        var showMarks = new Button
        {
            Text = "MOSTRAR MARCAÇÕES",
            AutoSize = false,
            Dock = DockStyle.Fill,
            Height = 34,
            Margin = new Padding(3, 1, 3, 1),
            Font = new Font("Arial Narrow", 8F, FontStyle.Bold)
        };
        markerTools.Controls.Add(spotMatch, 0, 0);
        markerTools.Controls.Add(showMarks, 1, 0);
        markerTools.SetColumnSpan(showMarks, 2);
        spotsLayout.Controls.Add(markers, 0, 1);
        spotsLayout.Controls.Add(markerTools, 0, 2);

        var useSpotsHeader = new TableLayoutPanel { Name = "SpotsToggleSettings", Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Margin = Padding.Empty };
        useSpotsHeader.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        useSpotsHeader.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        useSpotsHeader.Controls.Add(new Label
        {
            Text = "USAR SPOTS",
            AutoSize = true,
            Anchor = AnchorStyles.Right,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold),
            Margin = new Padding(3, 8, 8, 0)
        }, 0, 0);
        useSpots.Text = string.Empty;
        useSpots.Width = 64;
        useSpotsHeader.Controls.Add(useSpots, 1, 0);
        spotsLayout.Controls.Add(useSpotsHeader, 0, 0);

        var routeHeaders = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Margin = Padding.Empty };
        routeHeaders.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70));
        routeHeaders.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        routeHeaders.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70));
        routeHeaders.Controls.Add(RouteHeader("ORDEM"), 0, 0);
        routeHeaders.Controls.Add(RouteHeader("NOME DO SPOT"), 1, 0);
        routeHeaders.Controls.Add(RouteHeader("ATIVO"), 2, 0);
        spotsLayout.Controls.Add(routeHeaders, 0, 3);

        var spots = new SpotListBox
        {
            Name = "SpotsList",
            Dock = DockStyle.Fill,
            CheckOnClick = true,
            IntegralHeight = false,
            Font = new Font("Bahnschrift Condensed", 10.5F),
            ItemHeight = 30
        };
        spotsLayout.Controls.Add(spots, 0, 4);

        var spotButtons = new TableLayoutPanel { Name = "SpotsActionSettings", Dock = DockStyle.Fill, ColumnCount = 6, RowCount = 1, Margin = Padding.Empty };
        foreach (var width in new[] { 18F, 23F, 19F, 8F, 8F, 24F })
            spotButtons.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, width));
        var addSpot = SmallButton("＋");
        var updateSpot = SmallButton("↕ POSIÇÃO");
        var renameSpot = SmallButton("✎ NOME");
        var moveUp = SmallButton("▲");
        var moveDown = SmallButton("▼");
        moveUp.AutoSize = moveDown.AutoSize = false;
        var removeSpot = SmallButton("REMOVER");
        removeSpot.Tag = "danger";
        var spotActions = new[] { addSpot, updateSpot, renameSpot, moveUp, moveDown, removeSpot };
        for (var index = 0; index < spotActions.Length; index++)
        {
            spotActions[index].AutoSize = false;
            spotActions[index].Dock = DockStyle.Fill;
            spotActions[index].Margin = new Padding(3, 2, 3, 2);
            spotActions[index].Font = new Font("Arial Narrow", 8F, FontStyle.Bold);
            spotButtons.Controls.Add(spotActions[index], index, 0);
        }
        spotsLayout.Controls.Add(spotButtons, 0, 5);

        var cyclesLine = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, Padding = new Padding(0, 5, 0, 0) };
        cyclesLine.Controls.Add(new Label
        {
            Text = "REPETIR ROTA",
            AutoSize = true,
            ForeColor = Muted,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold),
            Margin = new Padding(3, 7, 12, 0)
        });
        var cycles = Number(profile.CycleCount, 1, 999, 1, 70);
        cyclesLine.Controls.Add(cycles);
        cyclesLine.Controls.Add(new Label
        {
            Text = "vezes",
            AutoSize = true,
            Font = new Font("Arial Narrow", 9F),
            Margin = new Padding(0, 7, 3, 0)
        });
        var resetSpots = SmallButton("↻ REINICIAR SPOTS");
        resetSpots.AutoSize = false;
        resetSpots.Width = 170;
        resetSpots.Height = 30;
        resetSpots.Font = new Font("Arial Narrow", 8.5F, FontStyle.Bold);
        resetSpots.Margin = new Padding(3, 2, 3, 2);
        var cyclesRow = new TableLayoutPanel { Name = "SpotsCycleSettings", Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Margin = Padding.Empty };
        cyclesRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        cyclesRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        cyclesRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        cyclesLine.AutoSize = true;
        cyclesLine.Dock = DockStyle.None;
        cyclesRow.Controls.Add(cyclesLine, 0, 0);
        cyclesRow.Controls.Add(resetSpots, 1, 0);
        spotsLayout.Controls.Add(cyclesRow, 0, 6);
        useSpotsHeader.VisibleChanged += (_, _) => spotsLayout.RowStyles[0].Height = useSpotsHeader.Visible ? 34 : 0;
        spotButtons.VisibleChanged += (_, _) => spotsLayout.RowStyles[5].Height = spotButtons.Visible ? 42 : 0;
        cyclesRow.VisibleChanged += (_, _) => spotsLayout.RowStyles[6].Height = cyclesRow.Visible ? 34 : 0;
        spotButtons.SizeChanged += (_, _) =>
        {
            var compactActions = spotButtons.ClientSize.Width < 620;
            addSpot.Text = compactActions ? "＋" : "＋ ADICIONAR";
            updateSpot.Text = compactActions ? "POSIÇÃO" : "↕ POSIÇÃO";
            renameSpot.Text = compactActions ? "NOME" : "✎ NOME";
            resetSpots.Text = spotButtons.ClientSize.Width < 700 ? "↻ REINICIAR" : "↻ REINICIAR SPOTS";
        };
        spotsGroup.Controls.Add(spotsLayout);
        root.Controls.Add(spotsGroup, 1, 0);

        markers.VisibleChanged += (_, _) => spotsLayout.RowStyles[1].Height = markers.Visible ? 72 : 0;
        markerTools.VisibleChanged += (_, _) => spotsLayout.RowStyles[2].Height = markerTools.Visible ? 38 : 0;

        var stateGroup = Group("⌁  SESSÃO");
        stateGroup.Name = "SessionGroup";
        var stateFlow = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 2,
            Padding = new Padding(10, 6, 10, 6)
        };
        stateFlow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        stateFlow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        stateFlow.RowStyles.Add(new RowStyle(SizeType.Percent, 64));
        stateFlow.RowStyles.Add(new RowStyle(SizeType.Percent, 36));
        var state = new Label { Text = "PARADA", AutoSize = true, ForeColor = Acid, Font = new Font("Arial Narrow", 13F, FontStyle.Bold) };
        var progress = new Label { AutoSize = true, ForeColor = Water, MaximumSize = new Size(360, 0) };
        var detected = new Label { Text = "Barra ainda não calibrada.", AutoSize = true, ForeColor = Acid, MaximumSize = new Size(360, 0) };
        var captureStatus = new Label { Text = "Captura: parada", AutoSize = true };
        var stateCell = MetricCell("STATUS", state, detected);
        var progressCell = MetricCell("PRÓXIMA REAÇÃO", progress);

        var sessionLine = new FlowLayoutPanel { AutoSize = true, WrapContents = false };
        sessionLine.Controls.Add(new Label
        {
            Text = "Limite da sessão:",
            AutoSize = true,
            Margin = new Padding(3, 7, 3, 0)
        });
        var sessionHours = Number(profile.SessionLimitMinutes / 60, 0, 168, 1, 60);
        var sessionMinutes = Number(profile.SessionLimitMinutes % 60, 0, 59, 1, 60);
        sessionLine.Controls.Add(sessionHours);
        sessionLine.Controls.Add(new Label { Text = "h", AutoSize = true, Margin = new Padding(0, 7, 3, 0) });
        sessionLine.Controls.Add(sessionMinutes);
        sessionLine.Controls.Add(new Label { Text = "min", AutoSize = true, Margin = new Padding(0, 7, 3, 0) });
        var sessionTime = new Label
        {
            Text = "00:00:00",
            AutoSize = true,
            ForeColor = Water,
            Font = new Font("Arial Narrow", 11F, FontStyle.Bold)
        };
        var remainingTime = new Label
        {
            Text = "01:00:00",
            AutoSize = true,
            ForeColor = Water,
            Font = new Font("Arial Narrow", 11F, FontStyle.Bold)
        };
        var timeCell = MetricCell("TEMPO ATIVO", sessionTime);
        var remainingCell = MetricCell("RESTANTE", remainingTime);
        stateFlow.Controls.Add(stateCell, 0, 0);
        stateFlow.Controls.Add(progressCell, 1, 0);
        stateFlow.Controls.Add(timeCell, 0, 1);
        stateFlow.Controls.Add(remainingCell, 1, 1);

        var stateButtons = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Margin = Padding.Empty };
        var rearm = SmallButton("⌖ RECALIBRAR");
        var reset = SmallButton("↻ REINICIAR");
        var test = SmallButton("▷ TESTAR");
        var backgroundTest = SmallButton("Testar clique em 2º plano");
        var backgroundCaptureTest = SmallButton("Testar captura em 2º plano");
        test.Tag = "water";
        stateButtons.Controls.AddRange([rearm, reset, test]);
        var sessionSettings = new FlowLayoutPanel
        {
            Name = "SessionSettings",
            Dock = DockStyle.Fill,
            WrapContents = false,
            Padding = new Padding(8, 5, 8, 2)
        };
        sessionSettings.Controls.Add(sessionLine);
        sessionSettings.Controls.Add(stateButtons);
        var sessionLayout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
        sessionLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        sessionLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 62));
        sessionLayout.Controls.Add(stateFlow, 0, 0);
        sessionLayout.Controls.Add(sessionSettings, 0, 1);
        sessionSettings.VisibleChanged += (_, _) =>
            sessionLayout.RowStyles[1].Height = sessionSettings.Visible ? 62 : 0;
        advancedRoute.Controls.Add(new Label { Text = "TESTES DE COMPATIBILIDADE", AutoSize = true, ForeColor = Gold, Margin = new Padding(3, 12, 3, 2) });
        var compatibilityTests = new FlowLayoutPanel { AutoSize = true, WrapContents = false };
        compatibilityTests.Controls.AddRange([backgroundTest, backgroundCaptureTest]);
        advancedRoute.Controls.Add(compatibilityTests);
        advancedRoute.Controls.Add(captureStatus);
        stateGroup.Controls.Add(sessionLayout);
        root.Controls.Add(stateGroup, 1, 1);

        root.Controls.Add(advancedArea, 0, 2);
        root.SetColumnSpan(advancedArea, 2);
        root.SizeChanged += (_, _) =>
        {
            ResizeAdvanced();
            var compact = root.ClientSize.Width < 1100;
            selectBar.Text = compact ? "⌖  MARCAR" : "⌖  MARCAR BARRA";
        };
        viewport.Controls.Add(root);
        page.Controls.Add(viewport);

        var ui = new ProfileUi(
            profile,
            windowCombo,
            barStatus,
            teleportStatus,
            safeTeleportStatus,
            randomTeleportStatus,
            spotWindowStatus,
            spotMenuStatus,
            confirmTeleportStatus,
            spotMatch,
            preview,
            spots,
            state,
            progress,
            detected,
            captureStatus,
            sessionTime,
            lifeMeter,
            lifePercent,
            lifeLoss,
            remainingTime);
        _profiles.Add(ui);
        RefreshProfileUi(ui);
        if (!profile.ProtectionEnabled)
            SetProfileStatus(ui, "Desativada", "Proteção desligada para esta janela.");

        windowCombo.SelectedIndexChanged += (_, _) =>
        {
            if (_loading || windowCombo.SelectedItem is not WindowChoice choice)
                return;
            profile.WindowTitle = choice.Title;
            profile.ProcessName = choice.ProcessName;
            ui.DisposeCapture();
            if (_running)
                PauseProfile(ui, "Janela alterada. Inicie novamente.");
            RefreshOverview(ui);
            TrySave();
        };
        backgroundMode.CheckedChanged += (_, _) =>
        {
            if (_running)
            {
                if (backgroundMode.Checked != profile.BackgroundMode)
                {
                    backgroundMode.Checked = profile.BackgroundMode;
                    MessageBox.Show(this, "Pare a proteção antes de alterar o modo de captura.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                return;
            }
            profile.BackgroundMode = backgroundMode.Checked;
            ui.CaptureStatus.Text = backgroundMode.Checked
                ? "Captura: segundo plano será iniciado com a proteção"
                : "Captura: tela visível (modo compatibilidade)";
            TrySave();
        };
        protectionEnabled.CheckedChanged += async (_, _) =>
        {
            protectionEnabled.Enabled = false;
            try
            {
                await SetProfileProtectionAsync(ui, protectionEnabled.Checked);
            }
            finally
            {
                protectionEnabled.Enabled = true;
            }
        };
        selectBar.Click += (_, _) => SelectHealthBar(ui);
        readNow.Click += async (_, _) => await ReadHealthNowAsync(ui);
        selectSafeTeleport.Click += (_, _) => SelectTeleport(ui, false);
        selectRandomTeleport.Click += (_, _) => SelectTeleport(ui, true);
        teleportMode.SelectedIndexChanged += (_, _) =>
        {
            var selected = teleportMode.SelectedIndex == 1 ? "Random" : "Safe";
            if (string.Equals(profile.TeleportMode, selected, StringComparison.OrdinalIgnoreCase))
                return;
            if (_running)
            {
                teleportMode.SelectedIndex = string.Equals(profile.TeleportMode, "Random", StringComparison.OrdinalIgnoreCase) ? 1 : 0;
                MessageBox.Show(this, "Pare a proteção antes de trocar o tipo de teleporte.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            profile.TeleportMode = selected;
            RefreshProfileUi(ui);
            TrySave();
        };
        selectSpotWindow.Click += (_, _) => SelectSpotWindow(ui);
        selectSpotMenu.Click += (_, _) => SelectSpotMenu(ui);
        selectConfirmTeleport.Click += (_, _) => SelectConfirmTeleport(ui);
        showMarks.Click += (_, _) => ShowMarks(ui);
        threshold.ValueChanged += (_, _) => { profile.DropLimitPercent = threshold.Value; TrySave(); };
        cycles.ValueChanged += (_, _) => { profile.CycleCount = (int)cycles.Value; UpdateProgress(ui); TrySave(); };
        sessionHours.ValueChanged += (_, _) => SaveSessionLimit();
        sessionMinutes.ValueChanged += (_, _) => SaveSessionLimit();
        useSpots.CheckedChanged += (_, _) =>
        {
            if (_running)
            {
                useSpots.Checked = profile.UseSpots;
                MessageBox.Show(this, "Pare a proteção antes de alterar o uso de spots.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            profile.UseSpots = useSpots.Checked;
            ui.NextSpotIndex = Math.Max(0, FindEnabledSpot(profile.Spots));
            ui.CompletedCycles = 0;
            if (ui.State == ProfileState.Completed)
                ui.State = ProfileState.Stopped;
            UpdateProgress(ui);
            TrySave();
        };
        spots.ItemCheck += (_, eventArgs) =>
        {
            if (ui.UpdatingSpotChecks || eventArgs.Index < 0 || eventArgs.Index >= profile.Spots.Count)
                return;

            var enabled = eventArgs.NewValue == CheckState.Checked;
            var current = profile.Spots[eventArgs.Index];
            var remaining = profile.Spots.Count(item => item.Enabled)
                            - (current.Enabled ? 1 : 0)
                            + (enabled ? 1 : 0);
            if (remaining == 0)
            {
                eventArgs.NewValue = eventArgs.CurrentValue;
                MessageBox.Show(this,
                    "Mantenha ao menos um spot ativo. Para usar somente o teleporte, desative o modo de spots.",
                    Text,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            current.Enabled = enabled;
            if (ui.NextSpotIndex < 0
                || ui.NextSpotIndex >= profile.Spots.Count
                || !profile.Spots[ui.NextSpotIndex].Enabled)
                ui.NextSpotIndex = FindEnabledSpot(profile.Spots, ui.NextSpotIndex + 1);
            UpdateProgress(ui);
            TrySave();
            SetStatus($"{current.Name} {(enabled ? "ativado" : "desativado")}; alteração válida para a próxima reação.");
        };
        delay.ValueChanged += (_, _) => { profile.TeleportToSpotDelayMs = (int)delay.Value; TrySave(); };
        teleportRetries.ValueChanged += (_, _) => { profile.TeleportRetryCount = (int)teleportRetries.Value; TrySave(); };
        spotSimilarity.ValueChanged += (_, _) => { profile.SpotWindowMinimumSimilarity = spotSimilarity.Value; TrySave(); };
        rearmDelay.ValueChanged += (_, _) => { profile.RearmDelayMs = (int)rearmDelay.Value; TrySave(); };
        stableTime.ValueChanged += (_, _) => { profile.StableTimeMs = (int)stableTime.Value; TrySave(); };
        advancedToggle.CheckedChanged += (_, _) =>
        {
            ResizeAdvanced();
            advancedGroup.Visible = advancedToggle.Checked;
            root.RowStyles[2].Height = advancedToggle.Checked ? 610 : 0;
            root.Height = advancedToggle.Checked ? 1290 : 680;
        };

        addSpot.Click += (_, _) => AddSpot(ui);
        updateSpot.Click += (_, _) => UpdateSpot(ui);
        renameSpot.Click += (_, _) => RenameSpot(ui);
        moveUp.Click += (_, _) => MoveSpot(ui, -1);
        moveDown.Click += (_, _) => MoveSpot(ui, 1);
        removeSpot.Click += (_, _) => RemoveSpot(ui);
        resetSpots.Click += (_, _) => ResetSpots(ui);
        rearm.Click += async (_, _) => await RearmProfileAsync(ui);
        reset.Click += async (_, _) => await ResetSequenceAsync(ui);
        test.Click += async (_, _) => await TestReactionAsync(ui);
        backgroundTest.Click += async (_, _) => await TestBackgroundClickAsync(ui);
        backgroundCaptureTest.Click += async (_, _) => await TestBackgroundCaptureAsync(ui);
        return (page, windowGroup);

        void ResizeAdvanced()
        {
            var width = Math.Max(500, root.ClientSize.Width - 42);
            advancedGroup.Width = width;
        }

        void SaveSessionLimit()
        {
            if (sessionHours.Value == 168 && sessionMinutes.Value > 0)
            {
                sessionMinutes.Value = 0;
                return;
            }
            var totalMinutes = (int)sessionHours.Value * 60 + (int)sessionMinutes.Value;
            if (totalMinutes < 1)
            {
                sessionMinutes.Value = 1;
                return;
            }
            profile.SessionLimitMinutes = totalMinutes;
            UpdateTime(ui);
            TrySave();
        }

    }

    static FlowLayoutPanel VerticalPanel(bool scroll = true) => new()
    {
        Dock = DockStyle.Fill,
        FlowDirection = FlowDirection.TopDown,
        WrapContents = false,
        AutoScroll = scroll
    };

    static ModuleCard Group(string text) => new()
    {
        Text = text,
        Dock = DockStyle.Fill,
        Margin = new Padding(6),
        Padding = new Padding(12, 30, 12, 12),
        BackColor = InkSoft,
        ForeColor = Bone,
    };

    static Label StepStatus() => new()
    {
        Text = "Não configurado",
        AutoSize = true,
        ForeColor = Coral,
        Font = new Font("Bahnschrift Condensed", 8.5F),
        Margin = new Padding(10, 7, 3, 0)
    };

    static Button SmallButton(string text) => new() { Text = text, AutoSize = true, MinimumSize = new Size(0, 34) };

    static Button MarkerButton(string text) => new()
    {
        Text = text,
        AutoSize = true,
        MinimumSize = new Size(135, 32),
        Margin = Padding.Empty,
        Font = new Font("Arial Narrow", 8F, FontStyle.Bold)
    };

    static NumericUpDown Number(decimal value, decimal min, decimal max, decimal increment, int width) => new()
    {
        Minimum = min,
        Maximum = max,
        Increment = increment,
        Value = Math.Clamp(value, min, max),
        Width = width
    };

    static FlowLayoutPanel OptionLine(string label, Control control)
    {
        var line = new FlowLayoutPanel { AutoSize = true, WrapContents = false };
        line.Controls.Add(new Label { Text = label, AutoSize = true, Width = 280, Margin = new Padding(3, 7, 3, 0) });
        line.Controls.Add(control);
        return line;
    }

    static FlowLayoutPanel MetricCell(string caption, params Control[] values)
    {
        var cell = VerticalPanel(false);
        cell.Padding = new Padding(8, 2, 8, 2);
        cell.Controls.Add(new Label
        {
            Text = caption,
            AutoSize = true,
            ForeColor = Gold,
            Font = new Font("Arial Narrow", 9F, FontStyle.Bold)
        });
        foreach (var value in values)
        {
            value.Margin = new Padding(3, 4, 3, 0);
            cell.Controls.Add(value);
        }
        return cell;
    }

    static Label RouteHeader(string text) => new()
    {
        Text = text,
        Dock = DockStyle.Fill,
        ForeColor = Muted,
        Font = new Font("Arial Narrow", 8F, FontStyle.Bold),
        TextAlign = ContentAlignment.MiddleLeft,
        Padding = new Padding(8, 0, 0, 0)
    };

    static Image? LoadBrandLogo()
    {
        using var stream = typeof(MainForm).Assembly.GetManifestResourceStream(
            "ControlarTela.Assets.ronaldinho-wordmark-gold.png");
        return stream is null ? null : new Bitmap(stream);
    }

    static void ApplyBrandTheme(Control root)
    {
        foreach (Control control in root.Controls)
        {
            switch (control)
            {
                case GroupBox group:
                    group.BackColor = InkSoft;
                    group.ForeColor = Bone;
                    break;
                case RoundedPanel rounded:
                    rounded.BackColor = InkSoft;
                    rounded.ForeColor = Bone;
                    break;
                case TabPage page:
                    page.BackColor = Ink;
                    page.ForeColor = Bone;
                    break;
                case Button button:
                    StyleButton(button);
                    break;
                case BrandToggle toggle:
                    toggle.BackColor = toggle.Parent?.BackColor ?? InkSoft;
                    toggle.ForeColor = Bone;
                    break;
                case CheckBox checkBox:
                    checkBox.BackColor = checkBox.Parent?.BackColor ?? Ink;
                    checkBox.ForeColor = Bone;
                    checkBox.FlatStyle = FlatStyle.Flat;
                    break;
                case ComboBox or NumericUpDown or TextBox or CheckedListBox:
                    control.BackColor = Color.FromArgb(18, 22, 21);
                    control.ForeColor = Bone;
                    break;
                case Label label when label.ForeColor == Color.DarkRed:
                    label.ForeColor = Coral;
                    break;
                case Label label when label.ForeColor == Color.DarkGreen:
                    label.ForeColor = Acid;
                    break;
                case Label label when label.ForeColor == SystemColors.ControlText:
                    label.ForeColor = Bone;
                    break;
                case FlowLayoutPanel or TableLayoutPanel or Panel:
                    control.BackColor = control.Parent?.BackColor ?? Ink;
                    control.ForeColor = Bone;
                    break;
            }
            ApplyBrandTheme(control);
        }
    }

    static void StyleButton(Button button)
    {
        button.FlatStyle = FlatStyle.Flat;
        button.FlatAppearance.BorderSize = 1;
        button.Cursor = Cursors.Hand;
        button.Padding = new Padding(8, 3, 8, 3);
        var role = button.Tag as string;
        button.BackColor = role switch
        {
            "primary" => Acid,
            "badge" => Color.FromArgb(31, 45, 10),
            "tabSelected" => InkSoft,
            "tab" => Ink,
            "navSelected" => Color.FromArgb(19, 25, 24),
            "nav" => Color.FromArgb(9, 13, 14),
            "danger" => InkSoft,
            _ => InkSoft
        };
        button.ForeColor = role switch
        {
            "primary" => Ink,
            "danger" => Coral,
            "water" => Water,
            "badge" => Acid,
            "tabSelected" => Gold,
            "tab" => Muted,
            "navSelected" => Gold,
            "nav" => Muted,
            _ => Gold
        };
        button.FlatAppearance.BorderColor = button.ForeColor;
        if (role is "badge")
            button.Padding = new Padding(6, 0, 6, 0);
        if (role is "tab" or "tabSelected" or "nav" or "navSelected")
            button.FlatAppearance.BorderSize = role == "tabSelected" ? 1 : 0;
        if (role == "navSelected")
            button.FlatAppearance.BorderSize = 1;
    }

    sealed class BrandComboBox : ComboBox
    {
        public BrandComboBox()
        {
            DrawMode = DrawMode.OwnerDrawFixed;
            FlatStyle = FlatStyle.Flat;
            BackColor = Color.FromArgb(16, 21, 20);
            ForeColor = Bone;
            ItemHeight = 24;
        }

        protected override void OnDrawItem(DrawItemEventArgs eventArgs)
        {
            if (eventArgs.Index < 0)
                return;
            using var fill = new SolidBrush((eventArgs.State & DrawItemState.Selected) != 0
                ? Color.FromArgb(24, 31, 29)
                : Color.FromArgb(16, 21, 20));
            eventArgs.Graphics.FillRectangle(fill, eventArgs.Bounds);
            var text = GetItemText(Items[eventArgs.Index]);
            TextRenderer.DrawText(eventArgs.Graphics, text, Font,
                new Rectangle(eventArgs.Bounds.X + 8, eventArgs.Bounds.Y, Math.Max(1, eventArgs.Bounds.Width - 12), eventArgs.Bounds.Height),
                Bone, TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
        }
    }

    sealed class SpotListBox : CheckedListBox
    {
        public SpotListBox()
        {
            DrawMode = DrawMode.OwnerDrawFixed;
            BorderStyle = BorderStyle.None;
            BackColor = InkSoft;
            ForeColor = Bone;
        }

        protected override void OnDrawItem(DrawItemEventArgs eventArgs)
        {
            if (eventArgs.Index < 0 || eventArgs.Index >= Items.Count)
                return;

            var graphics = eventArgs.Graphics;
            graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            var bounds = new Rectangle(eventArgs.Bounds.X + 2, eventArgs.Bounds.Y + 2,
                Math.Max(1, eventArgs.Bounds.Width - 5), Math.Max(1, eventArgs.Bounds.Height - 4));
            using var path = RoundedPath(bounds, 6);
            using var fill = new SolidBrush((eventArgs.State & DrawItemState.Selected) != 0
                ? Color.FromArgb(24, 31, 29)
                : Color.FromArgb(16, 21, 20));
            using var border = new Pen(Color.FromArgb(47, 57, 55));
            graphics.FillPath(fill, path);
            graphics.DrawPath(border, path);

            var raw = Items[eventArgs.Index]?.ToString() ?? string.Empty;
            var separator = raw.IndexOf('.');
            var name = separator >= 0 && separator + 1 < raw.Length ? raw[(separator + 1)..].Trim() : raw;
            TextRenderer.DrawText(graphics, "⠿", Font, new Rectangle(bounds.X + 10, bounds.Y, 24, bounds.Height), Muted,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding);
            TextRenderer.DrawText(graphics, (eventArgs.Index + 1).ToString(), Font,
                new Rectangle(bounds.X + 38, bounds.Y, 30, bounds.Height), Bone,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding);
            TextRenderer.DrawText(graphics, name, Font,
                new Rectangle(bounds.X + 78, bounds.Y, Math.Max(1, bounds.Width - 142), bounds.Height), Bone,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPadding);

            var toggle = new Rectangle(bounds.Right - 48, bounds.Y + Math.Max(2, (bounds.Height - 18) / 2), 38, 18);
            var isChecked = GetItemChecked(eventArgs.Index);
            using var togglePath = RoundedPath(toggle, 9);
            using var toggleFill = new SolidBrush(isChecked ? Acid : Color.FromArgb(53, 61, 59));
            graphics.FillPath(toggleFill, togglePath);
            var knobX = isChecked ? toggle.Right - 16 : toggle.X + 3;
            using var knob = new SolidBrush(Bone);
            graphics.FillEllipse(knob, knobX, toggle.Y + 3, 12, 12);
        }

        protected override void OnItemCheck(ItemCheckEventArgs eventArgs)
        {
            base.OnItemCheck(eventArgs);
            if (IsHandleCreated)
                BeginInvoke(Invalidate);
        }
    }

    sealed class RoundedPanel : Panel
    {
        public Color BorderColor { get; set; } = Color.FromArgb(55, 64, 62);

        public RoundedPanel()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.OptimizedDoubleBuffer, true);
        }

        protected override void OnPaintBackground(PaintEventArgs eventArgs)
        {
            eventArgs.Graphics.Clear(Parent?.BackColor ?? Ink);
            eventArgs.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using var path = RoundedPath(new Rectangle(1, 1, Math.Max(1, Width - 3), Math.Max(1, Height - 3)), 14);
            using var fill = new SolidBrush(BackColor);
            using var border = new Pen(BorderColor);
            eventArgs.Graphics.FillPath(fill, path);
            eventArgs.Graphics.DrawPath(border, path);
        }
    }

    sealed class ModuleCard : GroupBox
    {
        readonly Font _titleFont = new("Arial Narrow", 14F, FontStyle.Bold);

        public ModuleCard()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        }

        protected override void OnPaint(PaintEventArgs eventArgs)
        {
            eventArgs.Graphics.Clear(Parent?.BackColor ?? Ink);
            eventArgs.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using var path = RoundedPath(new Rectangle(1, 1, Math.Max(1, Width - 3), Math.Max(1, Height - 3)), 16);
            using var fill = new SolidBrush(BackColor);
            eventArgs.Graphics.FillPath(fill, path);
            var titleHeight = (int)Math.Ceiling(_titleFont.GetHeight(eventArgs.Graphics)) + 8;
            TextRenderer.DrawText(eventArgs.Graphics, Text, _titleFont,
                new Rectangle(20, 8, Math.Max(0, Width - 40), titleHeight), ForeColor,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
                _titleFont.Dispose();
            base.Dispose(disposing);
        }
    }

    static System.Drawing.Drawing2D.GraphicsPath RoundedPath(Rectangle bounds, int radius)
    {
        var diameter = radius * 2;
        var path = new System.Drawing.Drawing2D.GraphicsPath();
        path.AddArc(bounds.Left, bounds.Top, diameter, diameter, 180, 90);
        path.AddArc(bounds.Right - diameter, bounds.Top, diameter, diameter, 270, 90);
        path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(bounds.Left, bounds.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    sealed class BrandToggle : CheckBox
    {
        public BrandToggle()
        {
            AutoSize = false;
            Height = 42;
            Cursor = Cursors.Hand;
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.OptimizedDoubleBuffer, true);
        }

        protected override void OnCheckedChanged(EventArgs eventArgs)
        {
            base.OnCheckedChanged(eventArgs);
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs eventArgs)
        {
            eventArgs.Graphics.Clear(Parent?.BackColor ?? InkSoft);
            var switchWidth = 48;
            var switchHeight = 24;
            var switchLeft = Math.Max(4, Width - switchWidth - 12);
            var switchTop = (Height - switchHeight) / 2;
            var track = new Rectangle(switchLeft, switchTop, switchWidth, switchHeight);
            using var trackBrush = new SolidBrush(Checked && Enabled ? Acid : Color.FromArgb(42, 48, 46));
            eventArgs.Graphics.FillEllipse(trackBrush, track.Left, track.Top, track.Height, track.Height);
            eventArgs.Graphics.FillEllipse(trackBrush, track.Right - track.Height, track.Top, track.Height, track.Height);
            eventArgs.Graphics.FillRectangle(trackBrush,
                track.Left + track.Height / 2, track.Top, track.Width - track.Height, track.Height);
            var knobSize = 18;
            var knobLeft = Checked ? track.Right - knobSize - 3 : track.Left + 3;
            using var knob = new SolidBrush(Enabled ? Bone : Muted);
            eventArgs.Graphics.FillEllipse(knob, knobLeft, track.Top + 3, knobSize, knobSize);
            TextRenderer.DrawText(eventArgs.Graphics, Text, Font,
                new Rectangle(8, 0, Math.Max(0, switchLeft - 14), Height),
                Enabled ? ForeColor : Muted,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
        }
    }

    sealed class BrandProgressBar : Control
    {
        int _value;

        public int Value
        {
            get => _value;
            set
            {
                _value = Math.Clamp(value, 0, 100);
                Invalidate();
            }
        }

        public BrandProgressBar()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.OptimizedDoubleBuffer, true);
        }

        protected override void OnPaint(PaintEventArgs eventArgs)
        {
            var bounds = new Rectangle(0, 0, Math.Max(0, Width - 1), Math.Max(0, Height - 1));
            using var background = new SolidBrush(Color.FromArgb(52, 57, 55));
            using var fill = new SolidBrush(Coral);
            using var border = new Pen(Color.FromArgb(82, 87, 84));
            eventArgs.Graphics.FillRectangle(background, bounds);
            if (_value > 0)
                eventArgs.Graphics.FillRectangle(fill, new Rectangle(0, 0, bounds.Width * _value / 100, bounds.Height));
            eventArgs.Graphics.DrawRectangle(border, bounds);
        }
    }

    void RefreshWindows()
    {
        var choices = NativeMethods.ListWindows();
        _loading = true;
        try
        {
            foreach (var ui in _profiles)
            {
                ui.Window.DataSource = choices.ToList();
                ui.Window.DisplayMember = nameof(WindowChoice.Display);
                var matches = choices.Where(choice =>
                    choice.ProcessName.Equals(ui.Profile.ProcessName, StringComparison.OrdinalIgnoreCase)
                    && choice.Title.Equals(ui.Profile.WindowTitle, StringComparison.CurrentCultureIgnoreCase))
                    .ToList();
                ui.Window.SelectedItem = matches.Count == 1 ? matches[0] : null;
                if (ui.Window.SelectedItem is null)
                    ui.Window.SelectedIndex = -1;
            }
        }
        finally
        {
            _loading = false;
        }
        foreach (var ui in _profiles)
            RefreshOverview(ui);
        SetStatus($"{choices.Count} janelas encontradas.");
    }

    void SelectHealthBar(ProfileUi ui)
    {
        if (!CanEdit() || !TryGetTarget(ui, out var choice, out var bounds))
            return;

        Rectangle selected = Rectangle.Empty;
        Bitmap? captured = null;
        Hide();
        try
        {
            if (!NativeMethods.TryActivate(choice.Handle))
                return;
            using var overlay = new RegionOverlay(bounds);
            if (overlay.ShowDialog() != DialogResult.OK)
                return;
            selected = overlay.SelectedRegion;
            captured = Recognition.Capture(bounds, new ScreenRegion
            {
                X = selected.X,
                Y = selected.Y,
                Width = selected.Width,
                Height = selected.Height
            });
        }
        finally
        {
            Show();
            Activate();
        }

        if (captured is null)
            return;
        using (captured)
        {
            if (!Recognition.LooksLikeBar(captured))
            {
                MessageBox.Show(this,
                    "Não foi possível localizar a parte vermelha. Marque novamente com a barra cheia.",
                    Text,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }

            ui.Profile.HealthBar = new ScreenRegion
            {
                X = selected.X,
                Y = selected.Y,
                Width = selected.Width,
                Height = selected.Height
            };
            ui.Profile.FullHealthRedWidth = Recognition.RedWidth(captured);
            ui.ClearRuntime();
            SetPreview(ui, captured);
            SetLifeReading(ui, 100, 0);
        }
        RefreshProfileUi(ui);
        TrySave();
    }

    async Task ReadHealthNowAsync(ProfileUi ui)
    {
        if (_running)
        {
            MessageBox.Show(this, "A leitura já é atualizada durante o monitoramento.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (!ui.Profile.HealthBar.IsConfigured || ui.Window.SelectedItem is not WindowChoice)
        {
            MessageBox.Show(this, "Marque a barra de vida primeiro.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var useVisibleCapture = !ui.Profile.BackgroundMode;
        if (useVisibleCapture)
        {
            WindowState = FormWindowState.Minimized;
            await Task.Delay(350);
        }
        var temporaryCapture = false;
        try
        {
            if (ui.Profile.BackgroundMode && ui.Capture is null)
            {
                var capture = await StartBackgroundCaptureAsync(ui);
                if (!capture.Started)
                {
                    MessageBox.Show(this, capture.Error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                temporaryCapture = true;
            }
            if (!TryCaptureBar(ui, out var current, out var error))
            {
                MessageBox.Show(this, error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            using (current)
            {
                if (Recognition.RedWidth(current) == 0)
                {
                    MessageBox.Show(this, "A parte vermelha da barra não foi localizada.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                var life = Recognition.LifePercent(current, ui.Profile.FullHealthRedWidth);
                SetLifeReading(ui, life, 100 - life);
                ui.Detected.Text = $"Leitura manual: vida em {life:F1}%.";
                SetPreview(ui, current);
            }
        }
        finally
        {
            if (temporaryCapture)
                ui.DisposeCapture();
            if (useVisibleCapture)
            {
                WindowState = FormWindowState.Normal;
                Activate();
            }
        }
    }

    void SelectTeleport(ProfileUi ui, bool random)
    {
        if (!CanEdit() || !TrySelectPoint(ui, out var point))
            return;
        var selected = new ClickPointConfig { X = point.X, Y = point.Y, Configured = true };
        if (random)
            ui.Profile.RandomTeleportPoint = selected;
        else
            ui.Profile.TeleportPoint = selected;
        RefreshProfileUi(ui);
        TrySave();
    }

    void SelectSpotWindow(ProfileUi ui)
    {
        if (!CanEdit() || !TryGetTarget(ui, out var choice, out var bounds))
            return;

        Rectangle selected = Rectangle.Empty;
        Bitmap? captured = null;
        Hide();
        try
        {
            if (!NativeMethods.TryActivate(choice.Handle))
                return;
            using var overlay = new RegionOverlay(
                bounds,
                instruction: "Arraste sobre uma parte fixa da janela de spots — Esc cancela");
            if (overlay.ShowDialog() != DialogResult.OK)
                return;
            selected = overlay.SelectedRegion;
            captured = Recognition.Capture(bounds, new ScreenRegion
            {
                X = selected.X,
                Y = selected.Y,
                Width = selected.Width,
                Height = selected.Height
            });
        }
        finally
        {
            Show();
            Activate();
        }

        if (captured is null)
            return;
        using (captured)
        using (var stream = new MemoryStream())
        {
            captured.Save(stream, System.Drawing.Imaging.ImageFormat.Png);
            ui.Profile.SpotWindowRegion = new ScreenRegion
            {
                X = selected.X,
                Y = selected.Y,
                Width = selected.Width,
                Height = selected.Height
            };
            ui.Profile.SpotWindowReferencePng = stream.ToArray();
            ui.SetSpotWindowReference(captured);
            ui.SpotMatch.Text = "Semelhança atual: 100% (referência)";
        }
        RefreshProfileUi(ui);
        TrySave();
    }

    void SelectSpotMenu(ProfileUi ui)
    {
        if (!CanEdit() || !TrySelectPoint(ui, out var point))
            return;
        ui.Profile.SpotMenuPoint = new ClickPointConfig { X = point.X, Y = point.Y, Configured = true };
        RefreshProfileUi(ui);
        TrySave();
    }

    void SelectConfirmTeleport(ProfileUi ui)
    {
        if (!CanEdit() || !TrySelectPoint(ui, out var point))
            return;
        ui.Profile.ConfirmTeleportPoint = new ClickPointConfig { X = point.X, Y = point.Y, Configured = true };
        RefreshProfileUi(ui);
        TrySave();
    }

    void ShowMarks(ProfileUi ui)
    {
        if (!CanEdit() || !TryGetTarget(ui, out var choice, out var bounds))
            return;

        var regions = new List<(Rectangle Region, string Label, Color Color)>();
        if (ui.Profile.HealthBar.IsConfigured)
            regions.Add((ToRectangle(ui.Profile.HealthBar), "Barra de vida", Color.Yellow));
        if (ui.Profile.SpotWindowRegion.IsConfigured)
            regions.Add((ToRectangle(ui.Profile.SpotWindowRegion), "Janela de spots", Color.DeepSkyBlue));

        var points = new List<(Point Point, string Label, Color Color)>();
        if (ui.Profile.TeleportPoint.Configured)
            points.Add((ToPoint(ui.Profile.TeleportPoint), "1 Safe", Color.Red));
        if (ui.Profile.RandomTeleportPoint.Configured)
            points.Add((ToPoint(ui.Profile.RandomTeleportPoint), "1 Random", Color.Magenta));
        if (ui.Profile.SpotMenuPoint.Configured)
            points.Add((ToPoint(ui.Profile.SpotMenuPoint), "2 Abrir spots", Color.Orange));
        for (var index = 0; index < ui.Profile.Spots.Count; index++)
            points.Add((new Point(ui.Profile.Spots[index].X, ui.Profile.Spots[index].Y),
                $"3.{index + 1} {ui.Profile.Spots[index].Name}{(ui.Profile.Spots[index].Enabled ? "" : " (desativado)")}",
                ui.Profile.Spots[index].Enabled ? Color.DodgerBlue : Color.Gray));
        if (ui.Profile.ConfirmTeleportPoint.Configured)
            points.Add((ToPoint(ui.Profile.ConfirmTeleportPoint), "4 Teleportar", Color.LimeGreen));

        if (regions.Count == 0 && points.Count == 0)
        {
            MessageBox.Show(this, "Ainda não há marcações nesta janela.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        Hide();
        try
        {
            if (!NativeMethods.TryActivate(choice.Handle))
                return;
            using var overlay = new RegionOverlay(
                bounds,
                instruction: "Marcações configuradas — clique ou aguarde 8 segundos para fechar",
                regions: regions,
                points: points);
            overlay.ShowDialog();
        }
        finally
        {
            Show();
            Activate();
        }
    }

    static Rectangle ToRectangle(ScreenRegion region) =>
        new(region.X, region.Y, region.Width, region.Height);

    static Point ToPoint(ClickPointConfig point) => new(point.X, point.Y);

    void AddSpot(ProfileUi ui)
    {
        if (!CanEdit() || !TrySelectPoint(ui, out var point))
            return;
        ui.Profile.Spots.Add(new SpotConfig
        {
            Name = $"Spot {ui.Profile.Spots.Count + 1}",
            X = point.X,
            Y = point.Y
        });
        RefreshSpotList(ui, ui.Profile.Spots.Count - 1);
        TrySave();
    }

    void ResetSpots(ProfileUi ui)
    {
        if (!CanEdit())
            return;
        if (MessageBox.Show(this,
                "A rota atual será substituída pelos novos pontos. Marque um spot por vez e pressione Esc para concluir.\r\n\r\nSe você pressionar Esc antes do primeiro ponto, a rota atual será mantida.",
                "Reiniciar spots",
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Warning) != DialogResult.OK
            || !TryGetTarget(ui, out var choice, out var bounds))
            return;

        var newSpots = new List<SpotConfig>();
        Hide();
        try
        {
            if (!NativeMethods.TryActivate(choice.Handle))
                return;
            while (true)
            {
                using var overlay = new RegionOverlay(
                    bounds,
                    true,
                    $"Clique no Spot {newSpots.Count + 1} — Esc conclui");
                if (overlay.ShowDialog() != DialogResult.OK)
                    break;
                newSpots.Add(new SpotConfig
                {
                    Name = $"Spot {newSpots.Count + 1}",
                    X = overlay.SelectedPoint.X,
                    Y = overlay.SelectedPoint.Y
                });
            }
        }
        finally
        {
            Show();
            Activate();
        }

        if (newSpots.Count == 0)
        {
            SetStatus("Redefinição cancelada; a rota anterior foi mantida.");
            return;
        }
        ui.Profile.Spots.Clear();
        foreach (var spot in newSpots)
            ui.Profile.Spots.Add(spot);
        ui.NextSpotIndex = 0;
        ui.CompletedCycles = 0;
        RefreshSpotList(ui, 0);
        UpdateProgress(ui);
        TrySave();
        SetStatus($"Rota redefinida com {newSpots.Count} spot(s).");
    }

    void UpdateSpot(ProfileUi ui)
    {
        var index = ui.Spots.SelectedIndex;
        if (!CanEdit() || index < 0 || !TrySelectPoint(ui, out var point))
            return;
        ui.Profile.Spots[index].X = point.X;
        ui.Profile.Spots[index].Y = point.Y;
        RefreshSpotList(ui, index);
        TrySave();
    }

    void RenameSpot(ProfileUi ui)
    {
        var index = ui.Spots.SelectedIndex;
        if (!CanEdit() || index < 0)
            return;
        var spot = ui.Profile.Spots[index];
        var name = AskName(spot.Name);
        if (string.IsNullOrWhiteSpace(name))
            return;
        spot.Name = name.Trim();
        RefreshSpotList(ui, index);
        UpdateProgress(ui);
        TrySave();
    }

    void MoveSpot(ProfileUi ui, int direction)
    {
        var from = ui.Spots.SelectedIndex;
        var to = from + direction;
        if (!CanEdit() || from < 0 || to < 0 || to >= ui.Profile.Spots.Count)
            return;
        var item = ui.Profile.Spots[from];
        ui.Profile.Spots.RemoveAt(from);
        ui.Profile.Spots.Insert(to, item);
        RefreshSpotList(ui, to);
        UpdateProgress(ui);
        TrySave();
    }

    void RemoveSpot(ProfileUi ui)
    {
        var index = ui.Spots.SelectedIndex;
        if (!CanEdit() || index < 0)
            return;
        ui.Profile.Spots.RemoveAt(index);
        ui.NextSpotIndex = Math.Max(0, FindEnabledSpot(ui.Profile.Spots, Math.Min(index, ui.Profile.Spots.Count - 1)));
        RefreshSpotList(ui, Math.Min(index, ui.Profile.Spots.Count - 1));
        UpdateProgress(ui);
        TrySave();
    }

    bool TrySelectPoint(ProfileUi ui, out Point point)
    {
        point = Point.Empty;
        if (!TryGetTarget(ui, out var choice, out var bounds))
            return false;

        var accepted = false;
        Hide();
        try
        {
            if (!NativeMethods.TryActivate(choice.Handle))
                return false;
            using var overlay = new RegionOverlay(bounds, true);
            if (overlay.ShowDialog() != DialogResult.OK)
                return false;
            point = overlay.SelectedPoint;
            accepted = true;
        }
        finally
        {
            Show();
            Activate();
        }
        return accepted;
    }

    bool TryGetTarget(ProfileUi ui, out WindowChoice choice, out Rectangle bounds)
    {
        bounds = Rectangle.Empty;
        if (ui.Window.SelectedItem is not WindowChoice selected)
        {
            choice = null!;
            MessageBox.Show(this, "Escolha a janela do jogo primeiro.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return false;
        }
        choice = selected;
        if (NativeMethods.IsIconic(choice.Handle)
            || !NativeMethods.TryGetClientScreenBounds(choice.Handle, out bounds))
        {
            MessageBox.Show(this, "Restaure a janela do jogo antes de continuar.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
        return true;
    }

    bool CanEdit()
    {
        if (!_running)
            return true;
        MessageBox.Show(this, "Pare a proteção antes de alterar o roteiro.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
        return false;
    }

    async Task StartProtectionAsync()
    {
        var candidates = _profiles.Where(ui => ui.Profile.ProtectionEnabled
                                               && ui.Profile.IsConfigured
                                               && (!ui.Profile.UseSpots || ui.SpotWindowReference is not null)
                                               && ui.Window.SelectedItem is WindowChoice).ToList();
        if (candidates.Count == 0)
        {
            MessageBox.Show(this,
                "Conclua as marcações obrigatórias. Após esta atualização, remarque a barra uma vez com a vida cheia.",
                Text,
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return;
        }

        if (candidates.Any(ui => !ui.Profile.BackgroundMode))
        {
            WindowState = FormWindowState.Minimized;
            await Task.Delay(500);
        }
        var started = 0;
        foreach (var ui in candidates)
            if (await StartProfileAsync(ui))
                started++;

        if (started == 0)
        {
            WindowState = FormWindowState.Normal;
            Activate();
            MessageBox.Show(this,
                "Nenhuma janela pôde ser iniciada. Verifique se está visível e não minimizada.",
                Text,
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }

        _running = true;
        _startStop.Text = "■  PARAR PROTEÇÃO";
        _startStop.BackColor = Coral;
        _timer.Start();
        SetStatus($"Proteção ativa em {started} janela(s).");
    }

    async Task<bool> StartProfileAsync(ProfileUi ui)
    {
        if (!ui.Profile.ProtectionEnabled
            || ui.State is ProfileState.Completed or ProfileState.SessionExpired)
            return false;
        if (HasSessionExpired(ui))
        {
            ExpireProfile(ui);
            return false;
        }
        if (ui.Profile.BackgroundMode)
        {
            var capture = await StartBackgroundCaptureAsync(ui);
            if (!capture.Started)
            {
                BeginBarSearch(ui, capture.Error);
                return true;
            }
        }
        if (!ui.Profile.BackgroundMode)
        {
            ui.DisposeCapture();
            ui.CaptureStatus.Text = "Captura: tela visível (modo compatibilidade)";
        }
        if (!TryCaptureBar(ui, out var current, out var error))
        {
            BeginBarSearch(ui, error);
            return true;
        }
        using (current)
        {
            if (Recognition.RedWidth(current) == 0)
            {
                BeginBarSearch(ui, "A parte vermelha da barra não foi localizada.");
                return true;
            }
            SetPreview(ui, current);
            var life = Recognition.LifePercent(current, ui.Profile.FullHealthRedWidth);
            SetLifeReading(ui, life, 100 - life);
        }
        ui.State = ProfileState.Monitoring;
        ui.SessionWatch.Start();
        ui.LossConfirmations = 0;
        SetProfileStatus(ui, "Monitorando", "Barra localizada; monitoramento iniciado.");
        return true;
    }

    async Task SetProfileProtectionAsync(ProfileUi ui, bool enabled)
    {
        ui.Profile.ProtectionEnabled = enabled;
        TrySave();
        if (!enabled)
        {
            ui.SessionWatch.Stop();
            ui.DisposeCapture();
            ui.ResetStableCandidate();
            ui.LossConfirmations = 0;
            if (ui.State is not (ProfileState.Completed or ProfileState.SessionExpired))
            {
                ui.State = ProfileState.Stopped;
                SetProfileStatus(ui, "Desativada", "Proteção desligada para esta janela.");
            }
            SetStatus($"Proteção desativada em {ui.Profile.Name}.");
            return;
        }

        if (!_running)
        {
            if (ui.State is not (ProfileState.Completed or ProfileState.SessionExpired))
                SetProfileStatus(ui, "Pronta", "Será iniciada pelo botão Iniciar proteção.");
            return;
        }
        if (ui.State is ProfileState.Completed or ProfileState.SessionExpired)
        {
            SetStatus($"{ui.Profile.Name} permanece encerrada; reinicie sua sequência para ativá-la.", true);
            return;
        }

        var useVisibleCapture = !ui.Profile.BackgroundMode;
        if (useVisibleCapture)
        {
            WindowState = FormWindowState.Minimized;
            await Task.Delay(500);
        }
        try
        {
            if (await StartProfileAsync(ui))
                SetStatus($"Proteção ativada em {ui.Profile.Name}.");
        }
        finally
        {
            if (useVisibleCapture)
            {
                WindowState = FormWindowState.Normal;
                Activate();
            }
        }
    }

    async Task<(bool Started, string Error)> StartBackgroundCaptureAsync(ProfileUi ui)
    {
        ui.DisposeCapture();
        if (ui.Window.SelectedItem is not WindowChoice choice)
            return (false, "Janela não selecionada.");
        ui.CaptureStatus.Text = "Captura: iniciando segundo plano...";
        var result = await WindowCapture.StartAsync(choice.Handle);
        if (result.Capture is null)
        {
            ui.CaptureStatus.Text = "Captura: incompatível ou sem imagem";
            return (false, result.Error);
        }
        ui.Capture = result.Capture;
        ui.CaptureStatus.Text = "Captura: segundo plano ativo";
        return (true, "");
    }

    void BeginBarSearch(ProfileUi ui, string reason)
    {
        if (ui.State != ProfileState.Searching)
            ui.ResumeAfterSearch = ui.State == ProfileState.Stabilizing
                ? ProfileState.Stabilizing
                : ProfileState.Monitoring;
        ui.SessionWatch.Stop();
        ui.DisposeCapture();
        ui.State = ProfileState.Searching;
        ui.NextBarSearchAt = DateTimeOffset.Now.AddSeconds(BarSearchIntervalSeconds);
        ui.LossConfirmations = 0;
        ui.ResetStableCandidate();
        ui.CaptureStatus.Text = "Captura: procurando barra";
        SetProfileStatus(ui, "Procurando barra", $"{reason} Nova tentativa em {BarSearchIntervalSeconds} segundos.");
    }

    void StopProtection()
    {
        _running = false;
        _timer.Stop();
        foreach (var ui in _profiles)
            ui.DisposeCapture();
        foreach (var ui in _profiles.Where(item => IsActiveState(item.State)))
        {
            ui.SessionWatch.Stop();
            ui.State = ProfileState.Stopped;
            SetProfileStatus(ui, "Parada", "Progresso preservado.");
        }
        _startStop.Text = "⛨  INICIAR PROTEÇÃO";
        _startStop.BackColor = Acid;
        SetStatus("Proteção parada.");
    }

    async void MonitorTick(object? sender, EventArgs eventArgs)
    {
        if (!_running || _busy)
            return;
        _busy = true;
        _timer.Stop();
        try
        {
            foreach (var ui in _profiles)
                await ProcessProfileAsync(ui);
        }
        finally
        {
            _busy = false;
            if (_running && _profiles.Any(item => IsActiveState(item.State)))
                _timer.Start();
            else if (_running)
            {
                _running = false;
                _startStop.Text = "⛨  INICIAR PROTEÇÃO";
                _startStop.BackColor = Acid;
                SetStatus("Todas as sequências ativas foram concluídas ou pausadas.");
            }
        }
    }

    async Task ProcessProfileAsync(ProfileUi ui)
    {
        if (!ui.Profile.ProtectionEnabled)
            return;
        if (ui.State == ProfileState.Searching)
        {
            await SearchForBarAsync(ui);
            return;
        }
        if (ui.State is not (ProfileState.Monitoring or ProfileState.Stabilizing))
            return;
        UpdateTime(ui);
        if (HasSessionExpired(ui))
        {
            ExpireProfile(ui);
            return;
        }
        if (!TryCaptureBar(ui, out var current, out var error))
        {
            BeginBarSearch(ui, error);
            return;
        }

        using (current)
        {
            SetPreview(ui, current);
            if (Recognition.RedWidth(current) == 0)
            {
                BeginBarSearch(ui, "A parte vermelha da barra não foi localizada.");
                return;
            }
            if (ui.State == ProfileState.Stabilizing)
            {
                ProcessStabilizing(ui, current);
                return;
            }

            var life = Recognition.LifePercent(current, ui.Profile.FullHealthRedWidth);
            var loss = 100 - life;
            SetLifeReading(ui, life, loss);
            ui.Detected.Text = $"Vida estimada: {life:F0}% — queda: {loss:F1}%";

            if (loss >= (double)ui.Profile.DropLimitPercent)
                ui.LossConfirmations++;
            else
                ui.LossConfirmations = 0;

            if (ui.LossConfirmations >= 3)
                await ReactAsync(ui);
        }
    }

    async Task SearchForBarAsync(ProfileUi ui)
    {
        UpdateTime(ui);
        if (!IsBarSearchDue(DateTimeOffset.Now, ui.NextBarSearchAt))
            return;

        if (ui.Profile.BackgroundMode)
        {
            var capture = await StartBackgroundCaptureAsync(ui);
            if (!capture.Started)
            {
                BeginBarSearch(ui, capture.Error);
                return;
            }
        }
        if (!TryCaptureBar(ui, out var current, out var error))
        {
            BeginBarSearch(ui, error);
            return;
        }
        using (current)
        {
            SetPreview(ui, current);
            if (Recognition.RedWidth(current) == 0)
            {
                BeginBarSearch(ui, "A parte vermelha da barra ainda não foi localizada.");
                return;
            }

            ui.State = ui.ResumeAfterSearch;
            ui.SessionWatch.Start();
            ui.LossConfirmations = 0;
            if (ui.State == ProfileState.Stabilizing)
            {
                ui.RearmNotBefore = DateTimeOffset.Now;
                ui.ResetStableCandidate();
                SetProfileStatus(ui, "Aguardando", "Barra reencontrada; confirmando estabilidade.");
                return;
            }

            var life = Recognition.LifePercent(current, ui.Profile.FullHealthRedWidth);
            SetLifeReading(ui, life, 100 - life);
            SetProfileStatus(ui, "Monitorando", $"Barra reencontrada; vida em {life:F0}%.");
        }
    }

    static bool IsActiveState(ProfileState state) =>
        state is ProfileState.Monitoring or ProfileState.Reacting
            or ProfileState.Stabilizing or ProfileState.Searching;

    static bool IsBarSearchDue(DateTimeOffset now, DateTimeOffset nextSearch) => now >= nextSearch;

    async Task ReactAsync(ProfileUi ui)
    {
        if (!ui.Profile.ProtectionEnabled)
            return;
        if (ui.Profile.UseSpots && !ui.Profile.Spots.Any(item => item.Enabled))
        {
            PauseProfile(ui, "Nenhum spot ativo.");
            return;
        }

        ui.State = ProfileState.Reacting;
        ui.LossConfirmations = 0;
        SpotConfig? spot = null;
        var executedSpotIndex = -1;
        if (ui.Profile.UseSpots)
        {
            ui.NextSpotIndex = FindEnabledSpot(ui.Profile.Spots, ui.NextSpotIndex);
            executedSpotIndex = ui.NextSpotIndex;
            spot = ui.Profile.Spots[executedSpotIndex];
        }
        SetProfileStatus(ui, "Reagindo", spot is null
            ? "Usando somente o teleporte..."
            : $"Usando teleporte e depois {spot.Name}...");

        if (!await ExecuteClicksAsync(ui, spot, true))
            return;

        if (ui.Profile.UseSpots)
        {
            var advanced = AdvanceSequence(
                executedSpotIndex,
                ui.CompletedCycles,
                ui.Profile.Spots,
                ui.Profile.CycleCount);
            ui.NextSpotIndex = advanced.NextSpot;
            ui.CompletedCycles = advanced.CompletedCycles;

            if (advanced.Finished)
            {
                ui.State = ProfileState.Completed;
                ui.SessionWatch.Stop();
                ui.DisposeCapture();
                ui.DisposeImages();
                SetProfileStatus(ui, "Concluída", "Todos os ciclos foram executados.");
                UpdateProgress(ui);
                return;
            }
        }

        ui.State = ProfileState.Stabilizing;
        ui.RearmNotBefore = DateTimeOffset.Now.AddMilliseconds(ui.Profile.RearmDelayMs);
        ui.ResetStableCandidate();
        SetProfileStatus(ui, "Aguardando", "Esperando o jogo e a barra estabilizarem.");
        UpdateProgress(ui);
    }

    async Task<bool> ExecuteClicksAsync(ProfileUi ui, SpotConfig? spot, bool pauseOnError)
    {
        if (!ui.Profile.ProtectionEnabled || ui.Window.SelectedItem is not WindowChoice choice)
            return false;

        var teleport = SelectedTeleport(ui.Profile);
        if (!Click(teleport.X, teleport.Y, $"Teleporte {(UsesRandomTeleport(ui.Profile) ? "Random" : "Safe")}"))
            return false;

        if (spot is null)
            return true;

        await Task.Delay(ui.Profile.TeleportToSpotDelayMs);
        if (!ui.Profile.ProtectionEnabled)
            return false;
        if (!TryMeasureSpotWindow(ui, out var similarity, out var error))
            return Fail(error);

        if (similarity < (double)ui.Profile.SpotWindowMinimumSimilarity)
        {
            if (!Click(ui.Profile.SpotMenuPoint.X, ui.Profile.SpotMenuPoint.Y, "Abrir spots"))
                return false;
            await Task.Delay(ui.Profile.TeleportToSpotDelayMs);
            if (!ui.Profile.ProtectionEnabled)
                return false;
            if (!TryMeasureSpotWindow(ui, out similarity, out error))
                return Fail(error);
            if (similarity < (double)ui.Profile.SpotWindowMinimumSimilarity)
                return Fail($"Janela de spots não reconhecida ({similarity:F0}% de semelhança). Refaça a marcação ou ajuste o limite.");
        }

        if (!Click(spot.X, spot.Y, spot.Name))
            return false;
        await Task.Delay(ui.Profile.TeleportToSpotDelayMs);
        if (!ui.Profile.ProtectionEnabled)
            return false;
        for (var attempt = 1; attempt <= ui.Profile.TeleportRetryCount; attempt++)
        {
            SetProfileStatus(ui, "Reagindo", $"Confirmando teleporte ({attempt}/{ui.Profile.TeleportRetryCount})...");
            if (!Click(ui.Profile.ConfirmTeleportPoint.X, ui.Profile.ConfirmTeleportPoint.Y, "Botão Teleportar"))
                return false;
            await Task.Delay(ui.Profile.TeleportToSpotDelayMs);
            if (!ui.Profile.ProtectionEnabled)
                return false;
            if (!TryMeasureSpotWindow(ui, out similarity, out error))
                return Fail(error);
            if (similarity < (double)ui.Profile.SpotWindowMinimumSimilarity)
                return true;
        }
        return Fail($"Teleporte não confirmado após {ui.Profile.TeleportRetryCount} tentativa(s). A janela de spots continuou aberta.");

        bool Click(int x, int y, string name)
        {
            if (!ui.Profile.ProtectionEnabled)
                return false;
            var clicked = ui.Profile.BackgroundMode
                ? NativeMethods.TryBackgroundClick(choice.Handle, x, y, out var clickError)
                : NativeMethods.TryClick(choice.Handle, x, y, out clickError);
            if (clicked)
                return true;
            return Fail($"{name} não clicado: {clickError}");
        }

        bool Fail(string message)
        {
            if (pauseOnError)
                PauseProfile(ui, message);
            else
                MessageBox.Show(this, message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
    }

    void ProcessStabilizing(ProfileUi ui, Bitmap current)
    {
        var remaining = ui.RearmNotBefore - DateTimeOffset.Now;
        if (remaining > TimeSpan.Zero)
        {
            ui.Detected.Text = $"Aguardando {Math.Ceiling(remaining.TotalSeconds)} s antes de procurar a barra.";
            return;
        }
        if (ui.StableCandidate is null)
        {
            ui.SetStableCandidate(current);
            ui.StableSince = DateTimeOffset.Now;
            return;
        }

        if (Recognition.DifferencePercent(ui.StableCandidate, current) > 2)
        {
            ui.SetStableCandidate(current);
            ui.StableSince = DateTimeOffset.Now;
            ui.Detected.Text = "Barra encontrada; aguardando ficar estável.";
            return;
        }

        var stableFor = DateTimeOffset.Now - ui.StableSince;
        ui.Detected.Text = $"Barra estável por {stableFor.TotalSeconds:F1} s.";
        if (stableFor.TotalMilliseconds < ui.Profile.StableTimeMs)
            return;

        ui.ResetStableCandidate();
        ui.State = ProfileState.Monitoring;
        var life = Recognition.LifePercent(current, ui.Profile.FullHealthRedWidth);
        SetLifeReading(ui, life, 100 - life);
        ui.LossConfirmations = 0;
        SetProfileStatus(ui, "Monitorando", $"Barra estabilizada; vida em {life:F0}%.");
    }

    async Task RearmProfileAsync(ProfileUi ui)
    {
        if (ui.State == ProfileState.SessionExpired)
        {
            MessageBox.Show(this,
                "O limite desta sessão terminou. Use 'Recomeçar do Spot 1' para zerar o tempo.",
                Text,
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return;
        }
        var wasRunning = _running;
        var useVisibleCapture = !ui.Profile.BackgroundMode;
        if (useVisibleCapture)
        {
            WindowState = FormWindowState.Minimized;
            await Task.Delay(350);
        }
        var temporaryCapture = false;
        try
        {
        if (ui.Profile.BackgroundMode && ui.Capture is null)
        {
            var capture = await StartBackgroundCaptureAsync(ui);
            if (!capture.Started)
            {
                if (wasRunning)
                    BeginBarSearch(ui, capture.Error);
                else
                    MessageBox.Show(this, capture.Error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            temporaryCapture = !wasRunning;
        }
        if (TryCaptureBar(ui, out var current, out var error))
        {
            using (current)
            {
                if (Recognition.RedWidth(current) == 0)
                {
                    if (wasRunning)
                        BeginBarSearch(ui, "A parte vermelha da barra não foi localizada.");
                    else
                        MessageBox.Show(this, "A parte vermelha da barra não foi localizada.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                SetPreview(ui, current);
                var life = Recognition.LifePercent(current, ui.Profile.FullHealthRedWidth);
                SetLifeReading(ui, life, 100 - life);
            }
            ui.State = wasRunning ? ProfileState.Monitoring : ProfileState.Stopped;
            if (wasRunning)
            ui.SessionWatch.Start();
            ui.LossConfirmations = 0;
            SetProfileStatus(ui, wasRunning ? "Monitorando" : "Parada", "Leitura da barra atualizada.");
        }
        else
        {
            if (wasRunning)
                BeginBarSearch(ui, error);
            else
                MessageBox.Show(this, error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        }
        finally
        {
            if (!wasRunning && temporaryCapture)
                ui.DisposeCapture();
            if (useVisibleCapture)
            {
                WindowState = FormWindowState.Normal;
                Activate();
            }
        }
    }

    async Task ResetSequenceAsync(ProfileUi ui)
    {
        ui.NextSpotIndex = Math.Max(0, FindEnabledSpot(ui.Profile.Spots));
        ui.CompletedCycles = 0;
        ui.SessionWatch.Reset();
        UpdateTime(ui);
        UpdateProgress(ui);
        if (_running)
            await RearmProfileAsync(ui);
        else
        {
            ui.State = ProfileState.Stopped;
            ui.DisposeImages();
            SetProfileStatus(ui, "Parada", "Sequência reiniciada no primeiro spot ativo.");
        }
    }

    async Task TestReactionAsync(ProfileUi ui)
    {
        if (_running)
        {
            MessageBox.Show(this, "Pare a proteção antes de testar.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (!ui.Profile.IsConfigured
            || (ui.Profile.UseSpots && ui.SpotWindowReference is null)
            || ui.Window.SelectedItem is not WindowChoice)
        {
            MessageBox.Show(this, "Conclua os quatro passos antes de testar.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        SpotConfig? spot = null;
        if (ui.Profile.UseSpots)
        {
            ui.NextSpotIndex = FindEnabledSpot(ui.Profile.Spots, ui.NextSpotIndex);
            spot = ui.Profile.Spots[ui.NextSpotIndex];
        }
        if (MessageBox.Show(this,
                spot is null
                    ? "O teste clicará somente no item de teleporte. Continuar?"
                    : $"O teste abrirá o item de teleporte, localizará a janela de spots, escolherá {spot.Name} e confirmará. Continuar?",
                Text,
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question) != DialogResult.Yes)
            return;
        var temporaryCapture = false;
        if (ui.Profile.BackgroundMode && spot is not null)
        {
            var capture = await StartBackgroundCaptureAsync(ui);
            if (!capture.Started)
            {
                MessageBox.Show(this, capture.Error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            temporaryCapture = true;
        }
        await ExecuteClicksAsync(ui, spot, false);
        if (temporaryCapture)
            ui.DisposeCapture();
        Show();
        WindowState = FormWindowState.Normal;
        Activate();
    }

    async Task TestBackgroundClickAsync(ProfileUi ui)
    {
        if (_running)
        {
            MessageBox.Show(this, "Pare a proteção antes de testar a compatibilidade.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        var teleport = SelectedTeleport(ui.Profile);
        if (ui.Window.SelectedItem is not WindowChoice choice || !teleport.Configured)
        {
            MessageBox.Show(this, "Escolha a janela e marque o item de teleporte primeiro.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (MessageBox.Show(this,
                "Após confirmar, aguarde 5 segundos. Mantenha o jogo aberto; ele pode ficar coberto, mas não minimizado. O clique será enviado sem mover o cursor nem ativar a janela.",
                Text,
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Information) != DialogResult.OK)
            return;

        await Task.Delay(5000);
        if (NativeMethods.TryBackgroundClick(
                choice.Handle,
                teleport.X,
                teleport.Y,
                out var error))
        {
            SetStatus("Clique em segundo plano enviado. Confira se o item de teleporte abriu.");
            return;
        }

        MessageBox.Show(this, $"Teste em segundo plano não enviado: {error}", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
    }

    async Task TestBackgroundCaptureAsync(ProfileUi ui)
    {
        if (_running)
        {
            MessageBox.Show(this, "Pare a proteção antes de testar a captura.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (ui.Window.SelectedItem is not WindowChoice choice || !ui.Profile.HealthBar.IsConfigured)
        {
            MessageBox.Show(this, "Escolha a janela e marque a barra de vida primeiro.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (MessageBox.Show(this,
                "Após confirmar, aguarde 5 segundos. Mantenha o jogo aberto; ele pode ficar coberto, mas não minimizado. A barra será capturada sem ativar a janela.",
                Text,
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Information) != DialogResult.OK)
            return;

        await Task.Delay(5000);
        var result = await WindowCapture.StartAsync(choice.Handle);

        if (result.Capture is null)
        {
            MessageBox.Show(this, result.Error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        using (result.Capture)
        {
            if (!result.Capture.TryGetRegion(ui.Profile.HealthBar, out var bar, out var error))
            {
                MessageBox.Show(this, error, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            using (bar)
            {
            var content = Recognition.ContentPercent(bar);
            var looksLikeBar = Recognition.LooksLikeBar(bar);
            SetPreview(ui, bar);
            ui.Detected.Text = $"Captura em segundo plano: {content:F0}% de conteúdo visível.";
            MessageBox.Show(this,
                $"Captura recebida: {content:F0}% de conteúdo visível. A imagem {(looksLikeBar ? "parece" : "não parece")} conter a barra. Confira o visualizador.",
                Text,
                MessageBoxButtons.OK,
                looksLikeBar ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
            }
        }
    }

    bool TryMeasureSpotWindow(ProfileUi ui, out double similarity, out string error)
    {
        similarity = 0;
        if (ui.SpotWindowReference is null)
        {
            error = "A referência da janela de spots está ausente. Marque-a novamente.";
            return false;
        }
        if (!TryCaptureRegion(ui, ui.Profile.SpotWindowRegion, "A janela de spots", out var current, out error))
            return false;

        using (current)
            similarity = 100 - Recognition.DifferencePercent(ui.SpotWindowReference, current);
        similarity = Math.Clamp(similarity, 0, 100);
        ui.SpotMatch.Text = $"Semelhança atual: {similarity:F0}%";
        ui.SpotMatch.ForeColor = similarity >= (double)ui.Profile.SpotWindowMinimumSimilarity
            ? Acid
            : Coral;
        return true;
    }

    bool TryCaptureBar(ProfileUi ui, out Bitmap bitmap, out string error) =>
        TryCaptureRegion(ui, ui.Profile.HealthBar, "A barra", out bitmap, out error);

    bool TryCaptureRegion(ProfileUi ui, ScreenRegion region, string name, out Bitmap bitmap, out string error)
    {
        bitmap = null!;
        error = "";
        if (ui.Window.SelectedItem is not WindowChoice choice || !NativeMethods.IsWindow(choice.Handle))
        {
            error = "Janela não encontrada.";
            return false;
        }
        if (ui.Profile.BackgroundMode)
        {
            if (ui.Capture is null)
            {
                error = "A captura em segundo plano não foi iniciada.";
                ui.CaptureStatus.Text = "Captura: parada";
                return false;
            }
            if (ui.Capture.TryGetRegion(region, out bitmap, out error))
            {
                ui.CaptureStatus.Text = "Captura: segundo plano ativo";
                return true;
            }
            ui.CaptureStatus.Text = error.Contains("preta", StringComparison.OrdinalIgnoreCase)
                ? "Captura: quadro preto"
                : "Captura: sem quadros recentes";
            return false;
        }
        if (NativeMethods.IsIconic(choice.Handle)
            || !NativeMethods.TryGetClientScreenBounds(choice.Handle, out var client))
        {
            error = "Janela minimizada ou indisponível.";
            return false;
        }
        if (!region.IsConfigured
            || region.X < 0 || region.Y < 0
            || region.X + region.Width > client.Width
            || region.Y + region.Height > client.Height)
        {
            error = $"{name} ficou fora da janela. Marque-a novamente.";
            return false;
        }

        try
        {
            bitmap = Recognition.Capture(client, region);
            return true;
        }
        catch (Exception exception)
        {
            error = exception.Message;
            return false;
        }
    }

    void PauseProfile(ProfileUi ui, string reason)
    {
        ui.SessionWatch.Stop();
        ui.DisposeCapture();
        if (ui.Profile.BackgroundMode)
            ui.CaptureStatus.Text = "Captura: pausada por falha";
        ui.State = ProfileState.Error;
        ui.ResetStableCandidate();
        SetProfileStatus(ui, "Pausada", reason);
    }

    void SetProfileStatus(ProfileUi ui, string state, string detail)
    {
        ui.StateLabel.Text = state;
        ui.StateLabel.ForeColor = state switch
        {
            "Monitorando" or "Pronta" or "Concluída" => Acid,
            "Pausada" or "Tempo encerrado" or "Desativada" => Coral,
            "Reagindo" or "Aguardando" or "Procurando barra" => Gold,
            _ => Bone
        };
        ui.Detected.Text = detail;
        UpdateProgress(ui);
        UpdateTime(ui);
    }

    void UpdateProgress(ProfileUi ui)
    {
        if (ui.State == ProfileState.SessionExpired)
        {
            ui.Progress.Text = "Sessão encerrada";
            RefreshOverview(ui);
            return;
        }
        if (ui.State == ProfileState.Completed)
        {
            ui.Progress.Text = $"Concluído\r\n{ui.CompletedCycles}/{ui.Profile.CycleCount} ciclos";
            RefreshOverview(ui);
            return;
        }
        if (!ui.Profile.UseSpots)
        {
            ui.Progress.Text = "Somente teleporte";
            RefreshOverview(ui);
            return;
        }
        var activeCount = ui.Profile.Spots.Count(item => item.Enabled);
        if (activeCount == 0)
        {
            ui.Progress.Text = "Ative ao menos um spot.";
            RefreshOverview(ui);
            return;
        }
        ui.NextSpotIndex = FindEnabledSpot(ui.Profile.Spots, ui.NextSpotIndex);
        var cycle = Math.Min(ui.CompletedCycles + 1, ui.Profile.CycleCount);
        ui.Progress.Text = $"{ui.Profile.Spots[ui.NextSpotIndex].Name}\r\nCiclo {cycle}/{ui.Profile.CycleCount} • {activeCount} ativo(s)";
        RefreshOverview(ui);
    }

    void RefreshProfileUi(ProfileUi ui)
    {
        var barConfigured = ui.Profile.HealthBar.IsConfigured && ui.Profile.FullHealthRedWidth > 0;
        ui.BarStatus.Text = barConfigured
            ? $"✓ {ui.Profile.HealthBar.Width} × {ui.Profile.HealthBar.Height}"
            : ui.Profile.HealthBar.IsConfigured ? "Remarque com a vida cheia" : "Não configurado";
        ui.BarStatus.ForeColor = barConfigured ? Acid : Coral;
        var selectedTeleport = SelectedTeleport(ui.Profile);
        var teleportName = UsesRandomTeleport(ui.Profile) ? "RANDOM" : "SAFE";
        ui.TeleportStatus.Text = selectedTeleport.Configured ? $"{teleportName} • ✓ Ponto selecionado" : $"{teleportName} • Não configurado";
        ui.TeleportStatus.ForeColor = selectedTeleport.Configured ? Acid : Coral;
        ui.SafeTeleportStatus.Text = ui.Profile.TeleportPoint.Configured ? "✓ Ponto selecionado" : "Não configurado";
        ui.SafeTeleportStatus.ForeColor = ui.Profile.TeleportPoint.Configured ? Acid : Coral;
        ui.RandomTeleportStatus.Text = ui.Profile.RandomTeleportPoint.Configured ? "✓ Ponto selecionado" : "Não configurado";
        ui.RandomTeleportStatus.ForeColor = ui.Profile.RandomTeleportPoint.Configured ? Acid : Coral;
        var spotWindowConfigured = ui.Profile.SpotWindowRegion.IsConfigured && ui.SpotWindowReference is not null;
        ui.SpotWindowStatus.Text = spotWindowConfigured
            ? $"✓ {ui.Profile.SpotWindowRegion.Width} × {ui.Profile.SpotWindowRegion.Height}"
            : "Não configurado";
        ui.SpotWindowStatus.ForeColor = spotWindowConfigured ? Acid : Coral;
        ui.SpotMenuStatus.Text = ui.Profile.SpotMenuPoint.Configured ? "✓ Ponto selecionado" : "Não configurado";
        ui.SpotMenuStatus.ForeColor = ui.Profile.SpotMenuPoint.Configured ? Acid : Coral;
        ui.ConfirmTeleportStatus.Text = ui.Profile.ConfirmTeleportPoint.Configured ? "✓ Ponto selecionado" : "Não configurado";
        ui.ConfirmTeleportStatus.ForeColor = ui.Profile.ConfirmTeleportPoint.Configured ? Acid : Coral;
        if (!spotWindowConfigured)
        {
            ui.SpotMatch.Text = "Semelhança atual: --";
            ui.SpotMatch.ForeColor = Bone;
        }
        RefreshSpotList(ui, ui.Spots.SelectedIndex);
        if (ui.Capture is null)
            ui.CaptureStatus.Text = ui.Profile.BackgroundMode
                ? "Captura: segundo plano será iniciado com a proteção"
                : "Captura: tela visível (modo compatibilidade)";
        UpdateProgress(ui);
        UpdateTime(ui);
    }

    static bool UsesRandomTeleport(WindowProfile profile) =>
        string.Equals(profile.TeleportMode, "Random", StringComparison.OrdinalIgnoreCase);

    static ClickPointConfig SelectedTeleport(WindowProfile profile) =>
        UsesRandomTeleport(profile) ? profile.RandomTeleportPoint : profile.TeleportPoint;

    static TimeSpan SessionLimit(ProfileUi ui) => TimeSpan.FromMinutes(ui.Profile.SessionLimitMinutes);

    static bool HasSessionExpired(ProfileUi ui) =>
        HasSessionExpired(ui.SessionWatch.Elapsed, ui.Profile.SessionLimitMinutes);

    static bool HasSessionExpired(TimeSpan elapsed, int limitMinutes) =>
        elapsed >= TimeSpan.FromMinutes(limitMinutes);

    void UpdateTime(ProfileUi ui)
    {
        var active = ui.SessionWatch.Elapsed;
        var remaining = SessionLimit(ui) - active;
        if (remaining < TimeSpan.Zero)
            remaining = TimeSpan.Zero;
        ui.TimeLabel.Text = FormatTime(active);
        ui.RemainingTimeLabel.Text = FormatTime(remaining);
        RefreshOverview(ui);
    }

    void ExpireProfile(ProfileUi ui)
    {
        ui.SessionWatch.Stop();
        ui.State = ProfileState.SessionExpired;
        ui.DisposeCapture();
        ui.DisposeImages();
        UpdateTime(ui);
        SetProfileStatus(ui, "Tempo encerrado", "Esta janela foi desativada pelo limite da sessão.");
    }

    static string FormatTime(TimeSpan time) =>
        $"{(int)time.TotalHours:00}:{time.Minutes:00}:{time.Seconds:00}";

    static void RefreshSpotList(ProfileUi ui, int selected = -1)
    {
        ui.UpdatingSpotChecks = true;
        ui.Spots.BeginUpdate();
        try
        {
            ui.Spots.Items.Clear();
            for (var index = 0; index < ui.Profile.Spots.Count; index++)
                ui.Spots.Items.Add($"{index + 1}. {ui.Profile.Spots[index]}", ui.Profile.Spots[index].Enabled);
        }
        finally
        {
            ui.Spots.EndUpdate();
            ui.UpdatingSpotChecks = false;
        }
        if (selected >= 0 && selected < ui.Spots.Items.Count)
            ui.Spots.SelectedIndex = selected;
    }

    static void SetPreview(ProfileUi ui, Bitmap bitmap)
    {
        var previous = ui.Preview.Image;
        ui.Preview.Image = new Bitmap(bitmap);
        previous?.Dispose();
    }

    void SetLifeReading(ProfileUi ui, double life, double loss)
    {
        var safeLife = Math.Clamp(life, 0, 100);
        ui.LifeMeter.Value = (int)Math.Round(safeLife);
        ui.LifePercent.Text = $"{safeLife:F0}%";
        ui.LifeLoss.Text = $"Queda {Math.Clamp(loss, 0, 100):F1}%";
        RefreshOverview(ui);
    }

    static string? AskName(string current)
    {
        using var dialog = new Form
        {
            Text = "Nome do spot",
            Width = 360,
            Height = 145,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            StartPosition = FormStartPosition.CenterParent,
            MaximizeBox = false,
            MinimizeBox = false
        };
        var text = new TextBox { Text = current, Left = 15, Top = 18, Width = 310 };
        var ok = new Button { Text = "OK", DialogResult = DialogResult.OK, Left = 165, Top = 55, Width = 75 };
        var cancel = new Button { Text = "Cancelar", DialogResult = DialogResult.Cancel, Left = 250, Top = 55, Width = 75 };
        dialog.Controls.AddRange([text, ok, cancel]);
        dialog.AcceptButton = ok;
        dialog.CancelButton = cancel;
        return dialog.ShowDialog() == DialogResult.OK ? text.Text : null;
    }

    void TrySave()
    {
        try
        {
            ConfigStore.Save(_config);
        }
        catch (Exception error)
        {
            SetStatus($"Não foi possível salvar: {error.Message}", true);
        }
    }

    void SetStatus(string message, bool error = false)
    {
        _status.Text = message;
        _status.ForeColor = error ? Coral : Muted;
    }

    async Task CheckForUpdatesAsync(bool reportLatest = false)
    {
        if (_checkingUpdate)
            return;
        _checkingUpdate = true;
        try
        {
            _updateStatus.Text = "VERIFICANDO";
            SetStatus("Verificando atualizações...");
            var update = await Updater.CheckAsync();
            if (update is null)
            {
                _updateStatus.Text = "ATUALIZADO";
                SetStatus($"Ronaldinho v{Updater.CurrentVersion.ToString(3)} está atualizado.");
                if (reportLatest)
                    MessageBox.Show(this, "Você já está usando a versão mais recente.", "Atualização",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            var answer = MessageBox.Show(this,
                $"A versão {update.Tag} está disponível. Deseja baixar, instalar e reiniciar agora?",
                "Atualização disponível", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
            _updateStatus.Text = $"{update.Tag} DISPONÍVEL";
            if (answer != DialogResult.Yes)
            {
                SetStatus($"Atualização {update.Tag} disponível.");
                return;
            }

            SetStatus($"Baixando atualização {update.Tag}...");
            await Updater.InstallAndRestartAsync(update);
            Application.Exit();
        }
        catch (Exception error)
        {
            _updateStatus.Text = "OFFLINE";
            SetStatus($"Não foi possível verificar atualizações: {error.Message}", true);
            if (reportLatest)
                MessageBox.Show(this, error.Message, "Atualização", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        finally
        {
            _checkingUpdate = false;
        }
    }

    static (int NextSpot, int CompletedCycles, bool Finished) AdvanceSequence(
        int currentSpot,
        int completedCycles,
        IList<SpotConfig> spots,
        int cycleCount)
    {
        if (currentSpot < 0 || currentSpot >= spots.Count || cycleCount < 1)
            throw new ArgumentOutOfRangeException(nameof(currentSpot));

        var nextSpot = -1;
        for (var index = currentSpot + 1; index < spots.Count; index++)
        {
            if (!spots[index].Enabled)
                continue;
            nextSpot = index;
            break;
        }
        if (nextSpot < 0)
        {
            nextSpot = FindEnabledSpot(spots);
            if (nextSpot < 0)
                throw new InvalidOperationException("A sequência não possui spots ativos.");
            completedCycles++;
        }
        return (nextSpot, completedCycles, completedCycles >= cycleCount);
    }

    static int FindEnabledSpot(IList<SpotConfig> spots, int start = 0)
    {
        if (spots.Count == 0)
            return -1;
        start %= spots.Count;
        if (start < 0)
            start += spots.Count;
        for (var offset = 0; offset < spots.Count; offset++)
        {
            var index = (start + offset) % spots.Count;
            if (spots[index].Enabled)
                return index;
        }
        return -1;
    }

    public static void RunSelfTest()
    {
        var route = new List<SpotConfig>
        {
            new(),
            new() { Enabled = false },
            new()
        };
        var spot = 0;
        var cycles = 0;
        for (var reaction = 1; reaction <= 4; reaction++)
        {
            var result = AdvanceSequence(spot, cycles, route, 2);
            spot = result.NextSpot;
            cycles = result.CompletedCycles;
            if (result.Finished != (reaction == 4))
                throw new InvalidOperationException("Falha no autoteste do ciclo de spots.");
        }
        if (spot != 0 || cycles != 2)
            throw new InvalidOperationException("Falha no estado final do ciclo de spots.");
        if (FormatTime(TimeSpan.FromSeconds(3661)) != "01:01:01")
            throw new InvalidOperationException("Falha no formato do contador de sessão.");
        if (HasSessionExpired(TimeSpan.FromSeconds(3599), 60)
            || !HasSessionExpired(TimeSpan.FromHours(1), 60))
            throw new InvalidOperationException("Falha no limite do contador de sessão.");
        if (!IsActiveState(ProfileState.Searching) || IsActiveState(ProfileState.Error))
            throw new InvalidOperationException("Falha no estado de procura automática da barra.");
        var nextSearch = DateTimeOffset.UnixEpoch.AddSeconds(BarSearchIntervalSeconds);
        if (IsBarSearchDue(nextSearch.AddMilliseconds(-1), nextSearch)
            || !IsBarSearchDue(nextSearch, nextSearch))
            throw new InvalidOperationException("Falha no intervalo de procura automática da barra.");

        var profile = new WindowProfile
        {
            HealthBar = new ScreenRegion { Width = 100, Height = 10 },
            FullHealthRedWidth = 100,
            TeleportPoint = new ClickPointConfig { Configured = true },
            UseSpots = false
        };
        if (!profile.IsConfigured)
            throw new InvalidOperationException("O modo sem spots deveria estar configurado.");
        profile.TeleportMode = "Random";
        if (profile.IsConfigured)
            throw new InvalidOperationException("O modo Random deveria exigir seu próprio ponto.");
        profile.RandomTeleportPoint = new ClickPointConfig { Configured = true };
        if (!profile.IsConfigured)
            throw new InvalidOperationException("O modo Random configurado deveria estar pronto.");
        if (!ReferenceEquals(SelectedTeleport(profile), profile.RandomTeleportPoint))
            throw new InvalidOperationException("O modo Random não selecionou o ponto correto.");
        profile.TeleportMode = "Safe";
        if (!ReferenceEquals(SelectedTeleport(profile), profile.TeleportPoint))
            throw new InvalidOperationException("O modo Safe não selecionou o ponto correto.");
        profile.UseSpots = true;
        if (profile.IsConfigured)
            throw new InvalidOperationException("O modo com spots deveria exigir a rota completa.");
        profile.SpotWindowRegion = new ScreenRegion { Width = 20, Height = 20 };
        profile.SpotWindowReferencePng = [1];
        profile.SpotMenuPoint = new ClickPointConfig { Configured = true };
        profile.ConfirmTeleportPoint = new ClickPointConfig { Configured = true };
        profile.Spots.Add(new SpotConfig());
        if (!profile.IsConfigured)
            throw new InvalidOperationException("A rota completa de spots deveria estar configurada.");
        profile.TeleportRetryCount = 99;
        profile.TeleportMode = "inválido";
        var config = new AppConfig { Windows = [profile, new()] };
        config.Normalize();
        if (profile.TeleportRetryCount != 20)
            throw new InvalidOperationException("Falha no limite de tentativas do teleporte.");
        if (profile.TeleportMode != "Safe")
            throw new InvalidOperationException("Um tipo de teleporte inválido deveria voltar para Safe.");
    }

    enum ProfileState
    {
        Stopped,
        Monitoring,
        Reacting,
        Stabilizing,
        Searching,
        Completed,
        SessionExpired,
        Error
    }

    sealed record OverviewUi(
        Label Target,
        Label Protection,
        Label Life,
        Label Loss,
        Label State,
        Label Detail,
        Label Next,
        Label Time,
        Label Remaining);

    sealed class ProfileUi : IDisposable
    {
        public WindowProfile Profile { get; }
        public ComboBox Window { get; }
        public Label BarStatus { get; }
        public Label TeleportStatus { get; }
        public Label SafeTeleportStatus { get; }
        public Label RandomTeleportStatus { get; }
        public Label SpotWindowStatus { get; }
        public Label SpotMenuStatus { get; }
        public Label ConfirmTeleportStatus { get; }
        public Label SpotMatch { get; }
        public PictureBox Preview { get; }
        public CheckedListBox Spots { get; }
        public Label StateLabel { get; }
        public Label Progress { get; }
        public Label Detected { get; }
        public Label CaptureStatus { get; }
        public Label TimeLabel { get; }
        public Label RemainingTimeLabel { get; }
        public BrandProgressBar LifeMeter { get; }
        public Label LifePercent { get; }
        public Label LifeLoss { get; }
        public System.Diagnostics.Stopwatch SessionWatch { get; } = new();
        public ProfileState State { get; set; } = ProfileState.Stopped;
        public int NextSpotIndex { get; set; }
        public int CompletedCycles { get; set; }
        public int LossConfirmations { get; set; }
        public bool UpdatingSpotChecks { get; set; }
        public Bitmap? StableCandidate { get; private set; }
        public Bitmap? SpotWindowReference { get; private set; }
        public WindowCapture? Capture { get; set; }
        public DateTimeOffset StableSince { get; set; }
        public DateTimeOffset RearmNotBefore { get; set; }
        public DateTimeOffset NextBarSearchAt { get; set; }
        public ProfileState ResumeAfterSearch { get; set; } = ProfileState.Monitoring;

        public ProfileUi(
            WindowProfile profile,
            ComboBox window,
            Label barStatus,
            Label teleportStatus,
            Label safeTeleportStatus,
            Label randomTeleportStatus,
            Label spotWindowStatus,
            Label spotMenuStatus,
            Label confirmTeleportStatus,
            Label spotMatch,
            PictureBox preview,
            CheckedListBox spots,
            Label stateLabel,
            Label progress,
            Label detected,
            Label captureStatus,
            Label timeLabel,
            BrandProgressBar lifeMeter,
            Label lifePercent,
            Label lifeLoss,
            Label remainingTimeLabel)
        {
            Profile = profile;
            Window = window;
            BarStatus = barStatus;
            TeleportStatus = teleportStatus;
            SafeTeleportStatus = safeTeleportStatus;
            RandomTeleportStatus = randomTeleportStatus;
            SpotWindowStatus = spotWindowStatus;
            SpotMenuStatus = spotMenuStatus;
            ConfirmTeleportStatus = confirmTeleportStatus;
            SpotMatch = spotMatch;
            Preview = preview;
            Spots = spots;
            StateLabel = stateLabel;
            Progress = progress;
            Detected = detected;
            CaptureStatus = captureStatus;
            TimeLabel = timeLabel;
            LifeMeter = lifeMeter;
            LifePercent = lifePercent;
            LifeLoss = lifeLoss;
            RemainingTimeLabel = remainingTimeLabel;

            if (profile.SpotWindowReferencePng.Length > 0)
            {
                try
                {
                    using var stream = new MemoryStream(profile.SpotWindowReferencePng);
                    using var bitmap = new Bitmap(stream);
                    SpotWindowReference = new Bitmap(bitmap);
                }
                catch
                {
                    SpotWindowReference = null;
                }
            }
        }

        public void SetStableCandidate(Bitmap bitmap)
        {
            StableCandidate?.Dispose();
            StableCandidate = new Bitmap(bitmap);
        }

        public void SetSpotWindowReference(Bitmap bitmap)
        {
            SpotWindowReference?.Dispose();
            SpotWindowReference = new Bitmap(bitmap);
        }

        public void ResetStableCandidate()
        {
            StableCandidate?.Dispose();
            StableCandidate = null;
        }

        public void ClearRuntime()
        {
            State = ProfileState.Stopped;
            ResumeAfterSearch = ProfileState.Monitoring;
            SessionWatch.Reset();
            LossConfirmations = 0;
            DisposeImages();
        }

        public void DisposeCapture()
        {
            Capture?.Dispose();
            Capture = null;
            CaptureStatus.Text = "Captura: parada";
        }

        public void DisposeImages()
        {
            ResetStableCandidate();
        }

        public void Dispose()
        {
            SessionWatch.Stop();
            DisposeCapture();
            DisposeImages();
            SpotWindowReference?.Dispose();
            SpotWindowReference = null;
            Preview.Image?.Dispose();
            Preview.Image = null;
        }
    }
}

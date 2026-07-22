namespace ControlarTela;

static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        if (args.Contains("--visual-test", StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                ApplicationConfiguration.Initialize();
                RunVisualTest();
                return 0;
            }
            catch (Exception exception)
            {
                File.WriteAllText(Path.Combine(Path.GetTempPath(), "ControlarTela-visual-test-error.txt"), exception.ToString());
                return 1;
            }
        }

        if (args.Contains("--self-test", StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                NativeMethods.RunSelfTest();
                Recognition.RunSelfTest();
                Updater.RunSelfTest();
                MainForm.RunSelfTest();
                ApplicationConfiguration.Initialize();
                using var form = new MainForm(false)
                {
                    StartPosition = FormStartPosition.Manual,
                    Location = new Point(-32000, -32000),
                    ShowInTaskbar = false
                };
                form.Show();
                var scale = form.DeviceDpi / 96F;
                form.Size = new Size((int)(1100 * scale), (int)(680 * scale));
                Application.DoEvents();
                if (form.BackColor != Color.FromArgb(7, 9, 9))
                    throw new InvalidOperationException("A identidade visual Ronaldinho não foi aplicada.");
                var pages = form.Controls.Find("WindowPage", true);
                if (pages.Length != 2)
                    throw new InvalidOperationException("A interface deve conter exatamente duas janelas.");
                if (form.Controls.Find("ProtectionEnabled", true).Length != 2)
                    throw new InvalidOperationException("Cada janela deve permitir ativar ou desativar a proteção.");
                if (pages.Any(page => page.Controls.Find("LifePercent", true).Length != 1
                                      || page.Controls.Find("SpotsList", true).Length != 1
                                      || page.Controls.Find("SessionGroup", true).Length != 1
                                      || page.Controls.Find("AdvancedGroup", true).Length != 1
                                      || page.Controls.Find("LifeModule", true).Length != 1
                                      || page.Controls.Find("SpotsModule", true).Length != 1))
                    throw new InvalidOperationException("A interface visual compacta não foi montada por completo.");
                foreach (var name in new[] { "RefreshWindows", "StartStop" })
                    AssertInside(RequiredVisible(form, name));
                if (new[] { "LifeActions", "SpotsToggleSettings", "TeleportSettings", "SessionSettings" }
                    .Any(name => form.Controls.Find(name, true).Any(control => control.Visible)))
                    throw new InvalidOperationException("A visão geral deve exibir apenas status.");
                if (!RequiredVisible(form, "GlobalOverview").Visible
                    || form.Controls.Find("OverviewCard", true).Count(control => control.Visible) != 2)
                    throw new InvalidOperationException("A visão geral deve exibir as duas janelas.");

                FindAll(form).OfType<Button>().First(button => button.Text.Trim().EndsWith("JANELA")).PerformClick();
                Application.DoEvents();
                foreach (var name in new[] { "WindowSelector", "ProtectionEnabled" })
                    AssertInside(RequiredVisible(form, name));
                if (RequiredVisible(form, "ProtectionEnabled").Width > 220)
                    throw new InvalidOperationException("O controle de proteção voltou a se afastar do texto.");

                var routeNav = FindAll(form).OfType<Button>().First(button => button.Text.Contains("ROTA DE SPOTS"));
                routeNav.PerformClick();
                Application.DoEvents();
                var activePage = pages.Single(page => page.Visible);
                if (!activePage.Controls.Find("SpotsModule", true).Single().Visible
                    || new[] { "LifeModule", "TeleportModule", "SessionGroup" }
                        .Any(name => activePage.Controls.Find(name, true).Single().Visible))
                    throw new InvalidOperationException("A navegação lateral não isolou o módulo de spots.");
                AssertInside(RequiredVisible(form, "UseSpots"));
                foreach (var text in new[] { "JANELA DE SPOTS", "ABRIR MENU", "BOTÃO TELEPORTAR" })
                    AssertInside(RequiredVisibleButton(form, text));
                var spotsList = (CheckedListBox)RequiredVisible(form, "SpotsList");
                if (spotsList.ClientSize.Height / spotsList.ItemHeight < 5)
                    throw new InvalidOperationException("A lista de spots deve exibir cinco linhas completas.");
                AssertInside(FindAll(form).OfType<Button>().First(button => button.Visible && button.Text.StartsWith("＋")));
                AssertInside(RequiredVisibleButton(form, "REMOVER"));
                var resetSpots = FindAll(form).OfType<Button>()
                    .FirstOrDefault(button => button.Visible && button.Text.StartsWith("↻ REINICIAR"))
                    ?? throw new InvalidOperationException("Botão de reiniciar spots não encontrado.");
                AssertInside(resetSpots);

                FindAll(form).OfType<Button>().First(button => button.Text.Contains("BARRA DE VIDA")).PerformClick();
                Application.DoEvents();
                if (RequiredVisible(form, "LifeActions").Width > 270)
                    throw new InvalidOperationException("Os botões da barra voltaram a se afastar da leitura.");
                var lifePercent = (Label)RequiredVisible(form, "LifePercent");
                if (lifePercent.ClientSize.Height < lifePercent.GetPreferredSize(Size.Empty).Height)
                    throw new InvalidOperationException("O percentual da vida está recortado verticalmente.");

                FindAll(form).OfType<Button>().First(button => button.Text.Contains("TELEPORTE")).PerformClick();
                Application.DoEvents();
                AssertInside(RequiredVisible(form, "TeleportMode"));
                foreach (var text in new[] { "MARCAR SAFE", "MARCAR RANDOM" })
                    AssertInside(RequiredVisibleButton(form, text));

                FindAll(form).OfType<Button>().First(button => button.Text.Contains("SESSÃO")).PerformClick();
                Application.DoEvents();
                foreach (var text in new[] { "⌖ RECALIBRAR", "▷ TESTAR" })
                    AssertInside(RequiredVisibleButton(form, text));

                FindAll(form).OfType<Button>().First(button => button.Text.Contains("VISÃO GERAL")).PerformClick();
                Application.DoEvents();
                if (!RequiredVisible(form, "GlobalOverview").Visible || pages.Any(page => page.Visible))
                    throw new InvalidOperationException("A visão geral não restaurou o resumo das duas janelas.");
                FindAll(form).OfType<Button>().First(button => button.Text.Contains("CONFIGURAÇÕES")).PerformClick();
                Application.DoEvents();
                var advancedGroup = RequiredVisible(form, "AdvancedGroup");
                var viewport = RequiredVisible(form, "Viewport");
                if (advancedGroup.Width < viewport.ClientSize.Width - 80)
                    throw new InvalidOperationException("As opções avançadas foram comprimidas horizontalmente.");
                return 0;
            }
            catch (Exception exception)
            {
                File.WriteAllText(Path.Combine(Path.GetTempPath(), "ControlarTela-self-test-error.txt"), exception.ToString());
                return 1;
            }
        }

        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
        return 0;
    }

    static void RunVisualTest()
    {
        var output = Path.Combine(Path.GetTempPath(), "ControlarTela-visual-test");
        Directory.CreateDirectory(output);
        using var form = new MainForm(false)
        {
            StartPosition = FormStartPosition.Manual,
            Location = new Point(-32000, -32000),
            ShowInTaskbar = false
        };
        form.Show();
        var scale = form.DeviceDpi / 96F;
        CaptureSet("wide", 1280, 720);
        CaptureSet("compact", 1100, 680);

        void CaptureSet(string prefix, int width, int height)
        {
            form.Size = new Size((int)(width * scale), (int)(height * scale));
            Application.DoEvents();
            CaptureSection("VISÃO GERAL", $"{prefix}-overview");
            CaptureSection("BARRA DE VIDA", $"{prefix}-life");
            CaptureSection("TELEPORTE", $"{prefix}-teleport");
            CaptureSection("ROTA DE SPOTS", $"{prefix}-spots");
            CaptureSection("CONFIGURAÇÕES", $"{prefix}-advanced");
        }

        void CaptureSection(string navigationText, string fileName)
        {
            FindAll(form).OfType<Button>().First(button => button.Text.Contains(navigationText)).PerformClick();
            Application.DoEvents();
            Capture(fileName);
        }

        void Capture(string fileName)
        {
            using var bitmap = new Bitmap(form.ClientSize.Width, form.ClientSize.Height);
            form.DrawToBitmap(bitmap, form.ClientRectangle);
            bitmap.Save(Path.Combine(output, $"{fileName}.png"));
        }
    }

    static Control RequiredVisible(Control root, string name) =>
        root.Controls.Find(name, true).FirstOrDefault(control => control.Visible)
        ?? throw new InvalidOperationException($"Controle visível não encontrado: {name}.");

    static Button RequiredVisibleButton(Control root, string text) =>
        FindAll(root).OfType<Button>().FirstOrDefault(button => button.Visible && button.Text == text)
        ?? throw new InvalidOperationException($"Botão visível não encontrado: {text}.");

    static IEnumerable<Control> FindAll(Control root)
    {
        foreach (Control control in root.Controls)
        {
            yield return control;
            foreach (var child in FindAll(control))
                yield return child;
        }
    }

    static void AssertInside(Control control)
    {
        const int borderTolerance = 2;
        var parent = control.Parent
                     ?? throw new InvalidOperationException($"Controle sem contêiner: {control.Name} {control.Text}.");
        if (control.Left < -borderTolerance || control.Top < -borderTolerance
            || control.Right > parent.ClientSize.Width + borderTolerance
            || control.Bottom > parent.ClientSize.Height + borderTolerance)
            throw new InvalidOperationException(
                $"Controle recortado: {control.Name} {control.Text}; bounds={control.Bounds}; parent={parent.ClientSize}.");
    }
}

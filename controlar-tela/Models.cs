using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ControlarTela;

sealed class ScreenRegion
{
    public int X { get; set; }
    public int Y { get; set; }
    public int Width { get; set; }
    public int Height { get; set; }

    [JsonIgnore]
    public bool IsConfigured => Width > 1 && Height > 1;
}

sealed class ClickPointConfig
{
    public int X { get; set; }
    public int Y { get; set; }
    public bool Configured { get; set; }
}

sealed class SpotConfig
{
    public string Name { get; set; } = "Spot";
    public int X { get; set; }
    public int Y { get; set; }
    public bool Enabled { get; set; } = true;

    public override string ToString() => $"{Name}  ({X}, {Y})";
}

sealed class WindowProfile
{
    public string Name { get; set; } = "Janela";
    public string WindowTitle { get; set; } = "";
    public string ProcessName { get; set; } = "";
    public bool ProtectionEnabled { get; set; } = true;
    public bool BackgroundMode { get; set; } = true;
    public ScreenRegion HealthBar { get; set; } = new();
    public int FullHealthRedWidth { get; set; }
    public ClickPointConfig TeleportPoint { get; set; } = new();
    public ClickPointConfig RandomTeleportPoint { get; set; } = new();
    public string TeleportMode { get; set; } = "Safe";
    public ScreenRegion SpotWindowRegion { get; set; } = new();
    public byte[] SpotWindowReferencePng { get; set; } = [];
    public ClickPointConfig SpotMenuPoint { get; set; } = new();
    public ClickPointConfig ConfirmTeleportPoint { get; set; } = new();
    public bool UseSpots { get; set; } = true;
    public BindingList<SpotConfig> Spots { get; set; } = [];
    public decimal SpotWindowMinimumSimilarity { get; set; } = 80;
    public decimal DropLimitPercent { get; set; } = 10;
    public int CycleCount { get; set; } = 1;
    public int SessionLimitMinutes { get; set; } = 60;
    public int TeleportToSpotDelayMs { get; set; } = 1000;
    public int TeleportRetryCount { get; set; } = 5;
    public int RearmDelayMs { get; set; } = 5000;
    public int StableTimeMs { get; set; } = 2000;

    [JsonIgnore]
    public bool IsConfigured => HealthBar.IsConfigured
                                && FullHealthRedWidth > 0
                                && (string.Equals(TeleportMode, "Random", StringComparison.OrdinalIgnoreCase)
                                    ? RandomTeleportPoint.Configured
                                    : TeleportPoint.Configured)
                                && (!UseSpots
                                    || (SpotWindowRegion.IsConfigured
                                        && SpotWindowReferencePng.Length > 0
                                        && SpotMenuPoint.Configured
                                        && ConfirmTeleportPoint.Configured
                                        && Spots.Any(spot => spot.Enabled)));
}

sealed class AppConfig
{
    public int SchemaVersion { get; set; } = 5;
    public int CaptureIntervalMs { get; set; } = 300;
    public List<WindowProfile> Windows { get; set; } = [];

    public void Normalize()
    {
        SchemaVersion = 5;
        CaptureIntervalMs = Math.Clamp(CaptureIntervalMs, 100, 2000);
        while (Windows.Count < 2)
            Windows.Add(new WindowProfile { Name = $"Janela {Windows.Count + 1}" });
        if (Windows.Count > 2)
            Windows.RemoveRange(2, Windows.Count - 2);

        foreach (var profile in Windows)
        {
            profile.HealthBar ??= new ScreenRegion();
            profile.FullHealthRedWidth = Math.Clamp(profile.FullHealthRedWidth, 0, Math.Max(0, profile.HealthBar.Width));
            profile.TeleportPoint ??= new ClickPointConfig();
            profile.RandomTeleportPoint ??= new ClickPointConfig();
            profile.TeleportMode = string.Equals(profile.TeleportMode, "Random", StringComparison.OrdinalIgnoreCase)
                ? "Random"
                : "Safe";
            profile.SpotWindowRegion ??= new ScreenRegion();
            profile.SpotWindowReferencePng ??= [];
            profile.SpotMenuPoint ??= new ClickPointConfig();
            profile.ConfirmTeleportPoint ??= new ClickPointConfig();
            profile.Spots ??= [];
            profile.SpotWindowMinimumSimilarity = Math.Clamp(profile.SpotWindowMinimumSimilarity, 50, 100);
            profile.DropLimitPercent = Math.Clamp(profile.DropLimitPercent, 1, 90);
            profile.CycleCount = Math.Clamp(profile.CycleCount, 1, 999);
            profile.SessionLimitMinutes = Math.Clamp(profile.SessionLimitMinutes, 1, 10_080);
            profile.TeleportToSpotDelayMs = Math.Clamp(profile.TeleportToSpotDelayMs, 100, 10_000);
            profile.TeleportRetryCount = Math.Clamp(profile.TeleportRetryCount, 1, 20);
            profile.RearmDelayMs = Math.Clamp(profile.RearmDelayMs, 1000, 60_000);
            profile.StableTimeMs = Math.Clamp(profile.StableTimeMs, 500, 10_000);
        }
    }
}

static class ConfigStore
{
    static readonly string Folder = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ControlarTela");

    public static string FilePath => Path.Combine(Folder, "config.json");

    static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    public static AppConfig Load(out string? warning)
    {
        warning = null;
        if (!File.Exists(FilePath))
        {
            var fresh = new AppConfig();
            fresh.Normalize();
            return fresh;
        }

        try
        {
            var json = File.ReadAllText(FilePath);
            using var document = JsonDocument.Parse(json);
            var isOld = !document.RootElement.TryGetProperty(nameof(AppConfig.SchemaVersion), out var version)
                        || version.GetInt32() < 3;
            var config = JsonSerializer.Deserialize<AppConfig>(json, JsonOptions)
                         ?? new AppConfig();
            if (isOld)
                warning = "A rota de spots foi atualizada. Configure a janela, o menu e o botão Teleportar.";
            config.Normalize();
            return config;
        }
        catch (Exception error)
        {
            warning = $"Configuração inválida preservada em {FilePath}: {error.Message}";
            var fresh = new AppConfig();
            fresh.Normalize();
            return fresh;
        }
    }

    public static void Save(AppConfig config)
    {
        config.Normalize();
        Directory.CreateDirectory(Folder);
        var temporary = FilePath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(config, JsonOptions));
        if (File.Exists(FilePath))
            File.Copy(FilePath, FilePath + ".bak", true);
        File.Move(temporary, FilePath, true);
    }
}

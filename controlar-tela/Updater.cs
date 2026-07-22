using System.Net.Http.Headers;
using System.Reflection;
using System.Text;
using System.Text.Json;

namespace ControlarTela;

static class Updater
{
    const string LatestReleaseUrl = "https://api.github.com/repos/Carvalho3009/ronaldinho-protecao/releases/latest";
    const string AssetName = "ControlarTela.exe";

    public sealed record UpdateInfo(Version Version, string Tag, string DownloadUrl);

    public static Version CurrentVersion => Normalize(
        Assembly.GetExecutingAssembly().GetName().Version ?? new Version(1, 0, 0));

    public static async Task<UpdateInfo?> CheckAsync()
    {
        using var client = CreateClient();
        return ParseRelease(await client.GetStringAsync(LatestReleaseUrl), CurrentVersion);
    }

    public static async Task InstallAndRestartAsync(UpdateInfo update)
    {
        var currentExe = Environment.ProcessPath
            ?? throw new InvalidOperationException("Não foi possível localizar o executável atual.");
        if (!Path.GetFileName(currentExe).Equals(AssetName, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("A atualização automática funciona somente no executável portátil.");

        var tempDirectory = Path.Combine(Path.GetTempPath(), $"Ronaldinho-{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempDirectory);
        var downloadedExe = Path.Combine(tempDirectory, AssetName);

        using (var client = CreateClient())
        using (var response = await client.GetAsync(update.DownloadUrl, HttpCompletionOption.ResponseHeadersRead))
        {
            response.EnsureSuccessStatusCode();
            await using var source = await response.Content.ReadAsStreamAsync();
            await using var destination = File.Create(downloadedExe);
            await source.CopyToAsync(destination);
        }

        await using (var file = File.OpenRead(downloadedExe))
        {
            if (file.Length < 1_000_000 || file.ReadByte() != 'M' || file.ReadByte() != 'Z')
                throw new InvalidDataException("O arquivo de atualização recebido não é um executável válido.");
        }

        var script = $$"""
            $ErrorActionPreference = 'Stop'
            Wait-Process -Id {{Environment.ProcessId}} -ErrorAction SilentlyContinue
            Copy-Item -LiteralPath '{{Quote(downloadedExe)}}' -Destination '{{Quote(currentExe)}}' -Force
            Start-Process -FilePath '{{Quote(currentExe)}}'
            Remove-Item -LiteralPath '{{Quote(tempDirectory)}}' -Recurse -Force
            """;
        var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
        _ = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments = $"-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {encoded}",
            UseShellExecute = false,
            CreateNoWindow = true
        }) ?? throw new InvalidOperationException("Não foi possível iniciar a instalação da atualização.");
    }

    static HttpClient CreateClient()
    {
        var client = new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
        client.DefaultRequestHeaders.UserAgent.Add(
            new ProductInfoHeaderValue("Ronaldinho", CurrentVersion.ToString(3)));
        client.DefaultRequestHeaders.Accept.Add(
            new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        return client;
    }

    static UpdateInfo? ParseRelease(string json, Version currentVersion)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        var tag = root.GetProperty("tag_name").GetString()
            ?? throw new InvalidDataException("A versão publicada não possui identificação.");
        if (!Version.TryParse(tag.TrimStart('v', 'V'), out var parsedVersion))
            throw new InvalidDataException($"A versão publicada '{tag}' é inválida.");

        var version = Normalize(parsedVersion);
        if (version <= Normalize(currentVersion))
            return null;

        foreach (var asset in root.GetProperty("assets").EnumerateArray())
        {
            if (!string.Equals(asset.GetProperty("name").GetString(), AssetName, StringComparison.OrdinalIgnoreCase))
                continue;
            var url = asset.GetProperty("browser_download_url").GetString();
            if (!string.IsNullOrWhiteSpace(url))
                return new UpdateInfo(version, tag, url);
        }
        throw new InvalidDataException($"A versão {tag} não contém o arquivo {AssetName}.");
    }

    static Version Normalize(Version version) =>
        new(version.Major, version.Minor, Math.Max(0, version.Build));

    static string Quote(string value) => value.Replace("'", "''");

    public static void RunSelfTest()
    {
        const string release = """
            {"tag_name":"v1.2.0","assets":[{"name":"ControlarTela.exe","browser_download_url":"https://example.test/ControlarTela.exe"}]}
            """;
        var update = ParseRelease(release, new Version(1, 1, 0, 0));
        if (update?.Version != new Version(1, 2, 0) || update.DownloadUrl != "https://example.test/ControlarTela.exe")
            throw new InvalidOperationException("Falha no autoteste do atualizador.");
        if (ParseRelease(release, new Version(1, 2, 0, 0)) is not null)
            throw new InvalidOperationException("O atualizador ofereceu a versão já instalada.");
    }
}

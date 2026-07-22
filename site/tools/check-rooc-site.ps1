$ErrorActionPreference = "Stop"
$webRoot = Resolve-Path (Join-Path $PSScriptRoot "..\web")
$siteRoot = Resolve-Path (Join-Path $webRoot "rooc-am")
$pages = "index.html", "guia.html", "classes.html", "primeira-semana.html", "sistemas.html", "faq.html", "validacao.html"
$errors = [System.Collections.Generic.List[string]]::new()

foreach ($page in $pages) {
  $path = Join-Path $siteRoot $page
  if (-not (Test-Path -LiteralPath $path)) { $errors.Add("Arquivo ausente: $page"); continue }
  $html = Get-Content -LiteralPath $path -Raw
  if ($html -notmatch '<main') { $errors.Add("Sem <main>: $page") }
  if ($html -match 'href="[^"]+\.md(?:#|\")') { $errors.Add("Link Markdown não convertido: $page") }

  [regex]::Matches($html, '(?:href|src)="([^"]+)"') | ForEach-Object {
    $target = $_.Groups[1].Value.Split('#')[0]
    if (-not $target -or $target -match '^(?:https?:|mailto:|data:)') { return }
    $resolved = if ($target.StartsWith('/')) { Join-Path $webRoot $target.TrimStart('/') } else { Join-Path $siteRoot $target }
    if (-not (Test-Path -LiteralPath $resolved)) { $errors.Add("Destino ausente em ${page}: $target") }
  }

  [regex]::Matches($html, 'href="([^"#]*#([^"]+))"') | ForEach-Object {
    $href = $_.Groups[1].Value
    if ($href -match '^(?:https?:|mailto:|data:)') { return }
    $target, $fragment = $href.Split('#', 2)
    $fragment = [uri]::UnescapeDataString($fragment)
    $targetHtml = if (-not $target) { $html } else {
      $resolved = if ($target.StartsWith('/')) { Join-Path $webRoot $target.TrimStart('/') } else { Join-Path $siteRoot $target }
      if (Test-Path -LiteralPath $resolved) { Get-Content -LiteralPath $resolved -Raw }
    }
    if ($targetHtml -and $targetHtml -notmatch "id=`"$([regex]::Escape($fragment))`"") { $errors.Add("Âncora ausente em ${page}: $href") }
  }
}

$homeHtml = Get-Content -LiteralPath (Join-Path $siteRoot "index.html") -Raw
$classesHtml = Get-Content -LiteralPath (Join-Path $siteRoot "classes.html") -Raw
$weekHtml = Get-Content -LiteralPath (Join-Path $siteRoot "primeira-semana.html") -Raw
if ($homeHtml -notmatch 'id="class-quiz"' -or $homeHtml -notmatch 'classes\.html#lord-knight') { $errors.Add("Quiz ou âncora inicial de classe ausente") }
foreach ($anchor in "lord-knight", "paladin", "high-wizard", "professor", "sniper", "minstrel", "gypsy", "assassin-cross", "stalker", "high-priest", "champion", "whitesmith-mastersmith", "creator-biochemist", "summoner-doram") {
  if ($classesHtml -notmatch "id=`"$anchor`"") { $errors.Add("Âncora de classe ausente: $anchor") }
}
if ($weekHtml -notmatch 'data-user-checklist' -or $weekHtml -notmatch 'data-checklist-item') { $errors.Add("Checklist por perfil ausente") }

if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }
Write-Host "ROOC site OK: $($pages.Count) páginas, links e assets locais válidos."

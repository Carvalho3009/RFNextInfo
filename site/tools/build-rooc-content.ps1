$ErrorActionPreference = "Stop"

$sourceRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\rooc-americas\conteudo")
$outputRoot = Resolve-Path (Join-Path $PSScriptRoot "..\web\rooc-am")

$pages = @(
  @{ Source = "GUIA-ROOC-AMERICAS.md"; Output = "guia.html"; Description = "VisÃ£o completa do servidor Americas: preparaÃ§Ã£o, evoluÃ§Ã£o, economia, conteÃºdos, agenda e rotina." },
  @{ Source = "FICHAS-DE-CLASSE.md"; Output = "classes.html"; Description = "Identidade, rotas, pontos fortes e decisÃµes de investimento para as 14 classes confirmadas." },
  @{ Source = "PLANO-PRIMEIRA-SEMANA.md"; Output = "primeira-semana.html"; Description = "Um roteiro de sete dias para desbloquear sistemas, testar a build e preservar recursos raros." },
  @{ Source = "SISTEMAS-E-DECISOES.md"; Output = "sistemas.html"; Description = "Atributos, habilidades, equipamentos, refino, cartas, economia e critÃ©rios de upgrade." },
  @{ Source = "FAQ-E-GLOSSARIO.md"; Output = "faq.html"; Description = "Respostas rÃ¡pidas e termos essenciais para acompanhar o jogo sem confundir versÃµes regionais." },
  @{ Source = "MATRIZ-DE-VALIDACAO.md"; Output = "validacao.html"; Description = "Checklist editorial para substituir referÃªncias provisÃ³rias por evidÃªncias do cliente Americas." }
)

$links = @{
  "GUIA-ROOC-AMERICAS.md" = "guia.html"
  "FICHAS-DE-CLASSE.md" = "classes.html"
  "PLANO-PRIMEIRA-SEMANA.md" = "primeira-semana.html"
  "SISTEMAS-E-DECISOES.md" = "sistemas.html"
  "FAQ-E-GLOSSARIO.md" = "faq.html"
  "MATRIZ-DE-VALIDACAO.md" = "validacao.html"
}

$header = @'
  <a class="skip-link" href="#conteudo">Pular para o conteÃºdo</a>
  <header class="site-header frame-line">
    <a class="brand" href="index.html" aria-label="Karvalho â€” inÃ­cio do guia">
      <img class="brand-full" src="../assets/karvalho-primary-gold.png" alt="Karvalho">
      <img class="brand-symbol" src="../assets/karvalho-symbol-gold.png" alt="">
      <span class="brand-mobile">GUIA ROOC</span>
    </a>
    <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="site-nav"><span>MENU</span><i aria-hidden="true"></i></button>
    <nav id="site-nav" class="site-nav" aria-label="NavegaÃ§Ã£o principal">
      <a href="index.html">INÃCIO</a><a href="guia.html">GUIA</a><a href="classes.html">CLASSES</a><a href="primeira-semana.html">1Âª SEMANA</a><a href="sistemas.html">SISTEMAS</a><a href="faq.html">FAQ</a>
    </nav>
    <span class="language" aria-label="Idioma atual: portuguÃªs">PT</span>
  </header>
'@

$footer = @'
  <footer class="site-footer page-shell frame-line">
    <img src="../assets/karvalho-symbol-gold.png" alt="" aria-hidden="true">
    <div><strong>KARVALHO</strong><span>CLARO. CURIOSO. SEM ENROLAÃ‡ÃƒO.</span></div>
    <p>Guia independente. Ragnarok Ã© propriedade de seus respectivos titulares.</p>
  </footer>
  <script src="script.js"></script>
'@

for ($index = 0; $index -lt $pages.Count; $index++) {
  $page = $pages[$index]
  $markdown = Get-Content -LiteralPath (Join-Path $sourceRoot $page.Source) -Raw
  $title = [regex]::Match($markdown, '(?m)^#\s+(.+)$').Groups[1].Value
  $content = (ConvertFrom-Markdown -InputObject $markdown).Html
  $content = [regex]::Replace($content, '<h1[^>]*>.*?</h1>\s*', '', 'Singleline')
  foreach ($entry in $links.GetEnumerator()) {
    $content = $content.Replace("./$($entry.Key)", $entry.Value).Replace($entry.Key, $entry.Value)
  }
  $content = [regex]::Replace($content, '<a href="(https?://[^"]+)"', '<a href="$1" target="_blank" rel="noreferrer"')
  $content = [regex]::Replace($content, '(<table>.*?</table>)', '<div class="content-table">$1</div>', 'Singleline')

  if ($page.Output -eq "primeira-semana.html") {
    $controls = @'
<div class="checklist-profile ornamental-box">
  <div><p>O progresso fica salvo neste navegador e separado pelo nome do perfil.</p><strong id="checklist-status" aria-live="polite">Escolha um perfil local para comeÃ§ar.</strong></div>
  <form id="profile-form" class="profile-form"><label>PERFIL LOCAL<input id="profile-name" name="profile" list="saved-profiles" maxlength="32" autocomplete="off" required></label><datalist id="saved-profiles"></datalist><button type="submit">USAR PERFIL</button></form>
  <button id="reset-checklist" class="reset-checklist" type="button">ZERAR CHECKLIST DESTE PERFIL</button>
</div>
'@
    $content = $content.Replace('<h2 id="checklist-copiavel">Checklist copiÃ¡vel</h2>', '<section class="user-checklist" data-user-checklist><h2 id="checklist-copiavel">Checklist por perfil</h2>' + $controls)
    $content = [regex]::Replace($content, '<li class="task-list-item"><input disabled="disabled" type="checkbox" />\s*(.*?)</li>', '<li class="task-list-item"><label><input type="checkbox" data-checklist-item disabled><span>$1</span></label></li>')
    $content = [regex]::Replace($content, '(<section class="user-checklist".*?<ul class="contains-task-list">.*?</ul>)', '$1</section>', 'Singleline')
  }

  $toc = [regex]::Matches($content, '<h2 id="([^"]+)">(.*?)</h2>') | ForEach-Object {
    $label = [regex]::Replace($_.Groups[2].Value, '<[^>]+>', '')
    "<a href=`"#$($_.Groups[1].Value)`">$label</a>"
  }

  $previous = if ($index -gt 0) { "<a href=`"$($pages[$index - 1].Output)`">â† $([regex]::Match((Get-Content -LiteralPath (Join-Path $sourceRoot $pages[$index - 1].Source) -Raw), '(?m)^#\s+(.+)$').Groups[1].Value)</a>" } else { "<a href=`"index.html`">â† InÃ­cio do guia</a>" }
  $next = if ($index -lt $pages.Count - 1) { "<a href=`"$($pages[$index + 1].Output)`">$([regex]::Match((Get-Content -LiteralPath (Join-Path $sourceRoot $pages[$index + 1].Source) -Raw), '(?m)^#\s+(.+)$').Groups[1].Value) â†’</a>" } else { "<a href=`"index.html`">InÃ­cio do guia â†’</a>" }

  $document = @"
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="$($page.Description)">
  <title>$title â€” Karvalho</title>
  <link rel="icon" href="../assets/karvalho-symbol-gold.png">
  <link rel="stylesheet" href="styles.css">
</head>
<body class="article-page">
$header
  <main id="conteudo">
    <section class="article-hero page-shell">
      <p class="article-kicker">GUIA ROOC AMERICAS</p>
      <h1>$title</h1>
      <p>$($page.Description)</p>
    </section>
    <div class="article-layout page-shell">
      <aside class="article-toc" aria-label="NavegaÃ§Ã£o nesta pÃ¡gina"><strong>NESTA PÃGINA</strong><nav>$($toc -join "`n")</nav></aside>
      <article class="article-content">$content</article>
    </div>
    <nav class="article-pager" aria-label="NavegaÃ§Ã£o entre cadernos">$previous$next</nav>
  </main>
$footer
</body>
</html>
"@
  Set-Content -LiteralPath (Join-Path $outputRoot $page.Output) -Value $document -Encoding utf8
}

Write-Host "Geradas $($pages.Count) pÃ¡ginas editoriais em $outputRoot"


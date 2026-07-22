Add-Type -AssemblyName System.Drawing

$src = Join-Path $env:USERPROFILE 'Pictures\Screenshots\Captura de tela 2026-06-11 012849.png'
$outDir = Join-Path (Get-Location) 'public\rf-icons\races'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Crop-Content($bmp, $rect) {
  $minX = $rect.Width
  $minY = $rect.Height
  $maxX = 0
  $maxY = 0

  for ($y = 0; $y -lt $rect.Height; $y++) {
    for ($x = 0; $x -lt $rect.Width; $x++) {
      $p = $bmp.GetPixel($rect.X + $x, $rect.Y + $y)
      if (($p.R + $p.G + $p.B) -gt 80 -and [Math]::Max($p.R, [Math]::Max($p.G, $p.B)) -gt 45) {
        if ($x -lt $minX) { $minX = $x }
        if ($y -lt $minY) { $minY = $y }
        if ($x -gt $maxX) { $maxX = $x }
        if ($y -gt $maxY) { $maxY = $y }
      }
    }
  }

  if ($maxX -le $minX -or $maxY -le $minY) {
    return New-Object System.Drawing.Rectangle($rect.X, $rect.Y, $rect.Width, $rect.Height)
  }

  $pad = 5
  [int]$cropX0 = [Math]::Max(0, $rect.X + $minX - $pad)
  [int]$cropY0 = [Math]::Max(0, $rect.Y + $minY - $pad)
  [int]$cropX1 = [Math]::Min($bmp.Width - 1, $rect.X + $maxX + $pad)
  [int]$cropY1 = [Math]::Min($bmp.Height - 1, $rect.Y + $maxY + $pad)
  return New-Object System.Drawing.Rectangle($cropX0, $cropY0, ($cropX1 - $cropX0 + 1), ($cropY1 - $cropY0 + 1))
}

function Make-Icon($bmp, $rect, $path) {
  $content = Crop-Content $bmp $rect
  $source = $bmp.Clone($content, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $icon = New-Object System.Drawing.Bitmap(64, 64, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($icon)
  $g.Clear([System.Drawing.Color]::Transparent)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $scale = [Math]::Min(52 / $content.Width, 52 / $content.Height)
  $w = [int]($content.Width * $scale)
  $h = [int]($content.Height * $scale)
  $dest = New-Object System.Drawing.Rectangle([int]((64 - $w) / 2), [int]((64 - $h) / 2), $w, $h)
  $g.DrawImage($source, $dest)
  $g.Dispose()
  $icon.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $icon.Dispose()
  $source.Dispose()
}

function Draw-Icon($g, $path, $x, $y, $size) {
  $img = [System.Drawing.Image]::FromFile($path)
  $g.DrawImage($img, $x, $y, $size, $size)
  $img.Dispose()
}

$bmp = [System.Drawing.Bitmap]::FromFile($src)
$segmentWidth = [int]($bmp.Width / 6)

$bellPath = Join-Path $outDir 'bell.png'
$coraPath = Join-Path $outDir 'cora.png'
$accPath = Join-Path $outDir 'acc.png'

Make-Icon $bmp (New-Object System.Drawing.Rectangle(0, 0, $segmentWidth, $bmp.Height)) $bellPath
Make-Icon $bmp (New-Object System.Drawing.Rectangle([int](($bmp.Width - $segmentWidth) / 2), 0, $segmentWidth, $bmp.Height)) $coraPath
Make-Icon $bmp (New-Object System.Drawing.Rectangle(($bmp.Width - $segmentWidth), 0, $segmentWidth, $bmp.Height)) $accPath
$bmp.Dispose()

$previewPath = Join-Path $outDir 'race-icons-preview.png'
$preview = New-Object System.Drawing.Bitmap(420, 120, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($preview)
$g.Clear([System.Drawing.Color]::FromArgb(6, 10, 20))
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$font = New-Object System.Drawing.Font('Segoe UI', 9)
$brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(210, 220, 245))

$labels = @('Bell', 'Cora', 'Acc', 'Bell/Cora', 'Todas')
$xs = @(22, 102, 182, 268, 355)
for ($i = 0; $i -lt $labels.Length; $i++) {
  $g.DrawString($labels[$i], $font, $brush, $xs[$i] - 2, 88)
}

Draw-Icon $g $bellPath 18 20 48
Draw-Icon $g $coraPath 98 20 48
Draw-Icon $g $accPath 178 20 48
Draw-Icon $g $bellPath 258 24 42
Draw-Icon $g $coraPath 283 24 42
Draw-Icon $g $bellPath 350 36 34
Draw-Icon $g $coraPath 371 20 34
Draw-Icon $g $accPath 392 36 34

$g.Dispose()
$preview.Save($previewPath, [System.Drawing.Imaging.ImageFormat]::Png)
$preview.Dispose()

Write-Output $previewPath

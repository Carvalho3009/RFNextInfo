Add-Type -AssemblyName System.Drawing

$src = Join-Path $env:USERPROFILE 'Downloads\rf_icons_transparent.png'
$outDir = Join-Path (Get-Location) 'public\rf-icons\races'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Save-Crop($bmp, $name, $rect) {
  $x = [Math]::Max(0, [Math]::Min($bmp.Width - 1, $rect.X))
  $y = [Math]::Max(0, [Math]::Min($bmp.Height - 1, $rect.Y))
  $w = [Math]::Min($rect.Width, $bmp.Width - $x)
  $h = [Math]::Min($rect.Height, $bmp.Height - $y)
  $safeRect = New-Object System.Drawing.Rectangle($x, $y, $w, $h)
  $crop = $bmp.Clone($safeRect, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $path = Join-Path $outDir "$name.png"
  $crop.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $crop.Dispose()
  return $path
}

function Draw-Preview($g, $path, $x, $y, $w, $h, $label) {
  $img = [System.Drawing.Image]::FromFile($path)
  $g.DrawImage($img, $x, $y, $w, $h)
  $img.Dispose()
  $font = New-Object System.Drawing.Font('Segoe UI', 10)
  $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(230, 238, 255))
  $g.DrawString($label, $font, $brush, $x, ($y + $h + 8))
  $font.Dispose()
  $brush.Dispose()
}

$bmp = [System.Drawing.Bitmap]::FromFile($src)

function New-ScaledRect($x, $y, $w, $h) {
  $sx = $bmp.Width / 2048
  $sy = $bmp.Height / 1152
  return New-Object System.Drawing.Rectangle([int]($x * $sx), [int]($y * $sy), [int]($w * $sx), [int]($h * $sy))
}

$items = @(
  @{ Name='bell';      Label='Bell';      Rect=(New-ScaledRect 310 40 380 340) },
  @{ Name='cora';      Label='Cora';      Rect=(New-ScaledRect 820 45 430 335) },
  @{ Name='acc';       Label='Acc';       Rect=(New-ScaledRect 1375 50 390 315) },
  @{ Name='bell_cora'; Label='Bell/Cora'; Rect=(New-ScaledRect 255 420 520 330) },
  @{ Name='bell_acc';  Label='Bell/Acc';  Rect=(New-ScaledRect 765 420 520 330) },
  @{ Name='cora_acc';  Label='Cora/Acc';  Rect=(New-ScaledRect 1285 420 520 330) },
  @{ Name='all';       Label='Todas';     Rect=(New-ScaledRect 720 760 620 360) }
)

$paths = @()
foreach ($item in $items) {
  $paths += @{ Path=(Save-Crop $bmp $item.Name $item.Rect); Label=$item.Label }
}
$bmp.Dispose()

$previewPath = Join-Path $outDir 'race-symbols-preview.png'
$preview = New-Object System.Drawing.Bitmap(1100, 620, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($preview)
$g.Clear([System.Drawing.Color]::FromArgb(6, 10, 20))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

Draw-Preview $g $paths[0].Path 40 30 170 150 $paths[0].Label
Draw-Preview $g $paths[1].Path 260 30 190 150 $paths[1].Label
Draw-Preview $g $paths[2].Path 500 30 180 150 $paths[2].Label
Draw-Preview $g $paths[3].Path 40 250 230 145 $paths[3].Label
Draw-Preview $g $paths[4].Path 320 250 230 145 $paths[4].Label
Draw-Preview $g $paths[5].Path 600 250 230 145 $paths[5].Label
Draw-Preview $g $paths[6].Path 835 205 230 135 $paths[6].Label

$g.Dispose()
$preview.Save($previewPath, [System.Drawing.Imaging.ImageFormat]::Png)
$preview.Dispose()

Write-Output $previewPath

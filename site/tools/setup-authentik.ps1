$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root 'infra\authentik.env'

if (Test-Path -LiteralPath $target) {
    throw "O arquivo '$target' já existe. Ele não foi sobrescrito."
}

function New-Secret([int]$Bytes) {
    $buffer = New-Object byte[] $Bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($buffer)
    } finally {
        $generator.Dispose()
    }
    [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$postgresPassword = New-Secret 36
$authentikSecret = New-Secret 60

$content = @"
POSTGRES_DB=authentik
POSTGRES_USER=authentik
POSTGRES_PASSWORD=$postgresPassword
AUTHENTIK_POSTGRESQL__HOST=authentik-postgresql
AUTHENTIK_POSTGRESQL__NAME=authentik
AUTHENTIK_POSTGRESQL__USER=authentik
AUTHENTIK_POSTGRESQL__PASSWORD=$postgresPassword
AUTHENTIK_SECRET_KEY=$authentikSecret
"@
[IO.File]::WriteAllText($target, $content, (New-Object Text.UTF8Encoding($false)))

$postgresPassword = $authentikSecret = $content = $null
Write-Output 'Segredos do Authentik criados localmente. Nenhum valor foi exibido.'

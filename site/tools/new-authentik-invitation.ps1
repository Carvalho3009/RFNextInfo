param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9_.-]{2,31}$')]
    [string]$Username,
    [ValidateRange(1, 365)]
    [int]$ValidDays = 30
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$username = $Username.ToLowerInvariant()
$python = @"
from datetime import timedelta
from django.utils import timezone
from authentik.core.models import User
from authentik.flows.models import Flow
from authentik.stages.invitation.models import Invitation
username = '$username'
flow = Flow.objects.get(slug='karvalho-first-access')
Invitation.objects.filter(name='Primeiro acesso - ' + username).delete()
invite = Invitation.objects.create(
    name='Primeiro acesso - ' + username,
    flow=flow,
    single_use=True,
    expiring=True,
    expires=timezone.now() + timedelta(days=$ValidDays),
    created_by=User.objects.get(username='carvalho'),
    fixed_data={'username': username, 'name': username.capitalize()},
)
print('https://auth.karvalho.dev.br/if/flow/karvalho-first-access/?itoken=' + str(invite.invite_uuid) + '&next=%2Fapplication%2Flaunch%2Fprojetos-karvalho%2F')
"@

Push-Location $root
try {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $output = docker compose exec -e AUTHENTIK_LOG_LEVEL=warning authentik-server ak shell -v 0 --no-imports -c $python 2>$null
        $dockerExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($dockerExitCode -ne 0) { throw 'Não foi possível criar o convite.' }
    $link = $output | Where-Object { $_ -like 'https://*' } | Select-Object -Last 1
    if (-not $link) { throw 'O Authentik não retornou o endereço do convite.' }
    $link
} finally {
    Pop-Location
}

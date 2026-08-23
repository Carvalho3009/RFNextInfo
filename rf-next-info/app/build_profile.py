from __future__ import annotations

import base64
from urllib.parse import urlsplit


PROFILE_NAME = "beta"
PROFILE_LABEL = "Beta"
APP_VERSION = "2.0.0-beta.8"
RELEASE_SEQUENCE = 18

LICENSE_SERVER = "https://rflicenca.karvalho.dev.br"
SITE_SERVER = "https://rfnext.karvalho.dev.br"
# Receptor exclusivo do RF QOL Agent. Permanece vazio até existir um domínio
# dedicado homologado; nunca reutilizar SITE_SERVER/RF Next para este fluxo.
AGENT_SERVER = ""
SITE_FEATURES = frozenset({
    "character",
    "market",
    "codex",
    "memory_chips",
    "inventory",
    "subsession",
    "export",
    "observations",
    "pve-observations",
    "exp-ranking",
    "auction-bank",
    "pvp-sync",
})
MACHINE_STATE_NAME = "RF QOL Beta"
INSTANCE_SERVER_NAME = "RFQOL.Beta.App"

LEASE_V3_PUBLIC_KEYS = {
    "lease-v3-beta-2026-08": "JgiiNU8HOnVmgdt8TecTLk61Bz3fJcdE3qizfAEloi8",
}


def validate_build_profile(*, release: bool = False) -> None:
    if PROFILE_NAME not in {"staging", "beta", "production"}:
        raise RuntimeError("Perfil de build desconhecido")
    if release and PROFILE_NAME == "staging":
        raise RuntimeError("Perfil de staging não pode gerar release")
    if PROFILE_NAME == "staging":
        parsed = urlsplit(LICENSE_SERVER)
        if (
            APP_VERSION != "2.0.0-rc1"
            or PROFILE_LABEL != "Homologação"
            or RELEASE_SEQUENCE != 10
            or parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 8788
            or parsed.path not in {"", "/"}
            or SITE_SERVER != "https://rfnext.karvalho.dev.br"
            or SITE_FEATURES != {"market", "exp-ranking", "auction-bank"}
            or MACHINE_STATE_NAME != "RF QOL Staging"
            or INSTANCE_SERVER_NAME != "RFQOL.Staging.App"
            or set(LEASE_V3_PUBLIC_KEYS) != {"lease-v3-staging-2026-01"}
        ):
            raise RuntimeError("Perfil de staging inconsistente")
    elif PROFILE_NAME == "beta":
        parsed = urlsplit(LICENSE_SERVER)
        if (
            APP_VERSION != "2.0.0-beta.8"
            or PROFILE_LABEL != "Beta"
            or RELEASE_SEQUENCE != 18
            or parsed.scheme != "https"
            or parsed.hostname != "rflicenca.karvalho.dev.br"
            or parsed.path not in {"", "/"}
            or SITE_SERVER != "https://rfnext.karvalho.dev.br"
            or SITE_FEATURES != {
                "character", "market", "codex", "memory_chips",
                "inventory", "subsession", "export", "observations",
                "pve-observations", "exp-ranking", "auction-bank", "pvp-sync",
            }
            or MACHINE_STATE_NAME != "RF QOL Beta"
            or INSTANCE_SERVER_NAME != "RFQOL.Beta.App"
            or set(LEASE_V3_PUBLIC_KEYS) != {"lease-v3-beta-2026-08"}
        ):
            raise RuntimeError("Perfil beta inconsistente")
    else:
        parsed = urlsplit(LICENSE_SERVER)
        if (
            PROFILE_LABEL != "Produção"
            or "-" in APP_VERSION
            or parsed.scheme != "https"
            or parsed.hostname != "rflicenca.karvalho.dev.br"
            or parsed.path not in {"", "/"}
            or SITE_SERVER != "https://rfnext.karvalho.dev.br"
            or not SITE_FEATURES
            or MACHINE_STATE_NAME != "RF QOL"
            or INSTANCE_SERVER_NAME != "RFQOL.App"
            or not LEASE_V3_PUBLIC_KEYS
            or any("staging" in key for key in LEASE_V3_PUBLIC_KEYS)
        ):
            raise RuntimeError("Perfil de produção inconsistente")
    for key_id, encoded in LEASE_V3_PUBLIC_KEYS.items():
        if not key_id.startswith("lease-v3-"):
            raise RuntimeError("Identificador de chave pública v3 inválido")
        try:
            public_key = base64.urlsafe_b64decode(
                encoded + "=" * (-len(encoded) % 4)
            )
        except (TypeError, ValueError) as error:
            raise RuntimeError("Chave pública v3 inválida") from error
        if len(public_key) != 32:
            raise RuntimeError("Chave pública v3 inválida")
    if AGENT_SERVER:
        agent = urlsplit(AGENT_SERVER)
        if (
            agent.scheme != "https"
            or not agent.hostname
            or agent.username is not None
            or agent.password is not None
            or agent.query
            or agent.fragment
            or AGENT_SERVER.rstrip("/") == SITE_SERVER.rstrip("/")
            or agent.hostname == "rfnext.karvalho.dev.br"
        ):
            raise RuntimeError("Servidor do Agent deve ser HTTPS e separado do RF Next")

# Karvalho

Portal e projetos hospedados no PC por Docker, publicados por Cloudflare Tunnel sem abrir portas no roteador.

## Iniciar localmente

Requisitos: Docker Desktop aberto.

```powershell
docker compose up -d
```

Endereços:

- Portal: <http://localhost:8088>
- Guias ROOC AM: <http://ragnarok.localhost:8088>
- Calculadora RF Next: <http://rfnext.localhost:8088>
- Authentik: <http://auth.localhost:8088>

No portal, os cartões apontam para os subdomínios públicos para que as políticas do Cloudflare Access não possam ser contornadas pelo domínio principal.

Para parar:

```powershell
docker compose down
```

## Publicar pelo Cloudflare Tunnel

1. Aguarde `karvalho.dev.br` ficar ativo na Cloudflare após a troca dos nameservers.
2. No Cloudflare Zero Trust, crie um túnel do tipo Cloudflared e escolha Docker como ambiente.
3. Copie `.env.example` para `.env` e preencha `TUNNEL_TOKEN` localmente. O token é secreto e não deve ser enviado por chat nem commitado.
4. No túnel, configure as rotas abaixo, todas apontando para `http://gateway:80`:

| Host público | Serviço interno |
| --- | --- |
| `karvalho.dev.br` | `http://gateway:80` |
| `www.karvalho.dev.br` | `http://gateway:80` |
| `ragnarok.karvalho.dev.br` | `http://gateway:80` |
| `rfnext.karvalho.dev.br` | `http://gateway:80` |
| `auth.karvalho.dev.br` | `http://gateway:80` |

5. Inicie a pilha com o perfil do túnel:

```powershell
docker compose --profile tunnel up -d
```

O contêiner Cloudflared cria somente uma conexão de saída. Nenhuma porta do roteador precisa ser aberta.

## Controle de acesso

O Authentik gerencia usuários, senhas, sessões e convites de uso único. O portal principal permanece público; Ragnarok, RFEXP e PokeIdle passam pelo `forward_auth` do Caddy.

Antes do primeiro início, gere os segredos localmente (os valores não são exibidos):

```powershell
.\tools\setup-authentik.ps1
docker compose --profile tunnel up -d
```

No primeiro início, abra <http://auth.localhost:8088> e defina a senha do administrador `akadmin`. Depois crie um provedor **Proxy / Forward auth (domain level)** para `karvalho.dev.br`, usando `https://auth.karvalho.dev.br` como URL de autenticação, e associe-o ao outpost incorporado.

Crie convites individuais e de uso único no painel do Authentik. Predefina o `username` em minúsculas (`carvalho`, `duffita`, `kojiro`, `luiz` e `xonz`) para manter o mesmo perfil no RFEXP. O RFEXP recebe `X-Authentik-Username` do gateway e usa esse nome como proprietário do perfil e do histórico.

Para criar ou substituir um convite de primeiro acesso pelo PowerShell:

```powershell
.\tools\new-authentik-invitation.ps1 -Username duffita
```

O endereço retornado é individual, expira em 30 dias, deixa de funcionar após o primeiro uso e encaminha o usuário ao RFEXP. Gerar outro convite para o mesmo usuário revoga o anterior.

## Atualizar os projetos

O ROOC AM é estático. Os cadernos-fonte ficam em `..\ROOC AM\conteudo` e são convertidos pelo PowerShell nativo:

```powershell
.\tools\build-rooc-content.ps1
.\tools\check-rooc-site.ps1
```

A calculadora existente já está integrada pela imagem local `rf-next-calculadora:local`. Recompile essa imagem no diretório do projeto antes de atualizar a pilha. Se um projeto precisar de backend, troque apenas o serviço correspondente no `compose.yml`; o gateway e o túnel continuam iguais.

Os dados da calculadora ficam no volume Docker `rfnext-data`. Para atualizar sem apagar os históricos:

```powershell
docker compose up -d --force-recreate rfnext gateway
```

## Operação e segurança

- Não exponha portas dos serviços de projeto; somente o gateway está acessível em `127.0.0.1:8088`.
- Nunca versionar `.env`, tokens ou credenciais.
- Faça backup dos volumes `authentik-database` e `authentik-data`; sem o banco, usuários e configurações são perdidos.
- A rota RF Next permite script e estilo embutidos porque a aplicação atual é um HTML autocontido; remova essa exceção quando ela for separada em arquivos estáticos.
- Mantenha Docker Desktop, Caddy e Cloudflared atualizados.
- Faça backup do projeto e dos dados persistentes antes de atualizar aplicações futuras.
- Consulte logs com `docker compose logs -f --tail=100`.

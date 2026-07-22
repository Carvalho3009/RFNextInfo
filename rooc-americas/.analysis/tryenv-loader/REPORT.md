# TryEnv Loader — análise estática inicial

Data da análise: 2026-07-17

## Escopo

A amostra foi extraída e lida, mas não executada. Nenhum arquivo foi enviado a serviços de terceiros.

## Identificação

- ZIP SHA-256: `7BF4884E1794F0468EEAACFA61C133A1148E920DEB2D3DC37C33A8B5A409E8AB`
- EXE SHA-256: `6859B02BE721BB0790B349F924E5B1A970FC86CB44853BD18588278950B97BB1`
- EXE MD5: `0787B3B4176CD543961C9AA648E6067C`
- Tamanho: 17.327.104 bytes
- Arquitetura: Windows x64, GUI nativa
- Metadados: `tryenv-moduler`, empresa `tryenv`, versão `0.1.0`
- Assinatura Authenticode: ausente
- Timestamp do cabeçalho PE: `2026-04-25 07:31:15 UTC` (pode ser alterado pelo produtor)

## Construção

O executável foi produzido em Rust com Tauri. Strings preservadas identificam, entre outras, as versões Tauri `2.10.3`, reqwest `0.12.28`, Tokio `1.52.1` e Hyper `1.9.0`. O binário tem seções PE normais, não tem overlay e não apresenta sinal óbvio de packer comum.

## Fluxo observado

Evidência estática indica este fluxo:

1. A interface Tauri chama um comando interno `load_module`.
2. O loader recebe dados de jogo/configuração, incluindo literais como `exe`, `desc`, `dev_dll`, `download_url` e `load_virtual`.
3. Ele possui cliente HTTP e mensagens próprias de erro: `download_badStatus`, `download_tooLarge`, `download_requestFailed`, `download_readFailed` e `download_clientFailed`.
4. Ele procura processos por snapshot (`CreateToolhelp32Snapshot`, `Process32FirstW`, `Process32NextW`).
5. A rotina de carga usa `OpenProcess`, `VirtualAllocEx`, `WriteProcessMemory`, `CreateRemoteThread` e `LoadLibraryA`. Esse conjunto implementa a injeção clássica de uma DLL por caminho no processo-alvo.
6. Há rotinas de arquivo temporário/limpeza, indicadas por `safeWrite_removed`, `safeWrite_blocked`, `tempfile_removed` e `tempfile_blocked`.

Também aparecem `ReadProcessMemory`, APIs de entrada (`SendInput`, `GetAsyncKeyState`) e rede. Parte dessas APIs pode vir das dependências do Tauri; o encadeamento de download e injeção, porém, é específico do código em `src\core.rs`.

## Avaliação

O arquivo é um carregador de módulo, não a automação completa. A lógica principal do cheat provavelmente reside na DLL baixada em tempo de execução e injetada no processo do jogo.

Risco técnico: **alto para execução em máquina pessoal**. O modelo entrega código remoto que passa a rodar dentro de outro processo, com os mesmos privilégios do usuário. A ausência de assinatura impede verificar a identidade do produtor. Isso não prova que seja malware, mas o loader tem capacidade suficiente para executar qualquer comportamento contido na DLL entregue pelo servidor.

Não foi encontrado endpoint operacional em texto simples nem resultado público para o SHA-256 exato. O endereço pode estar no frontend Tauri comprimido, ser recebido em tempo de execução ou variar por configuração.

## Presença pública

Há anúncios públicos atribuídos ao usuário/vendedor `tryenv` que descrevem o produto como automação/hack para Ragnarok Origin e Classic, incluindo auto-quest, auto-skill, auto-battle, auto-eventos, auto-farm, auto-trade, speed hack e inspeção de entidades/equipamentos:

- https://www.elitepvpers.com/forum/trading/5294884-ragnarok-origin-hack-auto-skill-auto-battle-auto-events-auto-farm.html
- https://www.dfg.com.br/pt/ragnarok-online/outros/hack-origin-avancado-999602737

Esses anúncios associam o nome ao produto, mas não autenticam esta amostra específica.

## Próxima etapa segura

Executar somente em VM descartável com snapshot, sem contas ou credenciais reais, capturando:

- processo-alvo escolhido;
- URL, DNS e certificado usados no download;
- DLL criada/baixada antes da remoção;
- hash e assinatura da DLL;
- arquivos, registro, processos-filhos e conexões de rede.

A DLL capturada deve passar por nova análise estática antes de permanecer em execução.

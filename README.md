# RF Next Companion Agent 2.0.0-beta.54

Publicado em 21/09/2026 17:48 — horário de Brasília (UTC−3).

- A captura passa a usar Pktmon/ETW como padrão, com filtros TCP aplicados antes da entrega dos pacotes ao Agent. A alteração responde à recorrência de queda da conexão durante downloads na beta.53.
- O teste local desta modalidade durante download terminou sem queda: 60,47 segundos, 6.875 pacotes capturados, nenhum pacote rejeitado pelo filtro Python e nenhum erro de captura. Esse teste curto não comprova estabilidade prolongada no Agent completo.
- Decodificação, envio ao site, fila e recuperação de sessões mantêm o fluxo existente.

Validação: 714 testes (712 aprovados, dois ignorados), autoteste empacotado e instalação/desinstalação isoladas aprovados. 33 módulos e cinco arquivos de dados conferidos no instalador. Manifesto e procedência assinados com Ed25519. Sem Authenticode, conforme política do produto.

Atualize pelo Agent ou pelo [instalador beta.54](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.54/RF-Next-Companion-Setup-2.0.0-beta.54.exe). Não é necessário limpar a fila de envios.

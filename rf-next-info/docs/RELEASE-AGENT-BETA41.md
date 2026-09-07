# RF Next Companion 2.0.0-beta.41

Base: beta.40 (`37854f2`). Sequência do atualizador: 51.

- Reprocessa o perfil quando as referências dos equipamentos ativos chegam
  depois dele, inclusive por outra conexão ou após correlação parcial. Mantém confirmação de personagem,
  isolamento entre clientes/sessões, deduplicação e limite do cache pendente.
- Descarta o perfil pendente ao terminar a sessão ou substituir sua identidade.
- Outbox WAL usa `synchronous=FULL`: sincroniza os eventos e sua sequência em
  disco antes de enviá-los, reduzindo reutilização de sequências após queda de energia.
- Contrato de transporte permanece `2.0.0-beta.6`, já aceito pelo receptor.

Não inclui o backend experimental do Windows 10. Mantém a captura Pktmon streaming
da beta.40. Não altera o servidor nem a base de dados do usuário na instalação.

Não usa Authenticode, UPX, drivers adicionais nem alterações no antivírus.
Distribuição exige manifesto Ed25519, hash do instalador e testes automáticos.

Validação específica cobre chegada do perfil antes/depois da aparência, dois
clientes, UID não confirmado, sessão encerrada, repetição da aparência e
durabilidade/monotonicidade da sequência ao reabrir a outbox.
Testes sintéticos não substituem nova observação dos equipamentos após instalar.
Uma captura perdida pela beta.40 não pode ser recriada apenas ao instalar a atualização.

Validação de código: 134 testes específicos aprovados; regressão final com
614 testes em 75,166 s, sem falhas e com 1 ignorado. A verificação do executável
empacotado também exige a correlação de perfil parcial com referências tardias.

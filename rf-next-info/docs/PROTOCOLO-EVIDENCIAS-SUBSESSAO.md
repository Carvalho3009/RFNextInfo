# Evidências necessárias para estados da subsessão

O RF QOL não deve inferir MAU, launcher ou poção de EXP por semelhança textual
ou por um único pacote. Os campos das subsessões ficam em
`Aguardando captura validada` até que cada semântica passe pelo protocolo abaixo.

Drops não dependem do texto do chat. A origem oficial no RF QOL é o evento de
recompensa enviado pelo servidor, já decodificado como `drop_item_field`. Somente
resultados confirmados (`ret=0`) com ItemIndex e quantidade válidos entram no
histórico e nos alertas; EXP, créditos e contribuição são removidos.

Para cada recurso, coletar ao menos três séries independentes com:

1. baseline de 60 segundos sem a ação;
2. início marcado e ação isolada;
3. manutenção suficiente para observar renovações;
4. término, desmontagem ou expiração marcado;
5. repetição com outro personagem e outra sessão;
6. comparação negativa com ações parecidas.

Séries exigidas:

- MAU: entrar, permanecer, sair e ser destruído;
- launcher: equipar, disparar, trocar de arma e desequipar;
- poção de EXP: consumir, renovar antes do fim e observar expiração.

Somente campos presentes de forma repetida e exclusiva podem alimentar o estado
`detected`. O decoder canônico em `core/rfnext_frame_decode.py` continua sendo a
única origem; não criar um parser paralelo.

# RF Next Companion beta.63

Corrige a origem de EXP, facção e mercado por personagem e conexão. Usa world_id explícito da lista sanitizada de personagens e confirmação direta da conexão; não deduz servidor por IP ou número do UID. Ausência/conflito mantém origem desconhecida; páginas de ranking com evidências diferentes não se completam entre si.

783 testes: 781 aprovados e 2 ignorados. Contrato e projeção do site atual testados em SQLite descartável com Hecate 4 e Menkar 4. Autoteste empacotado, instalador isolado e comparação dos módulos aprovados. Manifesto e procedência Ed25519 verificados. Publicação autorizada em 04/11/2026; atualização disponível pelo canal beta.

Ainda não instalado nem validado em captura real. Após instalar, iniciar captura antes de entrar no personagem para observar lista e identidade; jogo já aberto pode permanecer sem origem até essa leitura. Conflito exige nova captura com evidência fresca. Não reclassifica históricos antigos. Instalador sem Authenticode conforme política do produto.

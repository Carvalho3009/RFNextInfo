# Validação v39

O agent-organizer reproduziu o problema e verificou os callbacks irmãos. O callback da identificação da conta capturava `label` por referência; ao final de `build()`, ela continha o texto de outro controle.

O novo teste `test_resize_callbacks_after_build_keep_their_widget` falhou antes da correção com o mesmo traceback fornecido pelo usuário. Após a correção, dispara todos os callbacks Configure registrados depois da montagem do shell, usando larguras 640 e 40, e verifica o wraplength do widget da conta.

26 testes direcionados passaram: shell, multicontas, consulta completa e execução de listas. Os testes não operam janelas reais nem abrem conexões ao jogo. A comparação antes/depois comprova a correção da referência capturada; não substitui avaliação visual manual.

O pacote passa por CRC, comparação dos fontes, repetição do teste de redimensionamento após extração e verificação SHA-256 do download publicado.

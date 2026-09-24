# Validação v37

- Suite completa: `python -m unittest discover -s tests -q`: 264 testes, 257 aprovados e 7 ignorados por ausência de capturas de referência.
- Após o ajuste final de espaçamento: `python -m unittest tests.test_desktop_shell tests.test_desktop_list_flow tests.test_product_ui tests.test_complete -q`: 29 testes aprovados.
- Cobertura nova: navegação, tamanho/fallback de fonte, árvore produto/refino/oferta, IDs de 64 bits, associação exata do vendedor, persistência da lista, cancelamento, resultado incerto sem repetição, seleção do modo de compra e limites das propostas do site.
- Interface testada por objetos simulados, sem controle de tela. Avaliação visual e teste em outro computador permanecem manuais.
- Nenhuma compra real ou alteração no site foi executada.

O pacote é verificado por CRC, igualdade dos fontes incluídos e SHA-256. Arquivos de estado de compras e preferências locais não devem integrar a distribuição.

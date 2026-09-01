# RF NEXT INFO

- Produto Windows para captura passiva e decodificação do cliente PC RF NEXT Brasil 1.28.5.
- Reutilize o decoder canônico de `K:\MCP\Karvalho\rf-next`; não invente semântica.
- Captura primária: Pktmon nativo. Não inclua Npcap, injeção, hooks invasivos, UPX, ofuscação ou bypass de antivírus.
- Interface e arte devem seguir integralmente `K:\Karvalho\Identidade Visual Karvalho\SKILL.md`.
- Kills são estimadas por recompensa; campos não confirmados ficam ocultos.
- Nenhum token/ticket de sessão ou payload `0x0101` pode ser salvo ou exibido.
- Por decisão do owner, executável e instalador não usam Authenticode; release pública exige manifesto e procedência Ed25519, hashes e testes limpos.
- Alterações não devem publicar releases nem mudar produção sem validação final.
- Toda mudança ou adição deve preservar as funcionalidades já existentes. Antes
  de considerar o trabalho concluído, executar testes específicos do novo
  comportamento e a suíte automática de regressão; qualquer regressão conhecida
  deve ser corrigida ou registrada explicitamente como bloqueio, nunca aceita
  silenciosamente.

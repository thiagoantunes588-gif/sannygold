# Módulo Frota - Multas e Infrações de Trânsito

## Escopo

Esta etapa implementa uma central interna para notificações de trânsito, prazos, identificação humana do condutor, risco de NIC, documentos, decisões, defesas, recursos, protocolos e pagamentos. Não inclui combustível, tanque, pneus avançados, telemetria, rastreamento em tempo real, scraping governamental, credenciais Gov.br, certificados digitais nem integração não autorizada com órgãos públicos.

## Arquitetura reutilizada

- Flask e Jinja no monólito atual.
- SQLite como armazenamento ativo estruturado, com espelho JSON compatível com o projeto.
- Cadastro existente de `vehicles`, `users`, rotas/eventos, checklists, ocorrências e entregas de veículo.
- `financial_entries` para a despesa, sem um segundo contas a pagar.
- auditoria central em `audit_log` e trilha detalhada em `fleet_infraction_audit_logs`.
- anexos locais protegidos; Dropbox permanece apenas como destino de backup/cópia.
- PDF e Excel gerados pela infraestrutura já existente, sem dependência nova.

## Entidades

### FleetTrafficInfraction

Registro principal com numeração `MULTA-AAAA-000001`, veículo existente, snapshots de placa/Renavam, órgão, auto, local, datas, valores, pontos, situação, responsabilidade, identificação do condutor, risco de NIC e vínculo com a infração original. Exclusão é lógica por `deleted_at`.

A chave natural ativa é órgão autuador + número do auto + placa + data. Duplicidade exata é bloqueada no domínio e no SQLite. Um registro semelhante em outra data exige conferência e justificativa.

### Prazos

`fleet_infraction_deadlines` guarda a data oficial copiada da notificação, data interna, origem, conferente, data da conferência, responsável e conclusão. Nenhum prazo legal universal é codificado. A classificação operacional é: vencido, vence hoje, urgente (até 3 dias), atenção (até 7 dias), preventivo (até 15 dias) e em dia.

As antecedências iniciais são `15, 10, 7, 5, 3, 1, 0` e podem ser alteradas por `fleet.fines.settings.manage`. Concluir uma etapa exige comprovante ou justificativa, responsável e auditoria.

### Identificação do condutor

`fleet_infraction_driver_identifications` conserva sugestão, confiança, evidências, período de responsabilidade, rota e operação. A busca prioriza:

1. entrega de veículo cobrindo data e hora;
2. checklist registrado na data;
3. motorista habitual do veículo.

A sugestão nunca confirma o condutor. Outro usuário autorizado deve revisar e confirmar. O sistema separa motorista provável, confirmado internamente e estados de protocolo/aceitação pelo órgão.

### NIC

O risco é aplicável quando existe proprietário empresarial, a identificação é exigida e ainda não foi regularizada. A proximidade ou perda do prazo muda o risco para atenção, alto risco ou prazo vencido. Uma notificação NIC exige `original_infraction_id`; não pode ser criada sem vínculo com a origem.

### Documentos e anexos

Os checklists documentais são configuráveis por órgão em:

- `fleet_infraction_document_templates`;
- `fleet_infraction_document_template_items`;
- `fleet_infraction_documents`.

CNH, CPF, assinaturas e documentos pessoais recebem marca de sensibilidade. A leitura exige `fleet.fines.sensitive_documents.view`. Os arquivos ficam em:

```text
Frota/Veiculos/PLACA/Multas/ANO/NUMERO_INTERNO/
  Notificacao/
  Indicacao_Condutor/
  Defesa_Previa/
  Recurso_JARI/
  Segunda_Instancia/
  Protocolos/
  Pagamentos/
  Decisoes/
```

O banco guarda metadados, SHA-256 e vínculos. Arquivos não são armazenados como BLOB e o Dropbox não é banco de dados.

### Decisões, processos e protocolos

`fleet_infraction_decisions` registra a escolha humana, responsável, data, justificativa, valores, impacto de pontos, risco NIC e disponibilidade documental. Quando um desconto pode implicar renúncia de defesa ou recurso, a confirmação explícita do aviso é obrigatória.

`fleet_infraction_proceedings` cobre indicação, defesa prévia, JARI, segunda instância, efeito suspensivo, restituição e outros processos. O sistema armazena textos e anexos como materiais editáveis; não produz peça jurídica definitiva.

`fleet_infraction_protocols` exige órgão/canal/data e comprovante. Exceção sem comprovante somente é aceita com autorização e justificativa registradas.

### Pagamentos e financeiro

`fleet_infraction_payments` referencia uma única `financial_entries.id`. O vínculo é idempotente pela nota interna da infração e há índice único sobre `financial_entry_id`. Uma tentativa de pagamento repetido é bloqueada. Responsabilidade do motorista não gera desconto salarial automático.

## Dashboard e central de prazos

A rota protegida `/fleet/fines` apresenta:

- novas notificações e casos em análise;
- condutores não identificados e riscos de NIC;
- prazos em 15, 7 e 3 dias e prazos vencidos;
- pagamentos pendentes/pagos e valores;
- filtros por período, veículo, motorista, órgão, status, tipo e responsabilidade;
- central ordenada por vencido, hoje, 3, 7 e 15 dias;
- ficha com condutor, documentos, processos, protocolos, decisão, pagamento e auditoria.

Motoristas com perfil de leitura veem somente infrações formalmente liberadas e relacionadas ao próprio usuário. Não podem alterar prazo, estratégia, pagamento, documentos ou confirmar a própria identificação.

## Importação e consultas oficiais

A importação `.xlsx` usa o leitor já existente. Placa ou Renavam deve localizar um veículo já cadastrado. Registros importados permanecem como rascunho para conferência humana. PDF e imagens podem ser anexados; não há OCR como fonte única.

Atalhos oficiais são URLs HTTPS configuráveis. Eles apenas abrem o portal e não carregam login, senha, token ou certificado.

## Permissões

- `fleet.fines.view`
- `fleet.fines.create`
- `fleet.fines.edit`
- `fleet.fines.assign`
- `fleet.fines.driver_identify`
- `fleet.fines.documents.manage`
- `fleet.fines.proceedings.manage`
- `fleet.fines.protocol.manage`
- `fleet.fines.decide`
- `fleet.fines.payments.view`
- `fleet.fines.payments.manage`
- `fleet.fines.financial_responsibility.manage`
- `fleet.fines.reports.view`
- `fleet.fines.sensitive_documents.view`
- `fleet.fines.audit.view`
- `fleet.fines.settings.manage`

Administrador possui todas. Operacional administra o fluxo, exceto pagamento e documentos sensíveis. Financeiro visualiza, paga e exporta. O perfil de leitura recebe apenas visualização filtrada quando autorizado como motorista.

## Migrations

Migrations aditivas `20260621_20` a `20260621_31` criam 12 tabelas:

1. `fleet_traffic_infractions`;
2. `fleet_infraction_deadlines`;
3. `fleet_infraction_driver_identifications`;
4. `fleet_infraction_document_templates`;
5. `fleet_infraction_document_template_items`;
6. `fleet_infraction_documents`;
7. `fleet_infraction_proceedings`;
8. `fleet_infraction_protocols`;
9. `fleet_infraction_payments`;
10. `fleet_infraction_attachments`;
11. `fleet_infraction_decisions`;
12. `fleet_infraction_audit_logs`.

Aplicação:

```bash
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py dry-run
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py apply
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py validate
```

## Rollback

Antes de qualquer alteração, `apply` cria snapshot em `backups/migrations/20260621_fleet_fines-AAAAMMDD-HHMMSS`. O snapshot inclui banco, configurações, financeiro e todos os JSON do módulo. Uma falha restaura automaticamente o snapshot.

Rollback manual:

```bash
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py snapshots
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py rollback --snapshot CAMINHO_DO_SNAPSHOT
```

O rollback restaura o banco completo, não executa `DROP TABLE` sobre dados em uso.

## Testes

`tests/test_fleet_fines.py` cobre cadastro, chave natural, possível duplicidade, múltiplas infrações, veículo, sugestão por entrega/rota, confirmação humana, motorista ausente, alertas, prazo vencido, NIC, documentos obrigatórios, protocolo, defesa, JARI, decisão, vínculo financeiro idempotente, dashboard, planilha, correção importada, hash de arquivo, exclusão lógica e migration/rollback.

Comando geral:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest discover tests
```

## Compatibilidade

- macOS e Windows: caminhos são montados com `pathlib`; não há separador fixo nem comando dependente de sistema operacional no módulo.
- celular: layout responsivo, controles nativos e listas convertidas para uma coluna abaixo de 800 px.
- servidor local/LAN: mantém autenticação e permissões atuais; não exige exposição pública.

## Limitações e integrações futuras

- Não consulta situação real em Senatran, Detran, PRF, DNIT ou municípios.
- Não valida juridicamente prazos, decisões, defesa, recurso ou desconto.
- Não envia e-mail, WhatsApp ou SMS nesta fase.
- Não automatiza desconto salarial ou cobrança do motorista.
- O vínculo de escala é limitado aos registros operacionais atualmente disponíveis: entregas, checklists, rotas e motorista habitual.
- Biblioteca empresarial permanente ainda não existe como módulo próprio; documentos societários podem ser referenciados nos metadados sem cópia redundante.
- Extração OCR não foi ativada porque não há infraestrutura confiável existente no projeto.

## Arquivos desta etapa

Criados:

- `app/routes/fleet_fines.py`;
- `app/services/fleet_fines.py`;
- `app/services/fleet_fines_migration.py`;
- `app/templates/fleet_fines.html`;
- `scripts/migrate_fleet_fines.py`;
- `tests/test_fleet_fines.py`;
- `docs/MODULO_FROTA_MULTAS.md`;
- 12 arquivos JSON vazios em `data/`, um para cada entidade migrada.

Alterados:

- `app/db/schema.sql`;
- `app/main.py`;
- `app/repositories/sqlite_repository.py`;
- `app/services/sqlite_migration.py`;
- `app/services/sqlite_store.py`;
- `app/templates/index.html`;
- `data/settings.json`, apenas para configurações iniciais do módulo;
- `data/audit_log.json`, pelo backup preventivo executado antes da migration;
- `data/sannygold.db`, pelas 12 migrations aditivas.

Artefatos operacionais gerados:

- backup local `backups/sannygold-data-backup-20260621-201751-eff28b96.zip`;
- cópia externa no Dropbox configurado para backups;
- snapshot `backups/migrations/20260621_fleet_fines-20260621-201814`.

## Validação executada

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m py_compile app/main.py app/routes/fleet_fines.py app/services/fleet_fines.py app/services/fleet_fines_migration.py
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest tests.test_fleet_fines
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest discover tests
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py dry-run
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py apply
PYTHONPATH=. python3 scripts/migrate_fleet_fines.py validate
sqlite3 data/sannygold.db 'PRAGMA integrity_check; PRAGMA foreign_key_check;'
curl -fsS http://127.0.0.1:5007/health
```

Resultado final: 244 testes aprovados, nenhum reprovado; 26 testes específicos de multas; migration íntegra e sem erro de chave estrangeira. A tela foi validada no navegador em 1280 x 720 e 390 x 844, sem rolagem horizontal ou erro de console.

## Teste manual

1. Abrir `http://127.0.0.1:5007`, entrar e acessar **Frota > Multas**.
2. Cadastrar uma notificação fictícia vinculada ao veículo de teste e informar somente os prazos impressos nela.
3. Conferir a sugestão de condutor, suas evidências e confirmar com outro usuário autorizado.
4. Verificar a central de prazos e o destaque de risco NIC quando aplicável.
5. Anexar uma notificação e um documento marcado como sensível; testar o bloqueio com um perfil sem permissão.
6. Abrir uma defesa ou recurso e registrar protocolo com comprovante.
7. Registrar uma decisão; se houver desconto condicionado, validar o aviso obrigatório.
8. Registrar pagamento e confirmar que existe somente um lançamento em `financial_entries`.
9. Baixar PDF, Excel e modelo de importação; importar uma planilha fictícia e revisar os rascunhos.
10. Arquivar um caso encerrado e confirmar que ele continua no banco com `deleted_at`.

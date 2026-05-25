# Migração gradual JSON -> SQLite

Esta etapa prepara a infraestrutura sem alterar o comportamento do sistema. A aplicação continua lendo e gravando os arquivos JSON atuais.

## Arquivos JSON mapeados

Listas principais:

- `clients.json`: clientes
- `events.json`: eventos/locações
- `equipment.json`: equipamentos
- `vehicles.json`: veículos
- `users.json`: usuários
- `audit_log.json`: auditoria
- `financial_receivables.json`: contas a receber
- `financial_entries.json`: lançamentos financeiros
- `financial_closeouts.json`: fechamentos financeiros

Listas preservadas em tabela genérica nesta primeira fase:

- `contracts.json`
- `quotes.json`
- `service_log.json`
- `attachments.json`
- `route_history.json`
- `warehouse_items.json`
- `warehouse_movements.json`
- `field_confirmations.json`
- `help_knowledge_base.json`
- `help_unanswered_questions.json`
- `help_support_tickets.json`

Documentos JSON:

- `settings.json`
- `operation_validation.json`
- `forecast_audit.json`
- `help_metrics.json`

Backups:

- arquivos `.zip` em `backups/` entram como metadados em `backup_files`, quando existirem.

## Schema inicial

Arquivo: `app/db/schema.sql`

Tabelas de controle:

- `migration_runs`
- `migration_items`

Tabelas principais:

- `clients`
- `events`
- `equipment`
- `vehicles`
- `users`
- `audit_log`
- `financial_receivables`
- `financial_entries`
- `financial_closeouts`

Tabelas de compatibilidade:

- `json_records`: registros de listas ainda não normalizadas.
- `json_documents`: documentos JSON únicos.
- `backup_files`: metadados de backups locais.

Todas as tabelas principais guardam também `payload_json`, `payload_hash`, `source_file` e `migrated_at`. Isso permite validar a migração antes de desligar qualquer JSON.

## Como rodar

Validação sem gravar no banco:

```bash
python3 scripts/migrate_json_to_sqlite.py --dry-run
```

Migração local para `data/sannygold.db`:

```bash
python3 scripts/migrate_json_to_sqlite.py
```

Com caminhos explícitos:

```bash
python3 scripts/migrate_json_to_sqlite.py \
  --data-dir data \
  --db data/sannygold.db \
  --report data/migration_reports/sqlite-migration-manual.json
```

O script:

- cria o banco se ele não existir;
- cria o schema inicial;
- valida tipo de cada JSON;
- não apaga nem altera os JSON originais;
- gera relatório com importados, ignorados e erros;
- importa registros sem ID com chave sintética para revisão, sem impedir a migração.

## O que continua em JSON

Tudo continua em JSON para a aplicação nesta etapa. O SQLite é apenas uma cópia preparada para validação e futura ativação por entidade.

## Próximo passo recomendado

Migrar primeiro `audit_log.json` para leitura em SQLite. É uma entidade de baixo risco porque é majoritariamente append-only e não interfere diretamente nos cadastros operacionais. Depois, migrar financeiro ou clientes com modo dual-write controlado por configuração.

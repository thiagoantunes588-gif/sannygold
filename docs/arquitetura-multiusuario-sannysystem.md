# Arquitetura multiusuário SannySystem

## Decisão central

O sistema deixa de usar SQLite compartilhado como banco ativo. A base transacional passa a ser PostgreSQL, acessada pela aplicação Electron instalada em cada computador.

Dropbox não deve armazenar o diretório físico do PostgreSQL nem qualquer SQLite. Dropbox fica responsável por dados sincronizados separados: snapshots, arquivos de conflito, uploads, exports, backups, logs operacionais e configuração sem segredos.

## Estrutura alvo

Windows:

```text
C:\Program Files\SannySystem
%USERPROFILE%\Dropbox\SannySystemData
```

Mac:

```text
/Applications/SannySystem.app
~/Dropbox/SannySystemData
```

Quando Dropbox não é encontrado, a aplicação usa uma pasta local de contingência em `Application Support/SannySystem/SannySystemData` no Mac ou `AppData/Roaming/SannySystem/SannySystemData` no Windows.

## Estrutura de dados

`SannySystemData` é criada automaticamente com esta estrutura:

```text
SannySystemData/
  logs/
  backups/
  temp/
  exports/
  uploads/
  database/
  config/
  sync/
    snapshots/
  conflicts/
  updates/
```

Uso de cada pasta:

- `logs/`: logs operacionais e de auditoria exportáveis.
- `backups/`: backups gerados pela aplicação.
- `temp/`: staging temporário de arquivos antes de renomeação atômica.
- `exports/`: relatórios e arquivos gerados para envio.
- `uploads/`: anexos operacionais.
- `database/`: somente metadados, manifests e relatórios; nunca banco físico.
- `config/`: `runtime.json` sem segredos, com diagnóstico de ambiente.
- `sync/snapshots/`: snapshots JSON para troca segura entre estações.
- `conflicts/`: material de apoio para resolução de conflito.
- `updates/`: metadados de atualização; instaladores não devem ficar aqui.

## Conteúdo proibido no Dropbox

A validação inicial sinaliza erro se encontrar em `SannySystemData`:

- `node_modules`;
- `.git`;
- `.cache` ou `cache`;
- `dist`, `release`, `build`, `.next` ou `out`;
- `.venv`, `venv` ou `__pycache__`;
- `.exe`, `.msi`, `.dmg`, `.pkg`, `.app`, `.dll`, `.bat`, `.cmd`, `.com`, `.ps1`, `.command`, `.sh`;
- `.db`, `.sqlite` ou `.sqlite3`.

Essa regra evita sincronizar dependências, executáveis, caches e bancos locais pelo Dropbox.

## Configuração inicial

Ao iniciar, a aplicação executa o runtime layout:

1. Detecta Dropbox por `info.json` oficial ou pastas padrão do sistema.
2. Cria `Dropbox/SannySystemData`.
3. Cria as pastas obrigatórias.
4. Grava `config/runtime.json`.
5. Cria `database/README-NO-SQLITE.txt`.
6. Testa escrita nas pastas principais.
7. Verifica conteúdo proibido dentro de `SannySystemData`.
8. Expõe o resultado em `/api/setup` e `/api/health`.

Em desenvolvimento, o mesmo diagnóstico roda com:

```bash
npm run check:setup
```

## Componentes

- `desktop/`: nova aplicação Electron.
- `desktop/prisma/schema.prisma`: contrato PostgreSQL.
- `desktop/src/backend/`: API local, autenticação, permissões, auditoria e sincronização.
- `desktop/src/renderer/`: interface desktop inicial.
- `desktop/src/scripts/migrate-json.ts`: migração dos dados antigos em JSON para PostgreSQL.
- `desktop/installer/windows/installer.nsh`: configuração NSIS para instalar em `Program Files/SannySystem`.
- `desktop/src/backend/paths.ts`: detecção de Dropbox, criação de diretórios e validação de conteúdo proibido.
- `desktop/src/backend/database.ts`: URL PostgreSQL com fallback, SSL, pool, timeout e reconnect.
- `desktop/src/backend/database-backup.ts`: backup PostgreSQL automático via `pg_dump`.
- `docs/deploy-postgresql-prisma-sannysystem.md`: deploy em PostgreSQL, Supabase, Neon e Railway.

## Perfis

- `administrador`: acesso total, usuários, auditoria, sincronização, cadastros e financeiro.
- `operação`: clientes, eventos, equipamentos, veículos, ordens de serviço e sincronização.
- `motorista`: leitura de rotas/eventos, ordens de serviço próprias e atualização operacional.
- `financeiro`: clientes/eventos em consulta, lançamentos financeiros, auditoria e exportação de dados.

## Auditoria

A tabela `AuditLog` registra:

- login e logout;
- criação, edição e exclusão;
- bloqueio por permissão;
- exportação/importação de snapshots;
- conflitos de sincronização;
- resolução de conflitos;
- verificação de atualização.

Logs operacionais ficam em `SannySystemData/logs`. Cache técnico fica fora do Dropbox, em `stateDir/cache`.

Além dos arquivos de log, a tabela `OperationalLog` guarda eventos técnicos de banco, migrations, backup e falhas relevantes.

## PostgreSQL profissional

A conexão PostgreSQL usa:

- fallback entre `DATABASE_URL`, `SANNYSYSTEM_DATABASE_URL`, `POSTGRES_PRISMA_URL`, `POSTGRES_URL`, `POSTGRES_URL_NON_POOLING`, `SUPABASE_DATABASE_URL`, `NEON_DATABASE_URL` e `RAILWAY_DATABASE_URL`;
- `sslmode=require` automático para Supabase, Neon e Railway;
- `connection_limit`, `pool_timeout` e `connect_timeout` aplicados na URL;
- retry inicial de conexão;
- health check sem expor senha;
- migrations automáticas com `prisma migrate deploy` quando `SANNYSYSTEM_AUTO_MIGRATE=true`.

## Backup PostgreSQL

O backup automático usa `pg_dump` no formato custom e grava em:

```text
SannySystemData/backups/
```

Cada backup registra status, provedor, tamanho, checksum, host, banco, início, fim e erro, se houver, na tabela `DatabaseBackup`.

## Sincronização segura

Cada estação tem um `workstationId` local. A exportação cria snapshots JSON atômicos em:

```text
SannySystemData/sync/snapshots
```

O arquivo é escrito primeiro em `SannySystemData/temp` e depois renomeado para `sync/snapshots`. Isso evita que outra máquina leia arquivo incompleto.

Na importação, a aplicação compara:

- origem da estação;
- entidade e ID;
- checksum remoto;
- cursor da última aplicação;
- data local de atualização.

Se o registro local mudou depois da última aplicação e o remoto é diferente, a aplicação não sobrescreve o dado. Ela cria um registro em `SyncConflict`.

## Tratamento de conflitos

Conflitos podem ser resolvidos por:

- manter local;
- usar remoto;
- ignorar.

A decisão fica registrada em auditoria com usuário, data e entidade.

## Atualização automática

O Electron usa `electron-updater` com provedor `generic`. O endereço é configurado por `SANNYSYSTEM_UPDATE_URL`.

Fluxo recomendado:

1. Gerar `.exe` e `.dmg`.
2. Publicar os artefatos e metadados no provedor de atualização configurado.
3. Configurar `SANNYSYSTEM_UPDATE_URL` em cada instalação.
4. A aplicação verifica atualização na abertura e também pelo botão `Atualizações`.

Instaladores `.exe`, `.dmg`, `.msi`, `.pkg` e `.app` não devem ser armazenados em `Dropbox/SannySystemData`.

## Compatibilidade

- Windows 10 x64.
- Windows 11 x64.
- macOS Intel x64.
- macOS Apple Silicon arm64.

O build Windows usa NSIS via Electron Builder. O build Mac gera DMG para arm64 e pode gerar x64 a partir do mesmo projeto quando executado com `electron-builder --mac dmg --x64`.

## Migração

O script `npm run data:migrate -- --data-dir ../data` importa:

- usuários;
- clientes;
- eventos;
- equipamentos;
- veículos;
- lançamentos financeiros;
- ordens de serviço;
- demais JSON como `GenericRecord`.

Senhas antigas do Flask/Werkzeug não são reutilizadas como senha válida. O hash legado é preservado apenas para rastreabilidade e os usuários devem criar nova senha.

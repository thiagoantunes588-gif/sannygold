# Deploy PostgreSQL e Prisma do SannySystem

## Objetivo

Esta arquitetura remove SQLite como banco ativo e usa PostgreSQL com Prisma ORM para suportar operação multiusuário real, pool de conexões, migrations controladas, auditoria, logs operacionais e backup automático.

## Variáveis obrigatórias

Configure ao menos uma URL PostgreSQL:

```env
DATABASE_URL="postgresql://usuario:senha@host:5432/banco?schema=public"
```

O runtime carrega `.env` destes locais, sem sobrescrever variáveis já existentes no sistema:

```text
SANNYSYSTEM_ENV_FILE
./.env.local
./.env
Application Support/SannySystem/config/.env
Application Support/SannySystem/.env
```

A aplicação tenta as variáveis nesta ordem:

```text
DATABASE_URL
SANNYSYSTEM_DATABASE_URL
POSTGRES_PRISMA_URL
POSTGRES_URL
POSTGRES_URL_NON_POOLING
SUPABASE_DATABASE_URL
NEON_DATABASE_URL
RAILWAY_DATABASE_URL
```

Para migrations, use uma conexão direta quando o provedor oferecer:

```env
SANNYSYSTEM_DIRECT_DATABASE_URL="postgresql://usuario:senha@host:5432/banco?schema=public"
DIRECT_URL="postgresql://usuario:senha@host:5432/banco?schema=public"
POSTGRES_URL_NON_POOLING="postgresql://usuario:senha@host:5432/banco?schema=public"
```

## Pool, SSL e reconnect

Configuração recomendada:

```env
SANNYSYSTEM_DB_SSLMODE="require"
SANNYSYSTEM_DB_POOL_MAX="10"
SANNYSYSTEM_DB_POOL_TIMEOUT_SECONDS="30"
SANNYSYSTEM_DB_CONNECT_TIMEOUT_SECONDS="10"
SANNYSYSTEM_DB_CONNECT_ATTEMPTS="5"
SANNYSYSTEM_AUTO_MIGRATE="true"
```

O runtime adiciona automaticamente à URL:

- `connection_limit`
- `pool_timeout`
- `connect_timeout`
- `sslmode=require` para Supabase, Neon e Railway, salvo quando `SANNYSYSTEM_DB_SSLMODE` estiver definido.

Se a primeira tentativa de conexão falhar, o backend tenta reconectar com espera progressiva antes de desistir.

## Supabase

Use a connection string PostgreSQL do projeto. Para uso diário da aplicação, prefira a URL com pool quando disponível. Para migrations, configure também a URL direta em `SANNYSYSTEM_DIRECT_DATABASE_URL`.

Exemplo:

```env
DATABASE_URL="postgresql://postgres.xxxxxx:senha@aws-0-region.pooler.supabase.com:6543/postgres?schema=public"
SANNYSYSTEM_DIRECT_DATABASE_URL="postgresql://postgres:senha@db.xxxxxx.supabase.co:5432/postgres?schema=public"
SANNYSYSTEM_DB_SSLMODE="require"
```

## Neon

Use a URL pooled para a aplicação e a URL direct/non-pooling para migrations.

Exemplo:

```env
DATABASE_URL="postgresql://usuario:senha@ep-nome-pooler.region.aws.neon.tech/sannysystem?schema=public"
SANNYSYSTEM_DIRECT_DATABASE_URL="postgresql://usuario:senha@ep-nome.region.aws.neon.tech/sannysystem?schema=public"
SANNYSYSTEM_DB_SSLMODE="require"
```

## Railway

Use as variáveis PostgreSQL geradas pelo serviço Railway. A aplicação reconhece `RAILWAY_DATABASE_URL`, `POSTGRES_URL` e `DATABASE_URL`.

Exemplo:

```env
RAILWAY_DATABASE_URL="postgresql://postgres:senha@host.railway.internal:5432/railway?schema=public"
DATABASE_URL="${RAILWAY_DATABASE_URL}"
SANNYSYSTEM_DB_SSLMODE="require"
```

## Migrations

Em deploy:

```bash
npm install
npm run prisma:generate
npm run db:deploy
npm run db:seed
```

No app desktop, `SANNYSYSTEM_AUTO_MIGRATE=true` tenta executar `prisma migrate deploy` na inicialização. Para ambientes controlados, rode `npm run db:deploy` antes de distribuir a versão e defina:

```env
SANNYSYSTEM_AUTO_MIGRATE="false"
```

## Migração dos dados antigos

Depois de aplicar migrations:

```bash
npm run data:migrate -- --data-dir ../data
```

O script importa dados antigos JSON para PostgreSQL. Senhas legadas são preservadas apenas como hash legado e os usuários devem criar nova senha.

## Backup automático

O backup usa `pg_dump` no formato custom:

```env
SANNYSYSTEM_BACKUP_ENABLED="true"
SANNYSYSTEM_BACKUP_TIME="20:00"
SANNYSYSTEM_BACKUP_RETENTION_DAYS="30"
SANNYSYSTEM_BACKUP_TIMEOUT_SECONDS="300"
SANNYSYSTEM_PG_DUMP_PATH=""
```

Se `pg_dump` não estiver no `PATH`, defina `SANNYSYSTEM_PG_DUMP_PATH`.

Backup manual:

```bash
npm run db:backup
```

Os arquivos são gravados em:

```text
Dropbox/SannySystemData/backups/
```

Cada execução registra:

- provedor;
- status;
- host;
- banco;
- caminho do arquivo;
- tamanho;
- checksum SHA-256;
- mensagem de erro, se houver.

## Diagnóstico

Verificar conexão:

```bash
npm run db:doctor
```

Verificar estrutura de dados:

```bash
npm run check:setup
```

No app:

- `/api/health`
- `/api/setup`
- `/api/database/status`

As rotas não retornam senha nem URL completa, apenas host, banco, provedor, SSL, pool e fingerprint.

## Segurança operacional

- Nunca use SQLite como banco ativo.
- Nunca sincronize diretório físico do PostgreSQL pelo Dropbox.
- Nunca salve `.db`, `.sqlite` ou `.sqlite3` em `Dropbox/SannySystemData`.
- Use conexão SSL em Supabase, Neon e Railway.
- Use uma conta PostgreSQL dedicada ao SannySystem.
- Rode migrations antes de liberar uma versão para a equipe.
- Confirme backups diariamente nos primeiros dias após migração.

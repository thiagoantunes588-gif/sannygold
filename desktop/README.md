# SannySystem Desktop

Arquitetura desktop multiusuário para o sistema interno SannyGold.

## Stack

- Electron
- Electron Builder
- Node.js
- PostgreSQL
- Prisma ORM
- Dropbox como pasta de dados sincronizados, sem banco ativo dentro do Dropbox

## Primeira execução local

1. Copie `.env.example` para `.env`.
2. Configure `DATABASE_URL` apontando para PostgreSQL.
3. Valide a estrutura local/Dropbox:

```bash
npm run check:setup
```

4. Rode:

```bash
npm install
npm run prisma:generate
npm run db:deploy
npm run db:seed
npm run data:migrate -- --data-dir ../data
npm run dev
```

## Separação aplicação/dados

A aplicação é instalada localmente:

- Windows: `C:\Program Files\SannySystem`
- Mac: `/Applications/SannySystem.app`

Os dados sincronizáveis ficam em `Dropbox/SannySystemData`. Essa pasta recebe apenas dados operacionais, snapshots, uploads, exports, backups, logs e configuração sem segredos.

Nunca coloque em `Dropbox/SannySystemData`:

- `node_modules`
- `release`, `dist` ou `build`
- `.exe`, `.dmg`, `.msi`, `.pkg`, `.app` ou scripts executáveis
- `.db`, `.sqlite` ou `.sqlite3`
- cache técnico

O diretório `database/` dentro de `SannySystemData` existe apenas para metadados e relatórios. O banco ativo é PostgreSQL via `DATABASE_URL`.

## PostgreSQL

Comandos principais:

```bash
npm run db:doctor
npm run db:deploy
npm run db:seed
npm run db:backup
```

Deploy completo: veja `../docs/deploy-postgresql-prisma-sannysystem.md`.

## Autenticação

O sistema usa JWT com refresh token rotativo, bcrypt para senha, sessão persistente, logs de acesso e auditoria completa de ações.

Documentação: `../docs/autenticacao-permissoes-sannysystem.md`.

## Builds

```bash
npm run assets:generate
npm run check
npm run build:win
npm run build:mac
npm run release:checksums
```

O instalador Windows usa NSIS e define instalação por máquina. Em Windows com permissão administrativa, o destino padrão é `Program Files/SannySystem`.

Artefatos esperados:

- `release/SannySystem-Setup-2.0.0.exe`
- `release/SannySystem-2.0.0-arm64.dmg`
- `release/SannySystem-2.0.0-x64.dmg`
- `release/CHECKSUMS-SHA256.txt`

## Atualizações, safe mode e recovery

Configure `SANNYSYSTEM_UPDATE_URL` para ativar update automático com `electron-updater`.

Modos de suporte:

```bash
SannySystem --safe-mode
SannySystem --recovery
```

No safe mode, migrations, backup automático e updates automáticos ficam desligados. No recovery mode, o app abre uma tela de diagnóstico com acesso aos logs, pasta de dados e reinicialização segura.

Documentação completa: `../docs/instaladores-profissionais-sannysystem.md`.

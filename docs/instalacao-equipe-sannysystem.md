# Instalação da equipe SannySystem

## Pré-requisitos

Em cada computador:

- Windows 10, Windows 11, Mac Intel ou Mac Apple Silicon;
- Node.js apenas para desenvolvimento ou build;
- Dropbox instalado e logado;
- acesso de rede ao PostgreSQL da operação.

No computador ou servidor de banco:

- PostgreSQL 15 ou superior;
- banco `sannysystem`;
- usuário dedicado para a aplicação;
- backup diário do PostgreSQL.

## Preparar PostgreSQL

Crie banco e usuário:

```sql
CREATE DATABASE sannysystem;
CREATE USER sannysystem WITH PASSWORD 'troque_esta_senha';
GRANT ALL PRIVILEGES ON DATABASE sannysystem TO sannysystem;
```

Defina a conexão:

```text
DATABASE_URL=postgresql://sannysystem:troque_esta_senha@SERVIDOR:5432/sannysystem?schema=public
```

Para equipe em rede local, `SERVIDOR` deve ser o IP fixo ou nome DNS da máquina que hospeda o PostgreSQL.

## Preparar Dropbox

Instale o Dropbox normalmente. A aplicação detecta automaticamente:

- `Dropbox/info.json` do cliente Dropbox;
- `%USERPROFILE%\Dropbox` no Windows;
- `~/Dropbox` no Mac;
- `~/Library/CloudStorage/Dropbox` no Mac moderno.

A pasta criada pela aplicação é:

```text
Dropbox/SannySystemData
```

Não coloque o diretório de dados do PostgreSQL dentro do Dropbox.

Estrutura criada automaticamente:

```text
Dropbox/SannySystemData/
  logs/
  backups/
  temp/
  exports/
  uploads/
  database/
  config/
  sync/snapshots/
  conflicts/
  updates/
```

Não coloque dentro dessa pasta:

- `node_modules`;
- executáveis ou instaladores;
- banco SQLite;
- cache;
- builds como `dist`, `release` ou `build`.

O diretório `database/` não recebe banco físico. Ele existe apenas para metadados e avisos de política de banco.

## Instalação Windows

1. Execute `SannySystem-Setup-2.0.0.exe` como administrador.
2. Confirme o destino `C:\Program Files\SannySystem`.
3. Abra o SannySystem pelo menu iniciar.
4. Informe ou valide a configuração `DATABASE_URL`.
5. Faça login com administrador inicial.
6. Crie usuários reais da equipe.

## Instalação Mac

1. Abra `SannySystem-2.0.0-arm64.dmg` ou `SannySystem-2.0.0-x64.dmg`.
2. Arraste o app para `Applications`.
3. Abra o app.
4. Informe ou valide a configuração `DATABASE_URL`.
5. Faça login com administrador inicial.

## Inicialização do banco

Na pasta `desktop`, em ambiente de desenvolvimento ou preparação:

```bash
npm install
npm run check:setup
npm run db:doctor
npm run prisma:generate
npm run db:deploy
npm run db:seed
npm run data:migrate -- --data-dir ../data
```

Depois da migração, valide no app:

- usuários;
- clientes;
- eventos;
- equipamentos;
- financeiro;
- auditoria.

## Permissões

Use:

- `administrador` para gestores e suporte interno;
- `operação` para equipe que cadastra clientes, eventos, equipamentos, veículos e OS;
- `motorista` para execução de rota e confirmação de serviço;
- `financeiro` para lançamentos, recebimentos, fechamento e auditoria financeira.

Não compartilhe login entre pessoas. Cada pessoa deve ter sua própria conta.

## Rotina de sincronização

1. Abra `Sincronização`.
2. Clique em `Exportar snapshot` ao final de mudanças relevantes.
3. Clique em `Importar snapshots` ao iniciar o dia ou antes de conferir dados de outra estação.
4. Resolva conflitos pendentes antes de gerar documentos críticos.

Se houver conflito:

- `Usar remoto`: aplica a versão recebida do Dropbox;
- `Manter local`: preserva a versão deste computador;
- `Ignorar`: mantém conflito registrado sem aplicar alteração.

## Atualizações

Quando houver nova versão:

1. Gere o instalador com Electron Builder.
2. Publique os artefatos no diretório de atualização.
3. Atualize o manifesto do `electron-updater`.
4. Abra o app e use o botão `Atualizações`.

Para Windows, distribua o `.exe`. Para Mac, distribua o `.dmg`.

## Verificação final após instalar

Em cada computador:

1. Abrir o app.
2. Fazer login.
3. Conferir `Painel`.
4. Conferir se Dropbox aparece como detectado.
5. Criar um cliente de teste.
6. Exportar snapshot.
7. Em outra máquina, importar snapshot.
8. Conferir auditoria.
9. Remover o cliente de teste se necessário.

## Regras de segurança

- PostgreSQL ativo fora do Dropbox.
- Dropbox somente para dados sincronizados, snapshots, conflitos, backups, exports, uploads, logs operacionais e configuração sem segredos.
- SQLite, executáveis, dependências e cache nunca entram em `Dropbox/SannySystemData`.
- Cada pessoa usa login próprio.
- Perfil financeiro não edita operação.
- Perfil motorista não acessa financeiro.
- Logs e auditoria não devem ser apagados manualmente.

## Deploy PostgreSQL

Para Supabase, Neon, Railway, pool, SSL, migrations e backup automático, use o guia:

[Deploy PostgreSQL e Prisma do SannySystem](deploy-postgresql-prisma-sannysystem.md)

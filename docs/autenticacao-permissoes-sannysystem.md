# Autenticação e permissões do SannySystem

## Perfis

O sistema possui cinco perfis operacionais:

- `administrador`: acesso total.
- `financeiro`: clientes, eventos, financeiro, auditoria e logs.
- `operação`: clientes, eventos, equipamentos, veículos, ordens de serviço e sincronização.
- `motorista`: eventos, rotas, ordens atribuídas, equipamentos e sincronização.
- `almoxarifado`: equipamentos, estoque, ordens de serviço, eventos e sincronização.

## Login e sessão

A autenticação usa:

- senha criptografada com bcrypt;
- access token JWT assinado;
- refresh token rotativo armazenado somente em hash no PostgreSQL;
- sessão persistente por dispositivo;
- logout automático após 30 minutos sem uso na aplicação desktop;
- revogação de sessões no logout, reset de senha e exclusão de usuário;
- bloqueio temporário após tentativas inválidas.

Variáveis principais:

```env
SANNYSYSTEM_JWT_SECRET="troque-por-uma-chave-jwt-com-32-caracteres-ou-mais"
SANNYSYSTEM_ACCESS_TOKEN_MINUTES="15"
SANNYSYSTEM_REFRESH_TOKEN_DAYS="7"
SANNYSYSTEM_MAX_FAILED_LOGINS="5"
SANNYSYSTEM_LOGIN_LOCK_MINUTES="15"
```

## Auditoria

Toda ação de escrita autenticada registra:

- usuário;
- data e horário;
- rota executada;
- IP;
- user-agent;
- máquina local;
- status HTTP;
- detalhes antes/depois quando a rota fornece essa informação.

Tabelas principais:

- `AuditLog`: auditoria de alterações e ações administrativas.
- `AccessLog`: login, logout, refresh token, sessão expirada e acesso negado.
- `OperationalLog`: logs técnicos e operacionais.
- `Session`: sessão persistente e revogável.

## Gestão administrativa

A tela `Usuários` permite:

- criar usuários;
- editar nome, login, e-mail, perfil e status;
- redefinir senha;
- inativar/excluir com histórico preservado;
- consultar matriz de permissões;
- consultar histórico de acessos, sessões e alterações por usuário;
- visualizar IP e máquina de acessos e alterações administrativas.

Exclusão de usuário é lógica: o registro fica inativo com `deletedAt`, preservando histórico e auditoria. O histórico administrativo consulta tanto ações feitas pelo usuário quanto ações feitas sobre ele, incluindo exclusão, alteração de perfil, troca de status e reset de senha.

## Migrations

As mudanças estão na migration:

```text
desktop/prisma/migrations/20260608010000_auth_permissions_hardening/migration.sql
```

Para aplicar em produção:

```bash
cd desktop
npm run db:deploy
npm run db:seed
```

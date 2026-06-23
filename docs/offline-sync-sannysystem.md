# SannySystem - Modo híbrido online/offline

## Objetivo

O modo híbrido permite que a equipe registre ações operacionais mesmo sem internet ou sem acesso momentâneo ao PostgreSQL. As ações ficam em cache local no aplicativo instalado e são enviadas automaticamente quando a conexão volta.

## O que funciona offline

- Checklist operacional.
- Check-in.
- Check-out.
- Fotos.
- Assinaturas.
- Ordens de serviço.
- Ocorrências operacionais.

## Onde cada dado fica

Aplicação instalada:

- Windows: `C:/Program Files/SannySystem`
- Mac: `/Applications/SannySystem`

Dados compartilhados:

- `Dropbox/SannySystemData`
- Usado para snapshots, exports, backups, uploads, logs e conflitos.

Cache offline local:

- Fica no armazenamento interno do Electron/Chromium via IndexedDB.
- Não fica dentro do Dropbox.
- Não armazena `node_modules`, executáveis, SQLite ou cache técnico em `SannySystemData`.

Banco principal:

- PostgreSQL via Prisma ORM.
- A fila recebida do cache local é gravada nas tabelas `OfflineQueueItem` e `OfflineAttachment`.

## Fluxo de operação

1. Usuário entra no sistema.
2. A tela `Operação offline` carrega ordens de serviço recentes e guarda uma cópia local.
3. Em campo, o usuário registra checklist, check-in, check-out, fotos, assinatura ou ocorrência.
4. Se não houver conexão, a ação fica como pendente na fila local.
5. Quando a conexão retorna, o aplicativo envia a fila local para o backend.
6. O backend processa a fila no PostgreSQL.
7. Depois do processamento, o sistema roda importação/exportação de snapshots para manter a sincronização por Dropbox.

## Retry automático

Cada item da fila no servidor possui:

- status: `PENDING`, `SYNCING`, `DONE`, `FAILED` ou `CONFLICT`
- número de tentativas
- próxima tentativa
- erro mais recente
- usuário que registrou
- data e hora da coleta

Falhas temporárias são reagendadas com espera crescente. Falhas definitivas permanecem registradas para análise.

## Tratamento de conflito

Um conflito é criado quando uma ordem de serviço foi alterada no PostgreSQL depois da versão que o operador tinha no cache local.

O sistema registra:

- entidade afetada
- ID do registro
- payload local
- payload enviado do offline
- usuário
- máquina
- data e hora

Os conflitos aparecem em:

- tela `Operação offline`
- tela `Sincronização`
- auditoria
- logs operacionais

## Indicadores na interface

Topo do sistema:

- `Online` ou `Offline`
- quantidade de itens na fila local

Tela `Operação offline`:

- conexão atual
- fila local
- fila no servidor
- última sincronização
- lista de pendências locais
- conflitos offline recentes

## Boas práticas para equipe

- Antes de sair para campo, abrir o sistema conectado para carregar ordens recentes no cache local.
- Durante a operação, registrar tudo normalmente pela tela `Operação offline`.
- Ao voltar para um local com internet, manter o sistema aberto até a fila local ficar zerada.
- Se aparecer conflito, não apagar a ordem. Resolver pela tela de sincronização para preservar histórico.
- Não copiar banco, executáveis, `node_modules` ou cache para o Dropbox.

## Tabelas criadas

- `OfflineQueueItem`
- `OfflineAttachment`

Enums criados:

- `OfflineActionType`
- `OfflineQueueStatus`
- `OfflineAttachmentKind`

Eventos de auditoria adicionados:

- `OFFLINE_QUEUE`
- `OFFLINE_SYNC`
- `OFFLINE_CONFLICT`

## APIs locais

- `GET /api/offline/status`
- `GET /api/offline/queue`
- `POST /api/offline/queue`
- `POST /api/offline/sync`
- `GET /api/service-orders`
- `POST /api/service-orders`
- `PUT /api/service-orders/:id`

## Permissões

- `offline.queue`: registrar ações offline.
- `offline.sync`: processar fila, retries e conflitos.

Perfis com operação offline:

- administrador
- operação
- motorista
- almoxarifado

Financeiro possui sincronização, mas não registra ações operacionais.

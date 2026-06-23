# Backup e restauração

Este guia descreve como proteger e restaurar os dados do Sistema SannyGold em operação real.

## Conceito

- O banco ativo fica em `data/sannygold.db`.
- Os arquivos de trabalho ficam em `data/`, `uploads/` e `preview/`.
- Backups locais ficam em `backups/`.
- Dropbox é usado apenas para receber cópias `.zip` prontas.
- O banco ativo, `data/`, `uploads/` e a pasta do sistema não devem ficar dentro do Dropbox.

## O que entra no backup

Cada backup `sannygold-data-backup-*.zip` inclui:

- `manifest.json`, com identificação `SannyGold` e formato do backup;
- `data/`, incluindo `sannygold.db` e arquivos JSON;
- `uploads/`, com anexos e fotos;
- `preview/`, com PDFs e arquivos gerados;
- `config/backup-config.json`;
- `config/runtime-config.json`, somente com configurações seguras.

O backup não inclui `.env.local`, `SANNYGOLD_SECRET_KEY`, senha inicial de admin, `.venv/`, `.git/`, logs, backups antigos ou temporários.

## Backup manual

Pelo painel:

1. Entre como administrador.
2. Abra o painel `Backup local dos dados`.
3. Clique em `Gerar backup agora`.
4. Confira se apareceu o arquivo em `backups/`.
5. Se Dropbox estiver configurado, confira se o `.zip` apareceu também em `DROPBOX_BACKUP_DIR`.

Pelo terminal:

```bash
python3 scripts/create_local_backup.py --trigger manual_cli
```

## Backup automático

O painel permite ativar/desativar o backup automático e escolher o horário.

O sistema registra:

- última execução;
- próximo horário;
- último arquivo gerado;
- erro ou aviso da última cópia para Dropbox.

## Retenção

Por padrão:

- últimos 30 backups locais;
- últimos 30 backups copiados para Dropbox.

Para alterar, edite `.env.local`:

```text
SANNYGOLD_BACKUP_RETENTION_LIMIT=30
SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT=30
```

Depois reinicie o sistema.

## Diagnóstico Dropbox

No painel, use `Testar pasta Dropbox`.

Estados esperados:

- `Dropbox OK`: pasta existe, permite escrita e já possui backup `.zip`;
- `Dropbox configurado, mas pasta não encontrada`: caminho configurado não existe;
- `Sem permissão para gravar no Dropbox`: o sistema não consegue escrever na pasta;
- `Dropbox configurado, mas sem backup ainda`: a pasta existe, mas ainda não recebeu `.zip`;
- `Risco: banco ativo parece estar dentro do Dropbox`: corrija antes de usar.

O painel também mostra:

- último backup local;
- última cópia no Dropbox;
- tamanho do último arquivo;
- diferença de horário entre backup local e cópia Dropbox.

## Testar restauração sem mexer nos dados

No painel:

1. Gere um backup.
2. Clique em `Testar restauração`.
3. O sistema valida o `.zip` e extrai em uma pasta temporária.
4. Nenhum dado real é sobrescrito.

Esse teste confirma se o arquivo parece restaurável antes de depender dele.

## Restaurar de verdade

Para restauração real, feche o launcher e pare o servidor antes.

No Mac:

```bash
python3 scripts/restore_backup.py backups/NOME-DO-BACKUP.zip
```

No Windows:

```powershell
.\.venv\Scripts\python.exe scripts\restore_backup.py backups\NOME-DO-BACKUP.zip
```

Se o arquivo veio do Dropbox, informe o caminho completo do `.zip`.

Antes de restaurar, o script:

1. valida `manifest.json`;
2. confirma que é backup SannyGold atual;
3. confirma que existe `data/`;
4. extrai primeiro para pasta temporária;
5. bloqueia a restauração se o sistema estiver rodando;
6. cria backup preventivo do estado atual;
7. restaura `data/`, `uploads/` e `preview/`;
8. registra em `logs/restore.log`;
9. mostra resumo final.

Backups antigos nunca são apagados durante a restauração.

## Validar depois de restaurar

1. Abra o launcher.
2. Acesse `http://127.0.0.1:5007`.
3. Confira clientes, eventos, financeiro, equipamentos e anexos.
4. Gere um novo backup manual.
5. Confira se o `.zip` novo apareceu em `backups/` e no Dropbox, se configurado.

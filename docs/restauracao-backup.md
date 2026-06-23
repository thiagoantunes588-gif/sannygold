# Restauração de backup

Use esta rotina quando precisar voltar o Sistema SannyGold para um backup `.zip` anterior.

## Antes de restaurar

1. Feche o launcher e o navegador.
2. Confirme que ninguém está usando o sistema no computador ou pelo celular.
3. Separe o arquivo `.zip` que será restaurado.
4. Prefira arquivos com nome parecido com `sannygold-data-backup-AAAAMMDD-HHMMSS-xxxxxxxx.zip`.

O script não apaga backups antigos. Antes de restaurar, ele cria um backup preventivo do estado atual.

## Restaurar no Mac

Na raiz do projeto:

```bash
python3 scripts/restore_backup.py backups/NOME-DO-BACKUP.zip
```

Se o arquivo veio do Dropbox, use o caminho completo, por exemplo:

```bash
python3 scripts/restore_backup.py "$HOME/Dropbox/Sistema SannyGold/Backups/NOME-DO-BACKUP.zip"
```

## Restaurar no Windows

Abra o PowerShell na pasta do projeto e rode:

```powershell
.\.venv\Scripts\python.exe scripts\restore_backup.py backups\NOME-DO-BACKUP.zip
```

Se o arquivo veio do Dropbox:

```powershell
.\.venv\Scripts\python.exe scripts\restore_backup.py "$env:USERPROFILE\Dropbox\Sistema SannyGold\Backups\NOME-DO-BACKUP.zip"
```

## O que o script valida

- O arquivo precisa ser `.zip`.
- O ZIP precisa conter `manifest.json`.
- O ZIP precisa conter a pasta `data/`.
- A extração acontece primeiro em uma pasta temporária.
- Se o launcher ou servidor estiver rodando, a restauração é bloqueada.
- O estado atual é salvo em um backup preventivo antes da troca dos arquivos.

## O que é restaurado

Quando existirem no ZIP, estas pastas são restauradas:

- `data/`
- `uploads/`
- `preview/`

As versões anteriores dessas pastas são movidas para `tmp/restore-replaced-*`.

## Como validar depois

1. Abra o launcher.
2. Acesse `http://127.0.0.1:5007`.
3. Confira clientes, eventos, financeiro e almoxarifado.
4. Gere um novo backup manual.
5. Confira se o novo `.zip` apareceu em `backups/` e, se configurado, no Dropbox.

O log da restauração fica em `logs/restore.log`.

# Iniciar a SannyGold automaticamente no macOS

Este guia configura o computador servidor para subir o sistema SannyGold automaticamente quando o usuario entrar no macOS.

Use isto no computador que guarda os dados locais. O celular acessa pelo mesmo Wi-Fi.

## O que sera criado

O script cria um LaunchAgent do macOS:

```text
~/Library/LaunchAgents/com.sannygold.sistema.launchagent.plist
```

Esse LaunchAgent chama:

```text
scripts/start_local.sh
```

O sistema continua podendo ser aberto manualmente pelo launcher `SannyGold Sistema.app`.

## Configuracao usada

No arquivo `.env.local`, confira:

```text
PORT=5007
FLASK_HOST=0.0.0.0
DROPBOX_BACKUP_DIR=/Users/thiago/Dropbox/Sistema SannyGold/Backups
```

Use `FLASK_HOST=0.0.0.0` para permitir acesso pelo celular no mesmo Wi-Fi.

Use `FLASK_HOST=127.0.0.1` somente se quiser bloquear acesso pelo celular e deixar o sistema apenas no Mac.

## Ativar inicio automatico

No Terminal, rode:

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
bash scripts/install_macos_launch_agent.sh
```

O comando instala e carrega o servico imediatamente. Na proxima entrada do usuario no macOS, o sistema tentara iniciar sozinho.

## Verificar se esta rodando

Use:

```bash
launchctl print gui/$(id -u)/com.sannygold.sistema.launchagent
```

Tambem teste no navegador:

```text
http://127.0.0.1:5007/health
```

No celular, conectado ao mesmo Wi-Fi, teste:

```text
http://IP_DO_MAC:5007/
```

O IP tambem aparece na tela admin `Acesso pelo Celular`.

## Parar temporariamente

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.sannygold.sistema.launchagent.plist
```

Isso para o servico carregado. O arquivo `.plist` continua instalado.

## Reiniciar

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.sannygold.sistema.launchagent.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sannygold.sistema.launchagent.plist
```

## Desativar e remover

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
bash scripts/uninstall_macos_launch_agent.sh
```

Isso remove somente o auto-inicio. Dados, backups, uploads e logs permanecem no projeto.

## Logs

Confira estes arquivos:

```text
logs/launchagent.out.log
logs/launchagent.err.log
logs/backup.log
logs/launcher.log
```

Se algo falhar, comece por `logs/launchagent.err.log`.

## Cuidados

- O Mac precisa estar ligado e com o usuario logado.
- O firewall do macOS pode bloquear acesso pelo celular.
- Nao mova `data/` nem `data/sannygold.db` para o Dropbox.
- O Dropbox deve receber apenas arquivos `.zip` de backup.
- Se a porta `5007` estiver ocupada, altere `PORT` em `.env.local` e reinstale o LaunchAgent.

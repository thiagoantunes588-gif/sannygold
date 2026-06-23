# Operação no Mac, Windows e Dropbox

Este guia explica a forma recomendada de operar o Sistema SannyGold em um computador servidor, com acesso pelo navegador e backups em `.zip`.

## 1. Conceito correto

- O sistema roda em um único computador servidor: Mac ou Windows.
- O navegador do próprio servidor acessa `http://127.0.0.1:5007`.
- Celulares e outros computadores acessam pelo Wi-Fi usando o endereço mostrado no launcher.
- Para acesso privado fora do Wi-Fi, use Tailscale. Não abra portas do roteador para a internet.
- Dropbox é usado somente como destino de cópias `.zip` de backup.
- O banco ativo não deve ficar no Dropbox. Mantenha `data/sannygold.db`, `data/` e `uploads/` na pasta local do projeto.

## 2. Instalação no Mac

Na raiz do projeto, rode:

```bash
bash scripts/start_local.sh
```

Esse comando prepara `.venv`, `.env.local`, pastas locais, SQLite e inicia o sistema na porta `5007`.

Para instalar o launcher do macOS:

```bash
bash scripts/install_macos_launcher.sh
```

Depois abra o app `SannyGold Sistema.app`.

Opcionalmente, para iniciar junto com o login do usuário:

```bash
bash scripts/install_macos_launch_agent.sh
```

Locais importantes no Mac:

- Dados ativos: `data/`
- Banco SQLite ativo: `data/sannygold.db`
- Uploads e anexos: `uploads/`
- Pré-visualizações: `preview/`
- Backups locais: `backups/`
- Logs: `logs/`
- Log do launcher: `logs/launcher.log`
- Log do app macOS: `logs/macos-launcher.log`
- Dropbox padrão: `~/Dropbox/Sistema SannyGold/Backups`

## 3. Instalação no Windows

1. Instale Python 3 no Windows 10 ou 11.
2. Se o instalador mostrar a opção `Add Python to PATH`, marque essa opção.
3. Instale e entre no Dropbox, se for usar cópia automática para Dropbox.
4. Abra o PowerShell na pasta do projeto.
5. Rode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_launcher.ps1
```

O instalador cria `.venv`, instala dependências, cria `.env.local`, prepara a pasta de backup do Dropbox e cria o atalho `SannyGold Sistema` na Área de Trabalho.

Depois, abra o sistema pelo atalho `SannyGold Sistema`.

Locais importantes no Windows:

- Dados ativos: `data\`
- Banco SQLite ativo: `data\sannygold.db`
- Uploads e anexos: `uploads\`
- Pré-visualizações: `preview\`
- Backups locais: `backups\`
- Logs: `logs\`
- Log do launcher: `logs\launcher.log`
- Log do instalador Windows: `logs\windows-launcher.log`
- Dropbox padrão: `%USERPROFILE%\Dropbox\Sistema SannyGold\Backups`

## 4. Configuração Dropbox

Caminho padrão no Mac:

```text
~/Dropbox/Sistema SannyGold/Backups
```

Caminho padrão no Windows:

```text
%USERPROFILE%\Dropbox\Sistema SannyGold\Backups
```

Como testar no painel:

1. Abra o sistema.
2. Entre com um usuário administrador.
3. Vá até o painel `Backup local dos dados`.
4. Clique em `Testar pasta Dropbox`.
5. Confira a mensagem de status.
6. Clique em `Gerar backup agora`.
7. Abra a pasta Dropbox configurada e confirme se apareceu um arquivo `sannygold-data-backup-*.zip`.

Status esperados:

- `Dropbox OK`: a pasta existe, permite escrita e já tem backup `.zip`.
- `Dropbox encontrado, sem backup ainda`: a pasta existe, mas ainda não recebeu um `.zip`.
- `Dropbox não encontrado`: instale, entre no Dropbox ou ajuste `DROPBOX_BACKUP_DIR`.
- `Sem permissão para gravar no Dropbox`: revise permissões da pasta.
- `Risco: banco ativo parece estar dentro do Dropbox`: corrija a configuração antes de continuar.

## 5. Uso diário

1. Abra o launcher.
2. Aguarde o servidor iniciar.
3. Clique em `Abrir sistema` ou acesse `http://127.0.0.1:5007`.
4. Para celular no mesmo Wi-Fi, use a URL mostrada no launcher.
5. Para acesso privado fora do Wi-Fi, use Tailscale.
6. Gere backup manual antes de mudanças importantes.
7. Verifique o status do Dropbox no painel ou no launcher.
8. Ao terminar, pare o servidor pelo botão do launcher.

## 6. Segurança

- Não coloque `data/sannygold.db` no Dropbox.
- Não coloque `data/` no Dropbox.
- Não coloque `uploads/` no Dropbox.
- Não mova a pasta inteira do projeto para dentro do Dropbox.
- Não abra dois servidores editando dados diferentes achando que estão sincronizados.
- Dropbox não sincroniza o banco ativo; ele guarda apenas cópias `.zip` para recuperação.
- Faça um teste de restauração seguindo `docs/restauracao-backup.md`.
- Guarde os `.zip` com cuidado, pois eles podem conter dados reais de clientes, eventos, financeiro e operação.

## 7. Solução de problemas

### Porta 5007 em uso

Feche outro launcher ou processo do SannyGold. Se continuar, reinicie o computador servidor. Só altere `PORT` no `.env.local` se souber que todos usarão a nova porta.

### Python não encontrado

No Windows, reinstale Python 3 e marque `Add Python to PATH`. Depois rode novamente:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_launcher.ps1
```

No Mac, confirme:

```bash
python3 --version
```

Se o comando não existir, instale Python 3 e rode novamente `bash scripts/start_local.sh`.

### Dropbox não encontrado

Instale o Dropbox no computador servidor, entre na conta correta e confirme a pasta:

- Mac: `~/Dropbox/Sistema SannyGold/Backups`
- Windows: `%USERPROFILE%\Dropbox\Sistema SannyGold\Backups`

Depois clique em `Testar pasta Dropbox` no painel.

### Backup não aparece no Dropbox

1. Confira `DROPBOX_BACKUP_DIR` no `.env.local`.
2. Clique em `Testar pasta Dropbox`.
3. Clique em `Gerar backup agora`.
4. Aguarde o Dropbox sincronizar.
5. Veja os logs `logs/backup.log` e `logs/launcher.log`.

### Celular não acessa no Wi-Fi

1. Confirme que computador servidor e celular estão no mesmo Wi-Fi.
2. Use a URL para celular mostrada no launcher, não `127.0.0.1`.
3. Verifique se o firewall do Windows ou macOS permite conexão local na porta `5007`.
4. Se a rede bloquear acesso local, use Tailscale.
5. Se estiver fora da loja/escritório, use Tailscale em vez do Wi-Fi local.

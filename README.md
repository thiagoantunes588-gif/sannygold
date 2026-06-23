# Sistema Geral SannyGold

README tecnico do sistema interno da SannyGold. O objetivo e permitir manutencao, testes, backup e evolucao sem depender de uma unica pessoa.

Caminho oficial do projeto:

```text
/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna
```

## O que o sistema faz

- Cadastro de clientes, eventos/locacoes, banheiros, trailers, climatizadores e pontos de hidratacao.
- Controle de equipamentos, veiculos, rotas, ordens de servico e PDFs operacionais.
- Financeiro basico: contas a receber, recebimentos, lancamentos, recibos e painel gerencial.
- Usuarios por perfil, auditoria, backup local e validacoes antes de gerar documentos.

## Documentacao por publico

- Equipe operacional/financeira: [docs/manual-equipe.md](docs/manual-equipe.md)
- Administradores: [docs/manual-admin.md](docs/manual-admin.md)
- Aplicativo no macOS: [docs/macos-launcher.md](docs/macos-launcher.md)
- Inicio automatico no macOS: [docs/macos-autostart.md](docs/macos-autostart.md)
- Estrutura do projeto e instaladores: [ESTRUTURA_DO_PROJETO.md](ESTRUTURA_DO_PROJETO.md)
- Operacao Mac, Windows e Dropbox: [docs/instalacao-mac-windows-dropbox.md](docs/instalacao-mac-windows-dropbox.md)
- Backup e restauracao: [docs/backup-e-restauracao.md](docs/backup-e-restauracao.md)
- Acesso externo seguro: [docs/tailscale-acesso-seguro.md](docs/tailscale-acesso-seguro.md)
- Refatoracao de backend: [docs/backend-route-map.md](docs/backend-route-map.md)
- Migracao JSON para SQLite: [docs/sqlite-migration-plan.md](docs/sqlite-migration-plan.md)
- Frota profissional - Fase 1: [docs/frota-fase1.md](docs/frota-fase1.md)
- Analise tecnica do modulo de Frota: [docs/ANALISE_MODULO_FROTA.md](docs/ANALISE_MODULO_FROTA.md)

## Instalar localmente

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Rodar localmente

Padroes locais oficiais:

- `SANNYGOLD_ENV=local`
- `SANNYGOLD_STORAGE_BACKEND=sqlite`
- `SANNYGOLD_SQLITE_MIRROR_JSON=1`
- `SANNYGOLD_SQLITE_PATH=data/sannygold.db`
- `PORT=5007`
- `FLASK_HOST=0.0.0.0`
- `FLASK_DEBUG=0`
- `DROPBOX_BACKUP_DIR=~/Dropbox/Sistema SannyGold/Backups` no Mac ou `%USERPROFILE%\Dropbox\Sistema SannyGold\Backups` no Windows
- `SANNYGOLD_BACKUP_RETENTION_LIMIT=30`
- `SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT=30`

O SQLite local e o banco ativo. Dropbox deve receber apenas backups `.zip`; o sistema bloqueia inicializacao se a pasta do projeto, `data/`, `uploads/` ou `sannygold.db` estiverem dentro do Dropbox.

Modo recomendado sem terminal para uso diario:

```bash
python3 scripts/sannygold_launcher.py
```

O launcher abre uma janela simples com:

- sistema rodando ou parado;
- endereco local no computador;
- endereco para celular no Wi-Fi;
- ultimo backup local;
- status da copia Dropbox;
- botoes `Abrir sistema`, `Gerar backup` e `Parar servidor`.
- tela `Configuração inicial` com pasta do sistema, banco, backups locais, Dropbox, teste de Dropbox e backup manual.

O launcher usa `waitress` como servidor WSGI local, registra erros em `logs/launcher.log` e cria uma trava em `logs/launcher.lock` para evitar duas janelas tentando iniciar o mesmo servidor. A porta padrao e `5007`, configuravel em `.env.local` com `PORT=5007`.

Modo terminal:

```bash
bash scripts/start_local.sh
```

Esse script cria `.env.local` se nao existir, prepara `.venv`, instala dependencias quando necessario, gera backup inicial se o ultimo tiver mais de 24 horas, roda migracao JSON para SQLite e inicia com `waitress`.

Abra:

```text
http://127.0.0.1:5007
```

Modo celular no mesmo Wi-Fi:

```bash
bash scripts/start_wifi.sh
```

Abra o sistema no computador e, no painel admin, use o bloco `Acesso pelo celular no Wi-Fi` para escanear o QR Code.

Criar o app/launcher no macOS:

```bash
bash scripts/install_macos_launcher.sh
```

O launcher criado chama `SannyGold Sistema.app`, abre a janela de status do launcher Python, inicia o sistema em modo Wi-Fi e abre `http://127.0.0.1:5007`.

Depois de criar o app:

1. Abra `~/Applications`.
2. Arraste `SannyGold Sistema.app` para o Dock, se quiser acesso rapido.
3. Para iniciar junto com o macOS, abra `Ajustes do Sistema > Geral > Itens de Início` e adicione `SannyGold Sistema.app`.

Logs do app ficam em `logs/launcher.log`. Dados ficam em `data/`, backups em `backups/`, configuracao local em `.env.local` e uploads em `uploads/`.

Guia completo: [docs/macos-launcher.md](docs/macos-launcher.md).

Iniciar automaticamente ao ligar/entrar no Mac:

```bash
bash scripts/install_macos_launch_agent.sh
```

Isso cria `~/Library/LaunchAgents/com.sannygold.sistema.launchagent.plist`, grava logs em `logs/launchagent.out.log` e `logs/launchagent.err.log`, e inicia o sistema pela porta configurada em `.env.local`.

Para desativar:

```bash
bash scripts/uninstall_macos_launch_agent.sh
```

Guia completo: [docs/macos-autostart.md](docs/macos-autostart.md).

Instalar e abrir no Windows:

1. Instale Python 3.
2. Abra o PowerShell na pasta do projeto.
3. Rode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_launcher.ps1
```

O instalador simples cria `.venv`, instala `requirements.txt`, cria `.env.local`, prepara `%USERPROFILE%\Dropbox\Sistema SannyGold\Backups` para receber `.zip` e cria o atalho `SannyGold Sistema` na Area de Trabalho.

Para gerar o instalador profissional Windows com `.exe`, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_installer.ps1
```

O instalador final esperado e `SannyGold-Sistema-Windows-Setup.exe`, salvo em `Dropbox\Sistema SannyGold\Instaladores\Windows\Instalador` quando o Dropbox estiver disponivel.

Para iniciar pelo terminal no Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1
```

Para abrir pelo atalho, use `SannyGold Sistema`. O atalho chama `scripts\start_windows_launcher.ps1`, que abre `scripts\sannygold_launcher.py` com o Python da `.venv`.

Modo acesso externo seguro com Tailscale:

```bash
bash scripts/start_tailscale_secure.sh
```

Esse modo valida se o Tailscale está conectado, mostra o endereço `http://IP_TAILSCALE:5007/` e mantém o acesso restrito a dispositivos autorizados na rede Tailscale. Ele não abre porta pública no roteador e não usa `tailscale funnel`.

Guia completo: [docs/tailscale-acesso-seguro.md](docs/tailscale-acesso-seguro.md).

Modo manual:

```bash
source .venv/bin/activate
export SANNYGOLD_ENV=local
export SANNYGOLD_SECRET_KEY="$(openssl rand -hex 32)"
export FLASK_DEBUG=0
python3 -m waitress --host=127.0.0.1 --port=5007 app.main:app
```

Abra:

```text
http://127.0.0.1:5007
```

## Variaveis de ambiente

Use `.env.example` como referencia, sem colocar senhas reais no repositorio.

Obrigatorias em producao:

- `SANNYGOLD_ENV=production`
- `SANNYGOLD_SECRET_KEY`: chave aleatoria com 32+ caracteres. Gere com `openssl rand -hex 32`.
- `SANNYGOLD_ADMIN_EMAIL`
- `SANNYGOLD_ADMIN_PASSWORD`
- `SANNYGOLD_ADMIN_NAME`
- `ROTAFLOW_STORAGE_DIR`: pasta persistente dos dados, por exemplo `/var/data`.
- `SANNYGOLD_SQLITE_PATH`: banco local ativo, por padrao `data/sannygold.db`.
- `SANNYGOLD_STORAGE_BACKEND`: use `sqlite` para operar pelo banco local; use `json` apenas para fallback.
- `SANNYGOLD_SQLITE_MIRROR_JSON=1`: mantém os JSON atualizados como espelho de segurança enquanto a migração estabiliza.
- `DROPBOX_BACKUP_DIR`: pasta Dropbox local que recebera somente arquivos `.zip` de backup, por exemplo `/Users/thiago/Dropbox/Sistema SannyGold/Backups`.
- `SANNYGOLD_TAILSCALE_URL`: opcional, endereço privado para exibir no painel admin, por exemplo `http://100.x.y.z:5007/`.
- `SANNYGOLD_TAILSCALE_IP`: opcional, IP privado Tailscale; se preenchido sem URL, o sistema monta `http://IP:PORTA/`.
- `FLASK_DEBUG=0`

Opcionais:

- `SANNYGOLD_SESSION_COOKIE_SECURE=1`: usar quando o acesso for HTTPS e o provedor nao for detectado automaticamente.
- `SANNYGOLD_CSRF_DISABLED=0`: manter `0`; usar outro valor apenas em teste controlado.
- `GOOGLE_MAPS_API_KEY`: melhora geocodificacao quando configurada.
- `SANNYGOLD_APP_VERSION`: identifica a versao no painel/status.

Em producao, a aplicacao nao inicia se a chave secreta estiver ausente, fraca ou se `FLASK_DEBUG` estiver ativo.

## Estrutura de pastas

- `app/main.py`: aplicacao Flask e rotas ainda nao separadas.
- `app/routes/`: rotas extraidas por modulo, como backup e financeiro.
- `app/services/`: servicos reutilizaveis, como backup e migracao.
- `app/repositories/`: camada preparada para SQLite.
- `app/templates/`: telas HTML.
- `app/static/`: imagens e assets fixos.
- `data/`: arquivos JSON locais usados pela versao atual.
- `backups/`: backups `.zip` gerados pelo sistema.
- `logs/`: logs locais de backup e diagnóstico.
- `preview/`: PDF/JSON da rota mais recente.
- `uploads/`: arquivos enviados pela equipe.
- `docs/`: documentacao de uso, administracao e evolucao.
- `scripts/`: inicializacao, rota, exportacao e migracao.
- `tests/`: testes automatizados.

## Rodar testes

Rodar tudo:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/rotaflow-pycache python3 -m compileall app tests
python3 -m unittest discover tests
```

Rodar apenas os fluxos principais:

```bash
python3 -m unittest tests.test_core_business_flows
```

Os testes usam dados falsos e armazenamento temporario. Nao dependem dos dados reais da empresa.

## Backup

Pelo sistema:

1. Entrar com usuario `admin`.
2. Abrir o painel administrativo/backup.
3. Clicar em `Gerar backup agora`.
4. Baixar o ultimo backup se precisar guardar uma copia fora da maquina.

Pelo endpoint interno autenticado:

- `POST /backup/generate`: gera backup manual.
- `GET /backup/latest.zip`: baixa o ultimo backup.
- `GET /backup/system.zip`: gera e baixa um backup novo.

O backup inclui:

- `data/`: banco `sannygold.db`, JSON, auditoria, configurações e relatórios de migração.
- `preview/`: PDFs e arquivos de rota gerados.
- `uploads/`: anexos, fotos e arquivos enviados pela equipe.

O backup não inclui `.venv/`, caches, `__pycache__/`, `node_modules/`, temporários nem backups antigos dentro do novo backup.

O backup fica em `backups/` e usa o padrao:

```text
sannygold-data-backup-AAAAMMDD-HHMMSS-xxxxxxxx.zip
```

O sistema mantem os ultimos 30 backups locais. Quando `DROPBOX_BACKUP_DIR` estiver configurado e a pasta existir, o `.zip` finalizado tambem e copiado para essa pasta Dropbox. O banco ativo continua fora do Dropbox e a falha da copia externa nao impede o backup local.

Para configurar Dropbox:

1. Crie uma pasta no Dropbox, por exemplo `/Users/thiago/Dropbox/Sistema SannyGold/Backups`.
2. Configure `DROPBOX_BACKUP_DIR` no `.env.local` com esse caminho.
3. Reinicie o sistema.
4. No painel admin, clique em `Testar pasta Dropbox`.
5. Clique em `Gerar backup agora` e confira se o painel mostra a ultima copia Dropbox.

Se a pasta Dropbox nao for encontrada, o painel mostra aviso. Nesse caso, crie a pasta, corrija o caminho em `DROPBOX_BACKUP_DIR` ou deixe sem Dropbox sabendo que o backup local continua salvo em `backups/`.

Configuracoes inseguras sao bloqueadas ou alertadas: nao coloque a pasta inteira do sistema, `data/`, `uploads/` ou `data/sannygold.db` dentro do Dropbox. O Dropbox sincroniza arquivos, nao e banco de dados ativo.

Backup automático:

- O horário padrão é `20:00`.
- O admin pode ativar/desativar e alterar o horário no painel administrativo de backup.
- O sistema registra último backup automático, próxima execução e último erro no painel.
- Se `DROPBOX_BACKUP_DIR` estiver configurado, o backup automático também tenta copiar o `.zip` para o Dropbox.
- Se a cópia Dropbox falhar, o backup local continua salvo e o painel mostra o aviso.

Backup manual por linha de comando:

```bash
python3 scripts/create_local_backup.py --trigger manual_cli
```

O `scripts/start_local.sh` tambem tenta gerar um backup automatico na inicializacao se o ultimo backup tiver mais de 24 horas.

## Restaurar backup

Restauracao manual segura:

1. Parar a aplicacao.
2. Fazer uma copia da pasta `data/` atual antes de mexer.
3. Extrair o `.zip` do backup em uma pasta temporaria.
4. Copiar os arquivos de `data/`, `preview/` e `uploads/` do backup para as pastas equivalentes usadas pelo sistema.
5. Subir a aplicacao.
6. Abrir `/health` e conferir clientes, eventos, financeiro e usuarios.

Exemplo local:

```bash
mkdir -p restore-tmp
unzip backups/sannygold-data-backup-ARQUIVO.zip -d restore-tmp
cp restore-tmp/data/* data/
[ -d restore-tmp/preview ] && cp -R restore-tmp/preview/* preview/
[ -d restore-tmp/uploads ] && cp -R restore-tmp/uploads/* uploads/
python3 -m app.main
```

Em producao, restaure dentro de `ROTAFLOW_STORAGE_DIR`, nao necessariamente na pasta do codigo.

## Migracao JSON para SQLite

A aplicacao pode rodar em modo SQLite local com JSON como espelho de segurança. O banco padrão é `data/sannygold.db`.

Ativar SQLite local:

```bash
python3 scripts/activate_sqlite_storage.py
```

Esse comando:

- atualiza `.env.local` para `SANNYGOLD_STORAGE_BACKEND=sqlite`;
- importa os JSON para `data/sannygold.db`;
- cria relatório em `data/migration_reports/`;
- não apaga os JSON originais.

Validar sem gravar:

```bash
python3 scripts/migrate_json_to_sqlite.py --dry-run
```

Gerar/atualizar `data/sannygold.db`:

```bash
python3 scripts/migrate_json_to_sqlite.py
```

Com caminhos explicitos:

```bash
python3 scripts/migrate_json_to_sqlite.py \
  --data-dir data \
  --db data/sannygold.db \
  --report data/migration_reports/sqlite-migration-manual.json
```

O relatorio informa importados, ignorados e erros. Nao ative leitura/escrita SQLite em producao sem uma etapa separada de validacao.

## PWA/app mobile

O sistema tem uma base PWA simples:

- `app/static/manifest.webmanifest`: permite instalação como app pelo navegador.
- `app/static/service-worker.js`: cacheia recursos estáticos principais.
- `app/static/offline.html`: mensagem clara quando a tela não consegue falar com o servidor local.

Limite atual: o PWA ainda não salva locações offline no celular. Para isso será necessária uma próxima etapa com fila local, sincronização e resolução de conflito.

## Regras de manutencao

- Fazer backup antes de mudancas em dados, templates ou migracao.
- Rodar testes antes e depois de alteracoes relevantes.
- Nao versionar senhas, chaves, backups reais, uploads reais ou dados sensiveis.
- Nao mudar URLs publicas ou nomes de templates sem necessidade.
- Preservar compatibilidade dos JSON enquanto a migracao SQLite nao for ativada.

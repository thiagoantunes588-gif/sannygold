# Instaladores profissionais do SannySystem

## Artefatos

A aplicação desktop é empacotada com Electron Builder.

- Windows: `desktop/release/SannySystem-Setup-2.0.0.exe`
- Mac Apple Silicon: `desktop/release/SannySystem-2.0.0-arm64.dmg`
- Mac Intel: `desktop/release/SannySystem-2.0.0-x64.dmg`
- Checksums: `desktop/release/CHECKSUMS-SHA256.txt`

## Build local

```bash
cd desktop
npm ci
npm run check
npm run build:win
npm run build:mac
npm run release:checksums
```

No macOS, o build `.dmg` é gerado localmente. No Windows, o `.exe` NSIS deve ser validado em uma máquina Windows ou pelo pipeline.

## Pipeline automatizado

O workflow fica em `.github/workflows/sannysystem-desktop-release.yml`.

Ele roda em:

- `windows-latest` para gerar `.exe`;
- `macos-latest` para gerar `.dmg`;
- tags `sannysystem-v*`;
- execução manual pelo GitHub Actions.

Configure a variável de repositório `SANNYSYSTEM_UPDATE_URL` com a URL pública ou interna onde os arquivos de update serão publicados.

## Atualização automática

O app usa `electron-updater`.

Variável principal:

```env
SANNYSYSTEM_UPDATE_URL="https://servidor-interno/releases/"
```

O diretório de update precisa conter os artefatos gerados pelo Electron Builder, incluindo:

- `latest.yml` para Windows;
- `latest-mac.yml` para macOS;
- `.blockmap`;
- `.exe` e `.dmg`.

Em safe mode, updates automáticos ficam desligados.

## Primeira execução

Na primeira execução, o app:

- detecta Dropbox;
- cria `Dropbox/SannySystemData`;
- cria `logs`, `backups`, `temp`, `exports`, `uploads`, `database`, `config`, `sync`, `conflicts` e `updates`;
- valida escrita nas pastas;
- bloqueia executáveis, SQLite, cache e `node_modules` dentro da pasta sincronizada;
- registra diagnóstico de ambiente.

## Logs

Windows installer:

- `%APPDATA%/SannySystem/logs/install.log`
- `%APPDATA%/SannySystem/logs/uninstall.log`

Aplicação:

- `Dropbox/SannySystemData/logs/sannysystem.log`
- `Dropbox/SannySystemData/logs/audit-errors.log`
- logs nativos do Electron em `userData/logs`.

## Safe mode

Use quando uma atualização, migration ou rotina automática precisar ser isolada.

```bash
SannySystem.exe --safe-mode
```

No safe mode:

- migrations automáticas ficam desativadas;
- backup automático fica desativado;
- updates automáticos ficam desativados;
- a conexão PostgreSQL continua sendo validada.

## Recovery mode

Use quando o app não inicia normalmente ou quando falta configuração PostgreSQL.

```bash
SannySystem.exe --recovery
```

O recovery mode abre uma janela com:

- erro de inicialização;
- diagnóstico de Dropbox;
- diagnóstico de PostgreSQL configurado;
- status do `pg_dump`;
- botões para abrir logs, abrir pasta de dados e reiniciar em safe mode.

## Mac profissional

O build `.dmg` é gerado com ícone e layout de instalação em `/Applications`.

Para distribuição fora da equipe, é necessário certificado Apple Developer ID válido e notarização. Sem isso, o arquivo existe e pode ser testado localmente, mas o macOS pode exibir aviso de segurança.

## Checklist de release

1. Atualizar `desktop/package.json` com a versão correta.
2. Configurar `.env` ou `SANNYSYSTEM_UPDATE_URL`.
3. Rodar `npm run check`.
4. Gerar `.exe` e `.dmg`.
5. Rodar `npm run release:checksums`.
6. Testar primeira execução em Windows 10, Windows 11, Mac Intel e Mac Apple Silicon.
7. Validar login, Dropbox, PostgreSQL, backup, logs, safe mode e recovery mode.

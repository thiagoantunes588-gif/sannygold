# Estrutura do Projeto SannyGold

Este projeto deve ficar fora do Dropbox. O Dropbox e usado apenas para distribuir
instaladores e receber backups `.zip` finalizados.

## Pastas principais do projeto

- `app/`: sistema web Flask, telas, rotas, servicos e arquivos estaticos.
- `data/`: banco e arquivos locais de operacao. Nao mover para o Dropbox.
- `uploads/`: arquivos enviados pela equipe. Nao apagar nem mover sem revisao.
- `preview/`: arquivos temporarios de visualizacao operacional, como PDFs recentes.
- `backups/`: backups locais gerados pelo sistema. Preservar backups reais `.zip`.
- `logs/`: registros de execucao e diagnostico.
- `scripts/`: inicializacao, backup, migracao e geracao de instaladores.
- `installer/`: modelos de documentacao e configuracoes usadas pelos instaladores.
- `desktop/`: aplicativo desktop Electron e artefatos de release.
- `mobile/`: aplicativo mobile em desenvolvimento com Expo.
- `docs/`: documentacao tecnica, operacional e administrativa.
- `tests/`: testes automatizados.
- `output/`: arquivos gerados para analise, validacao e exportacao.
- `build/` e `dist/`: saidas de empacotamento. Revisar antes de excluir.
- `_Revisao_Antes_de_Excluir/`: itens separados para decisao humana antes de qualquer exclusao definitiva.

## Local dos instaladores

A pasta de distribuicao fica em:

```text
~/Dropbox/Sistema SannyGold/Instaladores
```

Estrutura esperada:

```text
Instaladores/
  Mac/
    Instalador/
    Atualizações/
    LEIA-ME.md
  Windows/
    Instalador/
    Atualizações/
    LEIA-ME.md
  Celular/
    Android/
    iPhone-iOS/
    Atalho-Web/
    LEIA-ME.md
  Arquivados/
  _Revisao_Antes_de_Excluir/
  LEIA-ME.md
```

## Orientacao para Mac

Os arquivos do Mac ficam em `Instaladores/Mac/Instalador/`.
O arquivo esperado e `SannyGold Sistema.app` ou `SannyGold-Sistema-Mac.zip`.
Para gerar novamente, rode:

```bash
bash scripts/install_macos_launcher.sh
```

## Orientacao para Windows

Os arquivos do Windows ficam em `Instaladores/Windows/Instalador/`.
Os arquivos esperados sao:

- `SannyGold-Sistema-Windows-Setup.exe`
- `SannyGold-Sistema-Windows-Portable.zip`

No Windows, os geradores principais sao:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_all_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\build_windows_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts\package_windows_portable.ps1
```

## Orientacao para celular

A pasta `Instaladores/Celular/` existe para orientar a equipe. Atualmente ela nao
contem APK nem app iOS oficial.

O sistema ja possui suporte web instalavel pelo navegador por meio de
`manifest.webmanifest` e `service-worker.js`. No celular, use o endereco mostrado
em `Acesso pelo celular no Wi-Fi` e adicione o site a tela inicial pelo Chrome
ou Safari.

## Pastas que a equipe pode acessar

- `Instaladores/Mac/Instalador/`
- `Instaladores/Windows/Instalador/`
- `Instaladores/Celular/`
- `docs/`, quando precisar consultar orientacoes.

## Pastas que nao devem ser alteradas manualmente

- `data/`
- `uploads/`
- `backups/`
- `.venv/`
- `desktop/node_modules/`
- `mobile/node_modules/`
- `desktop/release/`, sem decisao de limpeza.
- `build/` e `dist/`, sem confirmar se os artefatos ainda sao necessarios.

## Como atualizar os instaladores

1. Gere o pacote na plataforma correta.
2. Confirme se o arquivo final apareceu em `Instaladores/<Plataforma>/Instalador/`.
3. Mantenha os arquivos antigos em `Arquivados/` ou `_Revisao_Antes_de_Excluir/`
   ate confirmar que nao sao mais necessarios.
4. Nao coloque banco de dados, uploads reais ou a pasta do sistema dentro do Dropbox.

## Como restaurar algo da revisao

1. Abra `_Revisao_Antes_de_Excluir/RELATORIO_LIMPEZA.md`.
2. Localize a origem original do arquivo ou pasta.
3. Mova o item de volta para o caminho original.
4. Rode os testes e abra o sistema antes de excluir qualquer copia restante.

# Instalador Windows do Sistema SannyGold

Este guia descreve o instalador profissional do `SannyGold Sistema` para Windows 10/11.

## Conceito

- O sistema ativo roda localmente no computador.
- O local de instalação padrão é `%LOCALAPPDATA%\SannyGold Sistema`.
- O banco ativo SQLite fica em `%LOCALAPPDATA%\SannyGold Sistema\data\sannygold.db`.
- `data`, `uploads` e `preview` ativos não ficam no Dropbox.
- O Dropbox guarda apenas instaladores e backups `.zip`.

## Pastas Dropbox

Backups:

```text
%USERPROFILE%\Dropbox\Sistema SannyGold\Backups
```

Instaladores:

```text
%USERPROFILE%\Dropbox\Sistema SannyGold\Instaladores
```

Estrutura recomendada:

```text
Dropbox\Sistema SannyGold\
  Backups\
  Instaladores\
    LEIA-ME.md
    Mac\
      Instalador\
      Atualizações\
      LEIA-ME.md
    Windows\
      Instalador\
        SannyGold-Sistema-Windows-Setup.exe
        SannyGold-Sistema-Windows-Portable.zip
      Atualizações\
      LEIA-ME.md
    Celular\
      Android\
      iPhone-iOS\
      Atalho-Web\
      LEIA-ME.md
    _Revisao_Antes_de_Excluir\
    Arquivados\
```

## Gerar o aplicativo Windows

Em um computador Windows com Python instalado:

```powershell
.\scripts\build_windows_app.ps1
```

Esse script:

- cria `.venv`;
- instala `requirements.txt`;
- instala `pyinstaller`;
- gera `dist\windows\SannyGold Sistema\SannyGold Sistema.exe`;
- inclui o launcher, app Flask, templates, arquivos estáticos e scripts necessários;
- não inclui `.env.local`, dados reais, uploads reais nem backups reais.

## Gerar tudo com um comando

Para gerar o app, o zip portátil, o instalador visual quando houver Inno Setup e copiar tudo para o Dropbox, rode:

```powershell
.\scripts\build_all_windows.ps1
```

Para usuário que prefere clicar, use:

```text
scripts\build_all_windows.bat
```

Se o Inno Setup não estiver instalado, o script mantém o zip portátil e mostra:

```text
Versão portátil criada. Instalador visual não criado porque Inno Setup não foi encontrado.
```

Se nenhum pacote for gerado, o script falha com:

```text
ERRO: nenhum pacote Windows foi gerado.
```

## Como saber se deu certo

Abra esta pasta no Windows:

```text
%USERPROFILE%\Dropbox\Sistema SannyGold\Instaladores\Windows
```

Ela deve conter pelo menos um destes arquivos:

```text
Instalador\SannyGold-Sistema-Windows-Setup.exe
Instalador\SannyGold-Sistema-Windows-Portable.zip
```

Também é esperado que exista:

```text
LEIA-ME.md
```

Se a pasta tiver apenas arquivos `.md`, o instalador Windows ainda não foi gerado. Arquivos `.md` são somente documentação; eles não instalam nem abrem o sistema.

## Gerar o pacote portátil

Em um computador Windows, rode:

```powershell
.\scripts\package_windows_portable.ps1
```

Esse script compacta `dist\windows\SannyGold Sistema` e copia o arquivo para:

```text
%USERPROFILE%\Dropbox\Sistema SannyGold\Instaladores\Windows\Instalador\SannyGold-Sistema-Windows-Portable.zip
```

Dentro do zip fica:

```text
SannyGold Sistema\
  SannyGold Sistema.exe
  abrir-sistema.bat
  diagnostico-dropbox.bat
  configurar-dropbox.bat
  LEIA-PRIMEIRO.txt
  data\
  uploads\
  preview\
  backups\
  logs\
```

O usuário comum abre `abrir-sistema.bat` ou `SannyGold Sistema.exe`. Não precisa abrir PowerShell para usar a versão portátil.

## Gerar o instalador

Instale o Inno Setup 6 e rode:

```powershell
.\scripts\build_windows_installer.ps1
```

O script verifica se `dist\windows\SannyGold Sistema\SannyGold Sistema.exe` existe. Se não existir, ele chama `scripts\build_windows_app.ps1`. Depois localiza `ISCC.exe`, compila `installer\windows\sannygold-windows.iss` e gera:

```text
dist\installers\SannyGold-Sistema-Windows-Setup.exe
%USERPROFILE%\Dropbox\Sistema SannyGold\Instaladores\Windows\Instalador\SannyGold-Sistema-Windows-Setup.exe
```

Se o Inno Setup não existir, a mensagem esperada é:

```text
Instale o Inno Setup para gerar o instalador .exe visual.
```

Se o Inno Setup não estiver instalado, existem duas opções:

- usar a versão portátil gerada por `scripts\package_windows_portable.ps1`;
- permitir que o script tente instalar via `winget`, se o Windows tiver `winget` disponível;
- instalar o Inno Setup 6 ou 7 manualmente e rodar `scripts\build_windows_installer.ps1` novamente.

Quando `winget` estiver disponível, o script pergunta:

```text
Inno Setup não encontrado. Deseja instalar agora via winget? S/N
```

Se você responder `S`, ele executa:

```powershell
winget install --id JRSoftware.InnoSetup -e -s winget
```

Se o Inno Setup continuar indisponível, o script gera somente a versão portátil e mostra:

```text
Instalador visual não foi criado, mas a versão portátil foi gerada.
```

Se o Dropbox não existir, o script falha com mensagem clara. O resultado final precisa existir fisicamente na pasta `Windows\Instalador` do Dropbox e ter tamanho maior que 10 MB.

```text
Status final: INSTALADOR WINDOWS GERADO COM SUCESSO
```

## Instalar no Windows

1. Abra `Dropbox\Sistema SannyGold\Instaladores\Windows\Instalador`.
2. Dê dois cliques em `SannyGold-Sistema-Windows-Setup.exe`.
3. Mantenha marcada a opção de atalho na Área de Trabalho.
4. Mantenha marcada a opção de abrir o SannyGold após instalar.
5. Use o launcher gráfico para abrir o sistema.

## Primeiro uso

O launcher cria automaticamente:

- `.env.local`;
- `data`;
- `uploads`;
- `preview`;
- `backups`;
- `logs`;
- `tmp`.

Se o Dropbox existir, ele configura:

```text
DROPBOX_BACKUP_DIR=%USERPROFILE%\Dropbox\Sistema SannyGold\Backups
```

Se não existir, o launcher mostra:

```text
Dropbox não encontrado. O sistema funcionará localmente, mas o backup externo não está ativo.
```

## Segurança

Não instale nem mova a pasta do sistema para dentro do Dropbox.

Nunca coloque no Dropbox:

- `data\sannygold.db`;
- `data`;
- `uploads`;
- `preview`.

## Desinstalar

Use `Adicionar ou remover programas` no Windows e remova `SannyGold Sistema`.

Antes de desinstalar, gere um backup e confirme se o `.zip` foi copiado para `Dropbox\Sistema SannyGold\Backups`.

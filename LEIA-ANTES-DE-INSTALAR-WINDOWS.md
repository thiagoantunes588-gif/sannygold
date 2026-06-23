# Leia Antes de Instalar no Windows

ATENÇÃO:
Se esta pasta tiver apenas arquivos .md, o instalador Windows ainda não foi gerado.
Para instalar no Windows, esta pasta precisa conter pelo menos um destes arquivos:
- Instalador\SannyGold-Sistema-Windows-Setup.exe
- Instalador\SannyGold-Sistema-Windows-Portable.zip

O arquivo .md é apenas documentação. Ele não instala o sistema.

Este instalador cria o aplicativo `SannyGold Sistema` no Windows sem exigir que o usuario abra PowerShell ou rode comandos manualmente.

## Instalar

1. Abra a pasta `Dropbox\Sistema SannyGold\Instaladores\Windows\Instalador`.
2. Dê dois cliques em `SannyGold-Sistema-Windows-Setup.exe`.
3. Mantenha marcada a opção `Criar atalho na Área de Trabalho`.
4. Mantenha marcada a opção `Abrir SannyGold Sistema após instalar`.

Também pode existir `SannyGold-Sistema-Windows-Portable.zip` na mesma pasta. Ele é uma versão portátil para suporte técnico. Para uso normal, instale pelo `.exe`.

Para usar a versão portátil, extraia o `.zip`, abra a pasta `SannyGold Sistema` e dê dois cliques em `abrir-sistema.bat`.

## Abrir pelo atalho

Depois da instalação, use o atalho `SannyGold Sistema` na Área de Trabalho ou no Menu Iniciar.

## Testar Dropbox

No launcher, abra `Configuração inicial` e clique em `Testar Dropbox`.

Mensagem esperada quando tudo estiver correto:

`Dropbox OK`

Se o Dropbox não existir, o sistema continuará localmente e mostrará:

`Dropbox não encontrado. O sistema funcionará localmente, mas o backup externo não está ativo.`

## Gerar backup

No launcher, clique em `Gerar backup` ou `Gerar backup agora`.

O backup local fica na pasta instalada, em `backups`.

Quando o Dropbox estiver disponível, uma cópia `.zip` será enviada para:

`%USERPROFILE%\Dropbox\Sistema SannyGold\Backups`

## Não mover para o Dropbox

Não mova a pasta instalada para dentro do Dropbox.

O Dropbox deve guardar apenas:

- instaladores;
- backups `.zip`.

O banco ativo `sannygold.db`, `data`, `uploads` e `preview` devem ficar protegidos no computador.

## Desinstalar

Use `Adicionar ou remover programas` do Windows e procure por `SannyGold Sistema`.

Antes de desinstalar, gere um backup e confirme se o `.zip` apareceu no Dropbox.

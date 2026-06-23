# SannyGold Sistema no macOS

Guia rapido para abrir a SannyGold no Mac como aplicativo, sem terminal.

## O que este app faz

O app `SannyGold Sistema.app` chama o launcher Python do projeto.

Ao abrir, ele:

1. inicia o servidor local com `waitress`;
2. abre o navegador em `http://127.0.0.1:5007/`, ou na porta configurada;
3. mostra status do sistema;
4. mostra endereco para celular no mesmo Wi-Fi;
5. permite gerar backup manual;
6. mostra status do Dropbox;
7. permite parar o servidor iniciado por ele.

## Onde ficam os arquivos

- Dados ativos: `data/`
- Banco local: `data/sannygold.db`
- Backups locais: `backups/`
- Uploads/anexos: `uploads/`
- PDFs e rotas geradas: `preview/`
- Configuracao local: `.env.local`
- Logs do launcher: `logs/launcher.log`
- Logs do app macOS: `logs/macos-launcher.log`

O Dropbox deve receber somente arquivos `.zip` de backup. Nao mova `data/` nem `sannygold.db` para dentro do Dropbox.

## Gerar o app

No Mac, rode uma vez:

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
bash scripts/install_macos_launcher.sh
```

O app sera criado em:

```text
~/Applications/SannyGold Sistema.app
```

O icone atual e o icone padrao de aplicativo AppleScript. Ele e um placeholder simples para esta etapa.

## Usar no dia a dia

1. Abra `~/Applications`.
2. Dê dois cliques em `SannyGold Sistema.app`.
3. Aguarde a janela de status aparecer.
4. O navegador deve abrir automaticamente.
5. Para celular, use o endereco mostrado na janela ou a tela admin `Acesso pelo Celular`.

## Colocar no Dock

1. Abra `~/Applications`.
2. Arraste `SannyGold Sistema.app` para o Dock.
3. Use o icone do Dock para abrir o sistema.

## Iniciar junto com o macOS

1. Abra `Ajustes do Sistema`.
2. Entre em `Geral`.
3. Abra `Itens de Inicio`.
4. Adicione `SannyGold Sistema.app`.

Se o Mac reiniciar, o sistema abrira automaticamente quando o usuario entrar na conta do macOS.

## Configurar porta

No arquivo `.env.local`, use:

```text
PORT=5007
FLASK_HOST=0.0.0.0
```

Use `FLASK_HOST=0.0.0.0` para permitir acesso pelo celular no mesmo Wi-Fi. Use `FLASK_HOST=127.0.0.1` se quiser permitir acesso apenas no proprio Mac.

## Diagnosticar erro

Se o app nao abrir:

1. Confira se existe `logs/macos-launcher.log`.
2. Confira `logs/launcher.log`.
3. Verifique se a porta configurada ja esta sendo usada por outro processo.
4. Rode manualmente para ver mensagens:

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
python3 scripts/sannygold_launcher.py
```

## PyInstaller

PyInstaller ainda nao e necessario para a operacao local. O app atual e mais simples e deixa dados, backups e configuracao na pasta do projeto.

Use PyInstaller no futuro se for preciso distribuir um app independente para outro computador. Antes disso, sera necessario definir assinatura, atualizacao, local fixo de dados e estrategia de suporte.

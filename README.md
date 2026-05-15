# SannyGold Operacao

Sistema interno para organizar a operacao da SannyGold: clientes, eventos, banheiros, equipamentos, frota, rotas, PDFs operacionais, almoxarifado, financeiro e acessos da equipe.

Caminho oficial:

```text
/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna
```

Este projeto antes aparecia como `gestor-de-rota-empresa`, mas o nome de trabalho mais claro e `SannyGold Operacao`, porque o sistema ja deixou de ser apenas um planejador de rotas.

## Para que serve

- Centralizar os clientes, eventos e produtos principais da SannyGold.
- Organizar banheiros, equipamentos e veiculos usados em cada operacao.
- Validar uma operacao antes de gerar rota ou PDF.
- Gerar material operacional para impressao, PDF e links de endereco.
- Controlar financeiro, contas a receber, recibos, fechamento e relatorios.
- Controlar almoxarifado, estoque baixo, movimentacoes e historico.
- Gerenciar usuarios, permissoes e acessos internos.

## Como abrir localmente

Modo recomendado:

```bash
bash scripts/start_local.sh
```

Depois abra:

```text
http://127.0.0.1:5007
```

Modo manual:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m app.main
```

Depois abra:

```text
http://127.0.0.1:5000
```

## Mapa rapido do projeto

- `app/`: aplicacao principal em Flask.
- `app/templates/`: telas do sistema.
- `app/static/`: imagens e arquivos visuais.
- `data/`: base local em JSON usada pela versao atual.
- `docs/`: finalizacao e orientacoes de uso.
- `references/`: regras de operacao, dados e materiais de apoio.
- `scripts/`: rotinas para iniciar, gerar PDFs e planejar rotas.
- `tests/`: testes automatizados do sistema.
- `preview/`: arquivos de rota e PDF para conferencia interna.
- `uploads/`: arquivos enviados/importados.
- `web/`: painel antigo/local de planejamento de rota, mantido como apoio.

## Fluxo diario recomendado

1. Abrir o sistema e revisar o que precisa de atencao.
2. Cadastrar ou atualizar clientes, eventos, banheiros, equipamentos e veiculos.
3. Validar a operacao antes de gerar a rota.
4. Gerar o PDF operacional.
5. Repassar o PDF impresso, arquivo ou links de endereco para a equipe.
6. Registrar ajustes internos, financeiro e almoxarifado quando necessario.
7. Baixar backup ou fechamento ao fim do dia.

## Principais documentos

- `app/README.md`: guia completo da aplicacao principal.
- `docs/finalizacao-local.md`: uso interno local.
- `docs/finalizacao-v1.md`: checklist para publicar e operar a v1.
- O Assistente Operacional dentro do sistema concentra a ajuda de uso da equipe.
- `references/operational-rules.md`: regras e indicadores operacionais.
- `references/mobile-operation.md`: playbook do PDF operacional.

## Publicacao

O arquivo `render.yaml` esta preparado para Render com disco persistente em `/var/data`.

Variaveis importantes:

- `SANNYGOLD_SECRET_KEY`
- `SANNYGOLD_ADMIN_EMAIL=contato@sannygold.com`
- `SANNYGOLD_ADMIN_PASSWORD`
- `SANNYGOLD_ADMIN_NAME`
- `ROTAFLOW_STORAGE_DIR=/var/data`

## Observacao

Nao renomeie a pasta do projeto sem revisar os comandos e caminhos salvos em scripts, deploy e documentos. O nome de trabalho foi melhorado nos arquivos para facilitar o uso sem quebrar configuracoes existentes.

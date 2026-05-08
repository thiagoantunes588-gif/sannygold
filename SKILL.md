---
name: sannygold-operacao
description: Gerenciar o sistema interno da SannyGold para operacao, clientes, eventos, banheiros, equipamentos, frota, rotas, PDF operacional, almoxarifado, financeiro e acessos. Use quando houver necessidade de melhorar fluxo de trabalho, telas, regras operacionais, relatorios, permissoes, dados em JSON, deploy Flask ou documentacao deste projeto.
---

# SannyGold Operacao

Sistema Flask usado para centralizar o dia a dia da SannyGold. O foco do produto e banheiros, com apoio de equipamentos, frota, rotas, financeiro, almoxarifado e materiais impressos/PDF para execucao.

## Fluxo rapido

1. Entender se a demanda e operacional, financeira, cadastro, acesso, estoque, PDF ou deploy.
2. Reusar os modulos existentes antes de criar uma tela nova.
3. Preservar o fluxo administrativo: a equipe recebe PDF, impresso ou links de endereco quando necessario.
4. Validar mudancas com testes direcionados e, em alteracoes de tela, uma checagem do app renderizado.
5. Manter linguagem de negocio centrada em SannyGold, banheiros, eventos e operacao.

## Comandos uteis

Abrir localmente:

```bash
bash scripts/start_local.sh
```

Rodar testes com `unittest`:

```bash
python3 -m unittest discover tests
```

Se houver erro de permissao de cache Python no macOS:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/rotaflow-pycache python3 -m unittest discover tests
```

Gerar pacote operacional de conferencia:

```bash
bash scripts/generate_mobile_package.sh
```

## Arquivos principais

- Aplicacao Flask: `app/main.py`
- Tela principal: `app/templates/index.html`
- Dados locais: `data/*.json`
- Documentacao: `README.md`, `app/README.md`, `docs/`, `references/`
- Testes: `tests/`

## Diretrizes do projeto

- Preferir melhorias praticas para o uso diario, com menos cliques e pendencias mais visiveis.
- Nao criar fluxo separado de equipe em campo sem pedido explicito.
- Usar PDF, impresso e links de endereco como entrega operacional externa.
- Tratar placas de equipamentos como opcionais, porque alguns itens nao possuem placa.
- Evitar linguagem generica de inventario quando o contexto correto for banheiros e operacao SannyGold.

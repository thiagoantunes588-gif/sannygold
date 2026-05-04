# Sistema SannyGold

## Subir localmente

Modo recomendado:

```bash
cd "/Users/thiagoantunes/Documents/New project/gestor-de-rota-empresa"
bash scripts/start_local.sh
```

Abra:

```text
http://127.0.0.1:5007
```

Modo manual:

```bash
cd "/Users/thiagoantunes/Documents/New project/gestor-de-rota-empresa"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m app.main
```

Abra:

```text
http://127.0.0.1:5000
```

## O que a versão atual já faz

- cadastro de clientes, veículos, equipamentos e eventos
- autenticação com modo visitante, roles e permissões por módulo
- data inicial e data final no evento
- cálculo automático de diárias pelo período do evento
- geração de rotas com validação prévia
- dashboard operacional, financeiro, agenda futura e pendências
- almoxarifado interno com reposição, baixa, ajuste e histórico
- financeiro com contas a receber, fluxo de caixa, inadimplência e fechamento mensal
- busca global fixa, modo operação rápida e filtros persistentes
- importação de clientes por texto em lote
- importação de clientes por Excel `.xlsx`
- PDF operacional para repassar ao motorista ou equipe
- relatórios PDF/Excel por módulo
- backup rápido dos dados do sistema

## Fluxo recomendado de uso

1. Cadastre ou importe os clientes.
2. Cadastre veículos e equipamentos.
3. Crie o evento com data inicial e data final.
4. Vincule clientes e veículos ao evento.
5. Valide a operação antes de gerar a rota.
6. Gere a rota.
7. Abra o PDF e repasse para o motorista ou equipe.
8. Registre confirmações de campo.
9. Acompanhe margem, lucro e capacidade no painel.

## Importação por Excel

Na aba `Clientes`, use `Baixar modelo Excel` e depois envie o `.xlsx`.

Colunas aceitas:

- `nome`
- `endereco`
- `latitude`
- `longitude`
- `tipo`
- `equipamento`
- `quantidade`
- `equipamento_id`
- `servico`
- `prioridade`
- `valor_servico`
- `custo_equipe`
- `custo_equipamento`
- `janela_inicial`
- `janela_final`
- `veiculo_travado`
- `contato`
- `cpf_cnpj`
- `email`

## Backup

Na aba `Clientes`, use `Baixar backup do sistema`.

O arquivo `.zip` inclui:

- clientes
- veículos
- equipamentos
- eventos
- histórico
- configurações
- última validação
- última projeção
- último PDF e JSON gerados
- usuários, auditoria, almoxarifado e financeiro

## Materiais de finalização

- `docs/finalizacao-v1.md`: checklist de aceite, deploy e rotina v1.0.
- `docs/manual-rapido-equipe.md`: manual em texto para treinamento.
- `output/pdf/sannygold-manual-rapido-equipe.pdf`: manual rápido em PDF.
- `output/pdf/sannygold-apresentacao-sistema.pdf`: apresentação do sistema em PDF.

## Publicação

O arquivo `render.yaml` está preparado para Render com disco persistente em `/var/data`.

Antes de publicar, configure no provedor:

- `SANNYGOLD_SECRET_KEY`
- `SANNYGOLD_ADMIN_EMAIL=contato@sannygold.com`
- `SANNYGOLD_ADMIN_PASSWORD`
- `SANNYGOLD_ADMIN_NAME`
- `ROTAFLOW_STORAGE_DIR=/var/data`

## Monitoramento básico

Endpoints úteis depois do deploy:

- `GET /health`: status básico da aplicação, armazenamento e artefatos principais.
- `GET /system/status.json`: snapshot operacional autenticado com versão, ambiente, contagens e status do sistema.

## Observação operacional

Para uso interno imediato, a versão local já está pronta. Para uso em equipe com acesso externo contínuo, o próximo passo ideal é publicar em uma hospedagem estável para Python, como Render, com backup recorrente.

Veja tambem `docs/finalizacao-v1.md` para o checklist final de versão.

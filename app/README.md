# Sistema Geral SannyGold

Aplicacao principal do sistema interno da SannyGold. Ela concentra operacao, banheiros, equipamentos, frota, eventos, rotas, PDFs, almoxarifado, financeiro e acessos da equipe.

## Subir localmente

Modo recomendado:

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
bash scripts/start_local.sh
```

Abra:

```text
http://127.0.0.1:5007
```

Modo manual:

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m app.main
```

Abra:

```text
http://127.0.0.1:5000
```

## O que a versao atual ja faz

- cadastro de clientes, banheiros, equipamentos, veiculos e eventos
- autenticacao com modo visitante, roles e permissoes por modulo
- data inicial e data final no evento
- calculo automatico de diarias pelo periodo do evento
- geracao de rotas com validacao previa
- dashboard operacional, financeiro, agenda futura e pendencias
- almoxarifado interno com reposicao, baixa, ajuste e historico
- financeiro com contas a receber, fluxo de caixa, inadimplencia e fechamento mensal
- busca global fixa, modo operacao rapida e filtros persistentes
- importacao de clientes por texto em lote
- importacao de clientes por Excel `.xlsx`
- PDF operacional para repassar impresso, em arquivo ou com links de endereco
- relatorios PDF/Excel por modulo
- backup rapido dos dados do sistema

## Fluxo recomendado de uso

1. Cadastre ou importe os clientes.
2. Cadastre banheiros, equipamentos e veiculos.
3. Crie o evento com data inicial e data final.
4. Vincule clientes e veículos ao evento.
5. Valide a operação antes de gerar a rota.
6. Gere a rota.
7. Abra o PDF e repasse para a equipe no formato combinado.
8. Registre internamente ajustes, observacoes e finalizacao.
9. Acompanhe pendencias, margem, lucro e capacidade no painel.

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

- `README.md`: guia tecnico de instalacao, testes, backup, restore e migracao.
- `docs/manual-equipe.md`: manual rapido para operacao e financeiro.
- `docs/manual-admin.md`: manual de acessos, auditoria, backup e pendencias criticas.
- `docs/finalizacao-v1.md`: checklist de aceite, deploy e rotina v1.0.
- O Assistente Operacional dentro do sistema concentra a ajuda de uso da equipe.
- `output/pdf/sannygold-apresentacao-sistema.pdf`: apresentação do sistema em PDF.

## Publicação

O arquivo `render.yaml` está preparado para Render com disco persistente em `/var/data`.

Antes de publicar, configure no provedor:

- `SANNYGOLD_ENV=production`
- `SANNYGOLD_SECRET_KEY` com 32+ caracteres aleatorios. Exemplo de geracao: `openssl rand -hex 32`.
- `SANNYGOLD_ADMIN_EMAIL=contato@sannygold.com`
- `SANNYGOLD_ADMIN_PASSWORD`
- `SANNYGOLD_ADMIN_NAME`
- `ROTAFLOW_STORAGE_DIR=/var/data`
- `FLASK_DEBUG=0`
- `SANNYGOLD_SESSION_COOKIE_SECURE=1` quando o acesso for por HTTPS fora do Render/Vercel.

Seguranca basica ativa:

- sessoes com cookie `HttpOnly`, `SameSite=Lax` e `Secure` em producao;
- formularios `POST` protegidos por CSRF;
- uploads limitados a 10 MB e a extensoes esperadas por cada fluxo;
- paginas de erro comuns exibem mensagens simples, sem stack trace para usuario comum.

## Monitoramento básico

Endpoints úteis depois do deploy:

- `GET /health`: status básico da aplicação, armazenamento e artefatos principais.
- `GET /system/status.json`: snapshot operacional autenticado com versão, ambiente, contagens e status do sistema.

## Estrutura do backend

- `app/main.py`: aplicacao Flask, dashboard, dados legados e rotas ainda nao extraidas.
- `app/routes/`: rotas ja separadas por responsabilidade.
- `app/services/`: servicos reutilizaveis sem renderizacao de tela.
- `app/repositories/`: camada preparada para armazenamento SQLite paralelo.
- `app/db/schema.sql`: schema inicial do banco local `data/sannygold.db`.
- `docs/backend-route-map.md`: mapa atual dos grupos de rotas e status da refatoracao.
- `docs/sqlite-migration-plan.md`: plano de migracao gradual JSON -> SQLite.

## Observação operacional

Para uso interno imediato, a versão local já está pronta. Para uso em equipe com acesso externo contínuo, o próximo passo ideal é publicar em uma hospedagem estável para Python, como Render, com backup recorrente.

Veja tambem `docs/finalizacao-v1.md` para o checklist final de versão.

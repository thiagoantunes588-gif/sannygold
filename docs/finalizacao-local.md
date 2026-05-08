# Finalizacao local do Sistema SannyGold

Este guia fecha a versao local para uso interno da operacao.

## Abrir o sistema

Use o script abaixo a partir da raiz do projeto:

```bash
bash scripts/start_local.sh
```

Depois abra:

```text
http://127.0.0.1:5007
```

O script cria as pastas locais de dados, prepara o ambiente Python e inicia o Flask.

## Checklist de operacao diaria

1. Baixar um backup em `Clientes > Baixar backup do sistema`.
2. Conferir clientes, veiculos e equipamentos antes de criar o evento.
3. Criar o evento com data inicial e data final.
4. Vincular clientes e veiculos ao evento.
5. Rodar `Validar operacao`.
6. Gerar a rota somente quando a validacao estiver apta.
7. Abrir o PDF operacional e repassar impresso, em arquivo ou com links de endereco.
8. Registrar internamente ajustes, observacoes e finalizacao.
9. Baixar novo backup ao fim do dia.

## Arquivos de conferencia interna

Para atualizar os arquivos em `preview/` quando precisar conferir rota e PDF:

```bash
bash scripts/generate_mobile_package.sh
```

Arquivos gerados:

- `preview/route-app.html`
- `preview/route-plan-mobile.json`
- `preview/route-plan.pdf`

## Dados locais

Os dados de trabalho ficam em:

- `data/clients.json`
- `data/vehicles.json`
- `data/equipment.json`
- `data/events.json`
- `data/field_confirmations.json`
- `data/route_history.json`
- `data/settings.json`

Nao apague esses arquivos sem antes baixar o backup do sistema.

## Entrega para equipe

Para uso em um unico computador, basta manter esta pasta do projeto e abrir pelo script local.

Para mais de uma pessoa acessando ao mesmo tempo, publique em um servidor Python estavel e configure armazenamento persistente. Render e uma boa opcao para a proxima etapa, mas o caminho atual esta fechado para uso local interno.

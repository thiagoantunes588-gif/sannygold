# Painel Web Local

Este painel permite subir `deliveries.csv` e `vehicles.csv` pelo navegador e gerar:

- `route-plan.json`
- `route-plan.html`
- `route-plan.pdf`

Tambem inclui um cadastro local de clientes, salvo em:

- `data/clients.json`

Com exportacao em CSV pelo proprio painel.

## Como iniciar

```bash
cd /Users/thiagoantunes/Documents/New\ project/gestor-de-rota-empresa
python3 web/panel_app.py --port 8010
```

Abra no navegador:

```text
http://127.0.0.1:8010
```

## Onde os arquivos ficam salvos

Cada execucao cria uma pasta em:

```text
tmp/panel_runs/<run_id>/
```

Com:

- `inputs/deliveries.csv`
- `inputs/vehicles.csv`
- `route-plan.json`
- `route-plan.html`
- `route-plan.pdf`

## Teste rapido

Voce pode usar os arquivos de modelo em:

- `assets/templates/deliveries.csv`
- `assets/templates/vehicles.csv`

# Painel Local de Rotas

Painel auxiliar antigo para testar planejamento de rotas por arquivos CSV. O sistema principal de trabalho fica em `app/`; mantenha este painel apenas como apoio tecnico quando precisar simular rota com `deliveries.csv` e `vehicles.csv`.

Ele permite subir os arquivos pelo navegador e gerar:

- `route-plan.json`
- `route-plan.html`
- `route-plan.pdf`

Tambem inclui um cadastro local simples de clientes, salvo em:

- `data/clients.json`

Com exportacao em CSV pelo proprio painel.

## Como iniciar

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
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

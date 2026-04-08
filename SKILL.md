---
name: gestor-de-rota-empresa
description: Gerenciar planejamento de rotas corporativas com foco mobile para operação de motorista em campo, incluindo entregas e coletas com restrições de frota, capacidade, janelas de atendimento e prioridade. Use quando houver necessidade de organizar paradas para celular, gerar plano diário de rota, produzir payload JSON enxuto para app, calcular KPIs logísticos, ou validar dados de operação em CSV/JSON.
---

# Gestor de Rota Empresa

Planejar rotas de operação logística com foco mobile-first, priorizando execução em celular, dados compactos e continuidade operacional em campo.

## Fluxo rápido

1. Validar o tipo de demanda: entrega, coleta ou mista.
2. Solicitar ou montar os arquivos `deliveries.csv` e `vehicles.csv` conforme `references/data-contract.md`.
3. Executar `scripts/plan_routes.py` para gerar distribuição inicial de rotas.
4. Revisar pendências e gargalos usando `references/operational-rules.md`.
5. Entregar ao usuário um plano acionável com KPIs e riscos operacionais para uso em mobile.

## Comando padrão

```bash
python3 scripts/plan_routes.py \
  --deliveries assets/templates/deliveries.csv \
  --vehicles assets/templates/vehicles.csv \
  --output /tmp/route-plan-mobile.json \
  --mobile-output
```

## Exportacao em PDF

```bash
python3 scripts/plan_routes.py \
  --deliveries assets/templates/deliveries.csv \
  --vehicles assets/templates/vehicles.csv \
  --output /tmp/route-plan-mobile.json \
  --mobile \
  --pdf-output /tmp/route-plan.pdf
```

- Usar `--pdf-output` para gerar um resumo imprimivel da rota.
- O PDF inclui resumo geral, veiculo, ordem das paradas e pendencias.

## Pacote mobile interno

```bash
bash scripts/generate_mobile_package.sh
```

- Gera `preview/index.html` para abertura direta no celular.
- Atualiza `preview/route-plan.pdf` e `preview/route-plan-mobile.json`.
- Mantem o uso interno, sem necessidade de publicacao publica.

## Diretrizes mobile

- Priorizar saída com `--mobile-output` para reduzir payload e tempo de sincronização.
- Exibir sempre a próxima parada (`next_stop`) por veículo no app do motorista.
- Garantir coordenadas (`lat`, `lng`) em cada parada para navegação imediata.
- Permitir preenchimento de `customer_name`, `equipment_number` e `address` em cada parada.
- Tratar `unassigned` como fila de exceção para despacho central.
- Evitar campos não utilizados pela tela de operação em campo.

## Interpretação de resultados

- Priorizar `unassigned_deliveries` como principal alerta operacional.
- Verificar `utilization_capacity_pct` para equilíbrio da frota.
- Usar `distance_km` e `total_minutes` para comparar cenários antes de confirmar despacho.

## Ajustes recomendados

- Replanejar quando houver mais de 10% de paradas não atribuídas.
- Inserir veículo adicional quando houver excesso de capacidade recorrente.
- Reduzir raio de rota quando tempo de deslocamento superar tempo de serviço.
- Repriorizar entregas críticas para início de rota.

## Recursos

- Script de planejamento: `scripts/plan_routes.py`
- Contrato de dados: `references/data-contract.md`
- Regras operacionais e KPIs: `references/operational-rules.md`
- Playbook mobile: `references/mobile-operation.md`
- Templates de entrada: `assets/templates/`

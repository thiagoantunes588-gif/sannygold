# Regras operacionais e KPIs

## Objetivo diário

- Maximizar atendimento de paradas com prioridade alta.
- Minimizar distância e tempo total de operação.
- Evitar ociosidade e sobrecarga entre veículos.
- Garantir fluidez da operação no aplicativo mobile.

## KPIs mínimos

- `assigned_ratio`: paradas alocadas / total de paradas.
- `distance_km`: km total por veículo e da frota.
- `total_minutes`: tempo total por rota incluindo deslocamento e serviço.
- `utilization_capacity_pct`: carga usada / capacidade total por veículo.
- `mobile_sync_success_pct`: eventos sincronizados / eventos enviados pelo app.
- `proof_of_delivery_pct`: entregas com confirmação em campo (assinatura, foto ou check-in).

## Alertas

- `assigned_ratio < 0.9`: necessidade de ajuste de frota ou janela.
- `utilization_capacity_pct > 95`: risco de estouro por variação real de carga.
- `total_minutes` próximo do limite de `max_minutes`: risco de atraso.
- `mobile_sync_success_pct < 98`: risco de perda de rastreabilidade.
- Alta taxa de bateria crítica no turno: risco de interrupção operacional.

## Ações corretivas

- Repriorizar entregas críticas para primeiros slots.
- Dividir rota com muitos desvios geográficos.
- Criar veículo reserva para picos previsíveis.
- Ajustar janelas muito restritivas com área comercial.
- Ativar rotina de pré-download de rota e verificação de bateria antes da saída.

# Regras operacionais e KPIs

## Objetivo diário

- Maximizar atendimento de paradas com prioridade alta.
- Minimizar distância e tempo total de operação.
- Evitar ociosidade e sobrecarga entre veículos.
- Garantir que o administrativo consiga gerar PDF, impressao e links de endereco sem retrabalho.

## KPIs mínimos

- `assigned_ratio`: paradas alocadas / total de paradas.
- `distance_km`: km total por veículo e da frota.
- `total_minutes`: tempo total por rota incluindo deslocamento e serviço.
- `utilization_capacity_pct`: carga usada / capacidade total por veículo.
- `pdf_ready_pct`: operacoes com PDF gerado e conferido antes do repasse.
- `internal_closeout_pct`: operacoes com ajustes e finalizacao registrados internamente.

## Alertas

- `assigned_ratio < 0.9`: necessidade de ajuste de frota ou janela.
- `utilization_capacity_pct > 95`: risco de estouro por variação real de carga.
- `total_minutes` próximo do limite de `max_minutes`: risco de atraso.
- `pdf_ready_pct < 100`: risco de equipe sair com informacao incompleta.
- Operacoes sem finalizacao interna: risco de perder historico e pendencias.

## Ações corretivas

- Repriorizar entregas críticas para primeiros slots.
- Dividir rota com muitos desvios geográficos.
- Criar veículo reserva para picos previsíveis.
- Ajustar janelas muito restritivas com área comercial.
- Conferir PDF, contatos e links de endereco antes de repassar para a equipe.

# Contrato de dados

## Arquivo `deliveries.csv`

Campos obrigatórios:

- `id` texto único da parada
- `lat` latitude decimal
- `lng` longitude decimal
- `demand` demanda de capacidade (inteiro)
- `service_minutes` tempo médio de atendimento no ponto (inteiro)

Campos opcionais:

- `customer_name` nome do cliente vinculado a parada
- `client_type` tipo do cliente (`fixo` ou `avulso`)
- `equipment_type` qual equipamento sera entregue ou atendido
- `equipment_quantity` quantidade de equipamentos nesta parada
- `equipment_number` identificador do equipamento vinculado a parada
- `priority` inteiro (1 mais urgente; padrão 3)
- `window_start` início da janela no formato `HH:MM` (padrão `08:00`)
- `window_end` fim da janela no formato `HH:MM` (padrão `18:00`)
- `address` texto livre

## Arquivo `vehicles.csv`

Campos obrigatórios:

- `id` identificador do veículo
- `start_lat` latitude de início
- `start_lng` longitude de início
- `capacity` capacidade total do veículo

Campos opcionais:

- `vehicle_type` tipo do veículo
- `plate` placa do veículo
- `model` modelo do veículo
- `max_stops` máximo de paradas (padrão 999)
- `max_minutes` máximo de minutos operacionais da rota (padrão 600)

## Regras de qualidade

- Não repetir `id` em `deliveries.csv`.
- Não usar coordenadas vazias.
- Não usar `demand <= 0`.
- Definir janela coerente (`window_start < window_end`).

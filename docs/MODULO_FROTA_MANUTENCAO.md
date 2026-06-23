# Módulo Frota - Manutenção (Fase 2)

Implementação concluída em 21 de junho de 2026 no sistema Flask/SQLite ativo do SannyGold.

## Escopo

Esta fase entrega ordens de serviço de frota, itens e serviços, custos, reserva e baixa de peças, planos preventivos, vencimentos por data e quilometragem, anexos e histórico do veículo.

Não fazem parte desta fase: multas, Detran, sinistros completos, checklist de saída/retorno, rastreamento em tempo real ou integrações externas.

## Entidades

### FleetServiceOrder

Tabela `fleet_service_orders`, espelho `data/fleet_service_orders.json` e número único no formato `OS-FROTA-AAAA-000001`.

Contém veículo, tipo, status, prioridade, problema, diagnóstico, serviços realizados, datas, quilometragens, fornecedor, responsáveis, custos, desconto, indisponibilidade, garantia, próxima revisão, observações, autoria e exclusão lógica.

### FleetServiceOrderItem

Tabela `fleet_service_order_items` e espelho `data/fleet_service_order_items.json`.

Tipos: peça, material, serviço, mão de obra, taxa e outros. Quantidade e custos não podem ser negativos. Produtos do almoxarifado não podem se repetir na mesma ordem.

### VehicleMaintenancePlan

Tabela `vehicle_maintenance_plans` e espelho `data/vehicle_maintenance_plans.json`.

O plano exige intervalo de quilometragem, dias ou ambos. O sistema não preenche intervalos genéricos. Alertas são definidos por plano e devem refletir o manual do veículo ou a regra interna aprovada.

### FleetMaintenanceAttachment

Tabela `fleet_maintenance_attachments` e espelho `data/fleet_maintenance_attachments.json`.

Os arquivos ficam em:

```text
uploads/Frota/Veiculos/PLACA/Manutencoes/OS-FROTA-AAAA-000001/
```

O banco guarda somente metadados e referências. O backup ZIP inclui `uploads/`; o Dropbox recebe apenas a cópia desse ZIP e nunca é banco ativo.

### FleetInventoryReservation

Tabela `fleet_inventory_reservations` e espelho `data/fleet_inventory_reservations.json`.

Estados: `reservada`, `consumida` e `liberada`. A reserva não altera o saldo físico. A conclusão gera a saída definitiva no histórico existente do almoxarifado.

## Migrations

IDs:

- `20260621_01_fleet_service_orders`;
- `20260621_02_fleet_service_order_items`;
- `20260621_03_vehicle_maintenance_plans`;
- `20260621_04_fleet_maintenance_attachments`;
- `20260621_05_fleet_inventory_reservations`.

Validação:

```bash
python3 scripts/migrate_fleet_maintenance.py apply --dry-run
```

Aplicação:

```bash
python3 scripts/migrate_fleet_maintenance.py apply
```

Antes da aplicação é criado snapshot em `backups/migrations/20260621_fleet_maintenance-AAAAMMDD-HHMMSS/`.

## Fluxo da ordem

1. Abertura gera número sequencial e registra o problema.
2. Uma ordem crítica bloqueia o veículo imediatamente.
3. Itens podem ser ajustados antes da aprovação.
4. Aprovação recalcula custos e reserva peças disponíveis.
5. Execução mantém a reserva e registra diagnóstico.
6. Conclusão exige serviço realizado e quilometragem de saída.
7. A conclusão baixa as peças, atualiza veículo, grava `VehicleMileage`, atualiza o plano vinculado e cria auditoria.
8. Liberação exige permissão e ausência de outra ordem crítica aberta.
9. Cancelamento libera reservas sem alterar o saldo físico.

Ordens concluídas não podem ser arquivadas. Outras ordens e todos os itens/planos usam exclusão lógica.

## Custos

O total é calculado por:

```text
peças e materiais + mão de obra + serviços/taxas/outros - desconto
```

Substituir o total calculado exige `fleet.maintenance.costs.manage` e justificativa administrativa. Usuários sem `fleet.maintenance.costs.view` não recebem custos na tela ou nos relatórios exportados.

## Integração com estoque

- O produto é sempre o cadastro existente em `warehouse_items.json`.
- Aprovação ou execução cria reserva sem baixar saldo.
- Conclusão cria movimento `saida frota` com usuário, data, veículo e ordem.
- Cancelamento cria movimento `liberacao reserva frota`.
- Estoque negativo é bloqueado; exceção exige administrador e confirmação explícita.
- As movimentações permanecem no histórico único `warehouse_movements.json`.

## Revisões e alertas

Uma revisão fica vencida quando a data ou a quilometragem atingir primeiro o limite. Os estados apresentados são `em_dia`, `atencao`, `proximo_vencimento`, `vencido`, `em_manutencao` e `concluido`.

Na conclusão de uma ordem vinculada, o plano recebe a última data/km e calcula a próxima data/km somente com os intervalos cadastrados.

## Permissões

- `fleet.maintenance.view`;
- `fleet.maintenance.create`;
- `fleet.maintenance.edit`;
- `fleet.maintenance.approve`;
- `fleet.maintenance.execute`;
- `fleet.maintenance.complete`;
- `fleet.maintenance.cancel`;
- `fleet.maintenance.costs.view`;
- `fleet.maintenance.costs.manage`;
- `fleet.maintenance.release_vehicle`;
- `fleet.maintenance.plans.manage`;
- `fleet.maintenance.inventory.manage`.

O perfil Operacional abre ordens, atualiza itens/execução e usa peças, mas não aprova, conclui, cancela, vê custos ou libera veículos. O Financeiro consulta ordens e custos. O Administrador possui acesso completo. O Flask atual não possui perfil formal de motorista; `driver_id` permanece referência textual/opcional.

## Telas e relatórios

Acesse `/fleet/maintenance` ou use `Frota > Manutenções`.

A tela reúne lista, abertura, detalhe, aprovação, execução, conclusão, planos, próximas revisões, histórico e relatórios iniciais. Os relatórios podem ser exportados pela infraestrutura existente em PDF e Excel; custos são removidos quando o usuário não tem permissão.

## Testes

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache \
python3 -m unittest tests.test_fleet_maintenance

PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache \
python3 -m unittest discover tests
```

Os testes cobrem numeração, custos, aprovação, conclusão, bloqueio, liberação, quilometragem, regressão de km, próxima revisão, baixa, cancelamento, permissões, exclusão lógica, auditoria, migration e rollback.

## Rollback

Com o servidor parado:

```bash
python3 scripts/migrate_fleet_maintenance.py rollback
```

Para escolher um snapshot:

```bash
python3 scripts/migrate_fleet_maintenance.py rollback --snapshot CAMINHO_DO_SNAPSHOT
```

O rollback restaura SQLite, espelhos JSON, veículos e arquivos do almoxarifado exatamente como estavam no snapshot. Anexos enviados depois da migration devem ser avaliados separadamente antes de apagar; a rotina não remove uploads operacionais.

## Limitações conhecidas

- A numeração é protegida por índice único e pelo processo local; uma futura operação com múltiplos servidores deve usar sequência transacional dedicada.
- O sistema híbrido grava SQLite e JSON em etapas; falha física entre essas gravações ainda pode exigir restauração do último backup.
- Não há entidade Flask dedicada de fornecedores ou motoristas; os IDs e nomes permanecem opcionais.
- A interface é responsiva e usa caminhos `pathlib`, mas a validação executada nesta implementação ocorreu no macOS; Windows foi validado por testes e análise estática dos launchers.

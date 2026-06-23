# Frota - Fase 1

Implementação iniciada em 19 de junho de 2026.
Revisão de segurança concluída em 20 de junho de 2026.

## Escopo entregue

- ficha profissional de veículos;
- separação entre proprietário legal, empresa/unidade operacional e centro de custo;
- validação de placa, Renavam e chassi duplicados;
- status operacional da frota;
- fotos organizadas por placa;
- documentos com emissão, vencimento, responsável, status e arquivo;
- alertas configuráveis de vencimento;
- exclusão lógica de veículos e documentos;
- auditoria de criação, edição e arquivamento;
- permissões específicas do módulo;
- persistência híbrida em SQLite com espelho JSON;
- snapshot completo antes da migration e rollback por restauração;
- rollback automático quando uma etapa da migration falha;
- gravação transacional no SQLite, sem deixar tabela parcialmente atualizada;
- preservação do espelho JSON quando a gravação SQLite falhar;
- bloqueio prévio da migration quando placa, Renavam ou chassi duplicados forem encontrados.
- rota protegida `GET /fleet`;
- entidades SQLite `Vehicle`, `VehicleDocument`, `VehicleMileage` e `VehicleAuditLog`;
- permissões básicas `fleet.create`, `fleet.edit`, `fleet.delete` e `fleet.documents.manage`, preservando as permissões granulares existentes.

Manutenções, planos preventivos, custos e integração controlada com almoxarifado foram implementados na Fase 2 e estão documentados em `docs/MODULO_FROTA_MANUTENCAO.md`. Checklists e multas permanecem fora do escopo atual.

## Arquitetura encontrada

O sistema é um monólito Flask com:

- aplicação principal em `app/main.py`;
- interface principal em `app/templates/index.html`;
- autenticação, sessão, perfis e permissões no próprio Flask;
- dados operacionais em `data/*.json`;
- SQLite ativo por configuração, com JSON como espelho de segurança;
- backup local em `backups/` e cópia opcional do ZIP para Dropbox;
- uploads incluídos no backup;
- rotas e módulos extraídos gradualmente em `app/routes/` e `app/services/`.

A Frota segue esse padrão transitório. O banco continua sendo a fonte ativa quando `SANNYGOLD_STORAGE_BACKEND=sqlite`; o Dropbox não é usado como banco.

## Dados

Veículos:

- JSON: `data/vehicles.json`;
- SQLite: tabela `vehicles`;
- identificadores normalizados: `plate_normalized`, `renavam_normalized` e `chassis_normalized`;
- índices únicos no SQLite quando os dados legados não contêm duplicidades;
- `deleted_at` e `deleted_by` para exclusão lógica.

Documentos:

- JSON: `data/fleet_documents.json`;
- SQLite: tabela `fleet_documents`;
- arquivos: `uploads/Frota/Veiculos/PLACA/Documentos/`;
- fotos: `uploads/Frota/Veiculos/PLACA/Fotos/`.

Histórico e auditoria:

- SQLite: tabelas `vehicle_mileage` e `vehicle_audit_logs`;
- a migration cria um marco inicial de quilometragem e um log inicial para cada veículo existente;
- o log operacional global em `data/audit_log.json` continua ativo.

O backup existente inclui `data/` e `uploads/`, portanto inclui banco, espelhos JSON, fotos e documentos da frota.

## Permissões

- `fleet.view`
- `fleet.vehicle.create`
- `fleet.vehicle.edit`
- `fleet.mileage.edit`
- `fleet.checklist.fill`
- `fleet.maintenance.open`
- `fleet.maintenance.approve`
- `fleet.costs.edit`
- `fleet.vehicle.block`
- `fleet.vehicle.release`
- `fleet.documents.view`
- `fleet.values.view`
- `fleet.fines.create`
- `fleet.fines.pay`
- `fleet.admin`

O perfil Operacional não recebe Renavam, chassi, apólice, seguradora, documentos ou valor de aquisição no HTML. O perfil Financeiro pode consultar documentos e valores, mas não administrar o cadastro. O Administrador possui acesso completo.

As permissões são validadas também no backend:

- alteração de quilometragem exige `fleet.mileage.edit`;
- mudança para bloqueado, manutenção ou parado exige `fleet.vehicle.block`;
- retorno de bloqueado, manutenção ou parado para disponível/operação exige `fleet.vehicle.release`;
- venda, baixa ou reativação de veículo arquivado exige `fleet.admin`;
- alteração de Renavam, chassi e dados de seguro exige acesso aos dados documentais;
- alteração do valor de aquisição exige acesso aos valores da frota.

Os índices de busca global e de rotas não incluem Renavam, chassi, apólice, seguradora ou valor de aquisição.

## Migration

### Fundação das entidades

Validação sem alterar dados:

```bash
python3 scripts/migrate_fleet_foundation.py apply --dry-run
```

Aplicação com snapshot:

```bash
python3 scripts/migrate_fleet_foundation.py apply
```

Rollback:

```bash
python3 scripts/migrate_fleet_foundation.py rollback
```

IDs registrados:

- `20260620_01_fleet_vehicle_entity`;
- `20260620_02_fleet_vehicle_documents`;
- `20260620_03_fleet_vehicle_mileage`;
- `20260620_04_fleet_vehicle_audit_logs`.

### Migration anterior da Fase 1

Validação sem alterar dados:

```bash
python3 scripts/migrate_fleet_phase1.py apply --dry-run
```

O relatório informa `can_apply` e lista duplicidades normalizadas em `duplicate_identifiers`. Se houver conflito, a aplicação é bloqueada antes de criar snapshot ou alterar arquivos.

Aplicação:

```bash
python3 scripts/migrate_fleet_phase1.py apply
```

Antes da gravação é criado um snapshot em:

```text
backups/migrations/20260619_01_fleet_phase1-AAAAMMDD-HHMMSS/
```

O snapshot guarda os arquivos que existiam antes da migration, incluindo o SQLite.

Se qualquer gravação falhar depois do snapshot, o rollback é executado automaticamente e um `failure-report.json` é salvo no diretório da tentativa.

Rollback para o último snapshot:

```bash
python3 scripts/migrate_fleet_phase1.py rollback
```

Rollback para um snapshot específico:

```bash
python3 scripts/migrate_fleet_phase1.py rollback \
  --snapshot backups/migrations/20260619_01_fleet_phase1-AAAAMMDD-HHMMSS
```

O rollback restaura os arquivos anteriores exatamente e remove os arquivos que não existiam antes da migration.

## Validação manual

1. Entrar como Administrador.
2. Abrir `Frota`.
3. Cadastrar um veículo com placa, proprietário, empresa responsável e centro de custo.
4. Tentar cadastrar outra placa, Renavam ou chassi igual e confirmar o bloqueio.
5. Anexar um documento com vencimento.
6. Conferir o alerta e abrir o arquivo.
7. Entrar como Operacional e confirmar que dados sensíveis, documentos e valores não aparecem.
8. Arquivar um documento e um veículo e confirmar que continuam no JSON/SQLite com `deleted_at`.
9. Gerar um backup e conferir `data/fleet_documents.json` e `uploads/Frota/` dentro do ZIP.

## Testes

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache \
python3 -m unittest discover tests
```

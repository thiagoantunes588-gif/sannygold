# Mapa de rotas do backend

Snapshot apos a primeira refatoracao incremental.

## Rotas movidas para `app/routes/backup.py`

- `GET /backup/system.zip` -> `download_system_backup`
- `POST /backup/generate` -> `generate_system_backup`
- `POST /backup/dropbox/test` -> `test_dropbox_backup_dir`
- `POST /backup/schedule` -> `update_backup_schedule`
- `GET /backup/latest.zip` -> `download_latest_system_backup`

## Rotas movidas para `app/routes/finance.py`

- `POST /financial/receivables` -> `save_financial_receivable`
- `POST /financial/receivables/generate-monthly` -> `generate_monthly_receivables`
- `POST /financial/receivables/<receivable_id>/payment` -> `update_receivable_payment`
- `GET /financial/receivables/<receivable_id>/receipt.pdf` -> `download_receivable_receipt`
- `POST /financial/entries` -> `save_financial_entry`
- `POST /financial/monthly-closeouts` -> `save_financial_monthly_closeout`
- `GET /financial/monthly-closeouts/<period>.pdf` -> `download_financial_monthly_closeout_pdf`

## Servicos movidos para `app/services/backup.py`

- listagem de arquivos de backup;
- compactacao dos arquivos importantes de `data/`;
- retencao dos ultimos 30 backups;
- montagem do status exibido no painel admin.

## Grupos ainda em `app/main.py`

- tela inicial e status: `/`, `/health`, `/status`, `/system/status.json`;
- assistente de ajuda: `/ajuda`, `/assistente`, `/assistant/*`, `/admin/help/*`;
- autenticacao e usuarios: `/auth/*`, `/account/password`, `/users/*`, convites e redefinicao;
- clientes: `/clients`, importacao, modelo Excel, limpeza e exclusao;
- eventos: `/events`, recorrencia, status, OS/PDF e valor financeiro;
- equipamentos, frota e almoxarifado;
- rotas, validacao operacional, geocode, preview e uploads;
- relatorios gerais: `/reports/*`, `/exports/*`, fechamento diario e semanal;
- configuracoes financeiras e modelos de orcamento.

## Como validar apos mover um grupo

1. Compilar os arquivos Python alterados.
2. Rodar testes focados no grupo movido.
3. Rodar `python3 -m unittest discover tests`.
4. Conferir `app.url_map` para garantir que as URLs e endpoints seguem iguais.
# Frota - Fase 1

- `GET /fleet`: entrada protegida do modulo; exige `fleet.view` e abre a aba Frota.

- `POST /vehicles`: cria ou atualiza veículo.
- `POST /vehicles/<vehicle_id>/delete`: arquiva veículo por exclusão lógica.
- `GET /fleet/maintenance`: lista, detalhe, planos, histórico e relatórios da manutenção.
- `POST /fleet/maintenance/orders`: abre ou edita ordem de serviço.
- `POST /fleet/maintenance/orders/<id>/items`: inclui peça, material ou serviço.
- `POST /fleet/maintenance/orders/<id>/approve`: aprova e reserva estoque.
- `POST /fleet/maintenance/orders/<id>/execute`: inicia ou atualiza execução.
- `POST /fleet/maintenance/orders/<id>/complete`: conclui, baixa estoque e atualiza quilometragem.
- `POST /fleet/maintenance/orders/<id>/cancel`: cancela e libera reservas.
- `POST /fleet/maintenance/vehicles/<id>/release`: libera veículo sem falha crítica aberta.
- `POST /fleet/maintenance/plans`: cria ou edita plano preventivo.
- `POST /fleet/maintenance/orders/<id>/attachments`: salva metadados e arquivo da manutenção.
- `POST /fleet/documents`: cadastra documento e arquivo da frota.
- `POST /fleet/documents/<document_id>/delete`: arquiva documento.
- `POST /fleet/document-alerts`: configura prazos de alerta.
- `GET /uploads/frota/<relative_path>`: entrega foto ou documento conforme permissão.

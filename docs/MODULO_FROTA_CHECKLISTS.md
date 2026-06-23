# Módulo Frota - Fase 3: Checklists e operação

## Escopo

Esta fase adiciona checklists configuráveis de saída, retorno, inspeção, entrega, devolução e manutenção; ocorrências; bloqueios operacionais; liberação formal; responsabilidade por veículo; autorização de motoristas; integração com rotas; fotos; painel e interface responsiva.

Não foram implementados consulta de multas, Detran/Senatran, telemetria, rastreamento em tempo real, abastecimento completo, cálculo de consumo, seguradora, aplicativo nativo ou nova autenticação.

## Entidades

- `fleet_checklist_templates`: modelo lógico, versão, tipo, tipo de veículo e autoria.
- `fleet_checklist_template_items`: itens configuráveis, resposta, criticidade e regras de foto, observação, ocorrência e bloqueio.
- `fleet_checklists`: execução vinculada a veículo, motorista, rota, operação e ordem de serviço.
- `fleet_checklist_responses`: resposta com cópia do título, categoria e criticidade usados na execução.
- `fleet_checklist_evidence`: metadados, caminho, tamanho, tipo e SHA-256 da foto.
- `fleet_occurrences`: relato operacional numerado no padrão `OC-FROTA-AAAA-000001`.
- `vehicle_operational_blocks`: bloqueio e liberação preservados no histórico.
- `fleet_vehicle_assignments`: entrega, devolução e período de responsabilidade do motorista.
- `fleet_driver_authorizations`: associação entre usuário existente, veículos e tipos autorizados. Não é um segundo cadastro de pessoas.

Todas as entidades possuem `deleted_at` quando a exclusão lógica é aplicável. Checklists concluídos, ocorrências e bloqueios não possuem fluxo de exclusão definitiva.

## Migrations

As migrations registradas em `schema_migrations` são:

1. `20260621_11_fleet_checklist_templates`
2. `20260621_12_fleet_checklist_template_items`
3. `20260621_13_fleet_checklists`
4. `20260621_14_fleet_checklist_responses`
5. `20260621_15_fleet_checklist_evidence`
6. `20260621_16_fleet_occurrences`
7. `20260621_17_vehicle_operational_blocks`
8. `20260621_18_fleet_vehicle_assignments`
9. `20260621_19_fleet_driver_authorizations`

O script cria um snapshot em `backups/migrations/`, aplica o schema SQLite, cria os arquivos JSON espelhados, inclui modelos iniciais de saída e retorno e ativa a exigência configurável de checklist em rotas. Não usa Dropbox como banco de dados.

```bash
python3 scripts/migrate_fleet_checklists.py apply --dry-run
python3 scripts/migrate_fleet_checklists.py apply
python3 scripts/migrate_fleet_checklists.py rollback --snapshot backups/migrations/<snapshot>
```

## Modelos e versionamento

O administrador pode criar modelos e itens pela tela `/fleet/checklists`. Alterar um modelo já usado gera uma nova versão e desativa a anterior. A execução mantém `template_id`, `template_version` e snapshots de título, categoria e criticidade, preservando o histórico.

Os modelos podem ser limitados por `vehicle_type`; a tela oculta modelos incompatíveis com o veículo escolhido. As categorias iniciais ficam no catálogo do serviço e os itens permanecem configuráveis no banco.

## Criticidade, ocorrências e bloqueio

- Atenção pode exigir observação e gerar ocorrência conforme o item.
- Não conformidade exige observação nas regras configuradas e foto quando exigida.
- Falha crítica reprova o checklist, cria ocorrência crítica e bloqueio operacional.
- Uma ordem de serviço não é aberta automaticamente. A ocorrência apenas orienta a avaliação.
- Um veículo bloqueado não pode iniciar entrega nem ser aceito em nova rota.

## Liberação

A liberação exige `fleet.vehicle.release`, confirmação de resolução e justificativa. Ela é recusada quando houver outro bloqueio ativo, ocorrência crítica aberta, ordem crítica em execução ou documento obrigatório vencido configurado para bloquear. Bloqueio e liberação permanecem no histórico e na auditoria.

## Quilometragem e concorrência

A conclusão usa transação SQLite com `BEGIN IMMEDIATE`. A saída não aceita valor inferior ao maior valor conhecido; correção exige `fleet.admin` e justificativa. O retorno não aceita valor inferior à saída, calcula a distância, atualiza o veículo e registra `vehicle_mileage` e `vehicle_audit_logs`.

O SQLite é a proteção de concorrência. Os JSON continuam como espelho de compatibilidade durante a arquitetura híbrida atual.

## Entrega e devolução

A saída concluída abre uma responsabilidade com motorista, rota/operação, horário, quilometragem e combustível. Outra entrega para o mesmo veículo é impedida. Uma substituição exige `fleet.route.override` e justificativa, encerra a responsabilidade anterior como substituída e registra auditoria.

O retorno exige uma entrega aberta para o mesmo motorista, encerra a responsabilidade e atualiza a quilometragem. Se houver bloqueio ativo, o retorno é permitido para conferência, mas o veículo permanece bloqueado.

## Integração com rotas

O módulo de rotas existente foi preservado. A integração usa `route_departure_status`, sem importar o gerador de rotas dentro do serviço de Frota.

- O seletor de veículos mostra quilometragem, motorista habitual, manutenção, checklist e entrega aberta.
- Veículos com bloqueio operacional ou manutenção são desabilitados.
- A geração por evento exige checklist de saída concluído quando `fleet_checklist_required_for_routes` está ativo.
- O encerramento do evento é interrompido enquanto existir entrega aberta e orienta o usuário a concluir o checklist de retorno.
- Tipos em `fleet_checklist_route_exception_operation_types` podem ser dispensados por configuração.
- Exceção manual exige `fleet.route.override`, configuração ativa e justificativa; bloqueio crítico não aceita exceção.
- A exceção é auditada por veículo e evento.

Limitação: a geração geral sem evento não possui identificador estável para vincular previamente um checklist e permanece no comportamento legado.

## Integração com motoristas

Usuários ativos são reutilizados. A autorização associa usuário, IDs de veículos e tipos permitidos. Um motorista de perfil leitura autorizado acessa somente veículos atribuídos/autorizados, seus checklists e ocorrências. Custos, documentos societários, configuração administrativa e dados de outros motoristas não são adicionados à tela restrita.

## Fotos

As fotos ficam em:

```text
uploads/Frota/Veiculos/<VEICULO>/Checklists/<ANO>/<CHECKLIST>/<TIPO>/
```

O banco guarda metadados, vínculo, caminho e SHA-256, não o binário. Imagens maiores são reduzidas no navegador para até 1600 px e JPEG com qualidade 82%. O servidor mantém limite e validação de extensão. A câmera e a localização dependem de autorização explícita do navegador.

O Dropbox continua apenas como destino de cópias de backup. O banco ativo e os arquivos de trabalho permanecem no armazenamento local configurado.

## Rascunho e celular

A tela prioriza toque, botões grandes, etapas, progresso, foto pela câmera e layout sem tabelas largas. O rascunho é salvo automaticamente no servidor. Em falha de conexão, somente campos textuais ficam no `localStorage`, sem fotos ou dados binários, e a tela informa que o conteúdo ainda não foi enviado. O rascunho local nunca é apresentado como concluído.

Não foi criada nova PWA, sincronização offline ou aplicativo nativo.

## Permissões

- `fleet.checklist.view`
- `fleet.checklist.create`
- `fleet.checklist.complete`
- `fleet.checklist.cancel`
- `fleet.checklist.templates.manage`
- `fleet.occurrence.view`
- `fleet.occurrence.create`
- `fleet.occurrence.assign`
- `fleet.occurrence.resolve`
- `fleet.vehicle.block`
- `fleet.vehicle.release`
- `fleet.route.override`
- `fleet.audit.view`

Administradores possuem todas. O perfil operacional recebe execução, ocorrências e bloqueio, mas não liberação, modelos ou exceção de rota. Motoristas autorizados usam a regra de atribuição sem ganhar permissões administrativas.

## Auditoria e notificações

Criação, rascunho, conclusão, cancelamento, ocorrência, atribuição, resolução, bloqueio, liberação, substituição de motorista, correção de quilometragem e exceção de rota geram registros. Dados sensíveis continuam filtrados pelo mecanismo central.

As notificações são calculadas na infraestrutura interna existente para checklist reprovado, ocorrência crítica, bloqueio, liberação, retorno pendente ou atrasado e sugestão de ordem de serviço. Não foram criadas integrações com WhatsApp, SMS ou e-mail.

## Testes

`tests/test_fleet_checklists.py` cobre criação e versão de modelo, itens configuráveis, rascunho, conclusão, campos/fotos/observações obrigatórios, falhas, ocorrência, bloqueio, rota, liberação, múltiplos bloqueios, quilometragem transacional, entrega/devolução, motorista, permissão, auditoria, exclusão lógica, migration e rollback.

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest tests.test_fleet_checklists
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest discover tests
```

## Rollback e limitações

Antes da migration, faça backup local completo. O rollback restaura os arquivos e o banco presentes no snapshot. Fotos enviadas depois da migration não fazem parte do snapshot de migration; restaure-as pelo backup geral se necessário.

Limitações conhecidas:

- Persistência ainda é híbrida entre SQLite e JSON por compatibilidade com o monólito.
- Compressão depende de APIs atuais do navegador; arquivos pequenos são enviados sem recompressão.
- Geolocalização pode exigir HTTPS fora de `localhost` e nunca é obrigatória.
- Validação física em Windows deve ser repetida em uma máquina Windows; a implementação usa `pathlib`, caminhos relativos e nomes sem separador fixo.
- Não há consulta oficial de multas, Detran, combustível, telemetria ou rastreamento nesta fase.

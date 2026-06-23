# Analise do Modulo de Frota

Data da analise: 20 de junho de 2026.

## 1. Escopo e decisao tecnica

Esta analise foi realizada antes das alteracoes desta etapa no checkout:

```text
/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna
```

O repositorio contem duas arquiteturas:

1. O sistema operacional atual, em Flask, com SQLite e espelhos JSON locais.
2. Uma linha em `desktop/`, com Electron, Express, Prisma e PostgreSQL, incluindo artefatos `.exe` e `.dmg`.

A Frota desta fase deve continuar no sistema Flask atual. Migrar o modulo para Electron/PostgreSQL agora criaria duas fontes de verdade e aumentaria o risco de perda ou divergencia de dados.

Nao fazem parte desta etapa: manutencoes, checklists, multas, dashboard gerencial, Detran ou credenciais governamentais.

## 2. Arquitetura atual

### Sistema operacional em uso

- Linguagem: Python 3.
- Backend: Flask 3.0.3 e rotas WSGI.
- Servidor local: Waitress no Windows e macOS; Gunicorn permanece disponivel para Unix/servidor.
- Frontend: HTML renderizado com Jinja, Bootstrap e JavaScript em `app/templates/index.html`.
- Persistencia principal: SQLite em `data/sannygold.db` quando o backend SQLite esta ativo.
- Espelho: JSON em `data/` quando `SANNYGOLD_SQLITE_MIRROR_JSON` esta ativo.
- Autenticacao: sessao Flask, hash PBKDF2, expiracao e bloqueio por tentativas.
- Autorizacao: perfis fixos e permissoes em `ROLE_PERMISSIONS`.
- Formularios: protecao CSRF.
- Uploads: arquivos locais em `uploads/`.
- Auditoria: `data/audit_log.json` e tabela SQLite `audit_log`.
- Backup: ZIP local em `backups/`, com copia opcional do ZIP pronto para Dropbox.

### Linha desktop preparada, mas fora desta fase

`desktop/` usa Electron, Node.js, Express, Prisma e PostgreSQL. Ela possui instaladores para Windows e macOS e uma arquitetura de autenticacao e auditoria separada. Exige `DATABASE_URL` e migrations Prisma. Nao deve ser misturada com a Frota Flask/SQLite sem um projeto formal de migracao de plataforma.

### Banco remoto

Nao foi identificado banco remoto ativo no Flask. PostgreSQL aparece na linha `desktop/` e na documentacao de evolucao, mas nao e a fonte atual do sistema Flask. Dropbox nao e banco remoto.

## 3. Estrutura principal de pastas

```text
app/                         aplicacao Flask
app/db/schema.sql            schema SQLite
app/repositories/            acesso SQLite
app/routes/                  rotas extraidas
app/services/                servicos e migrations
app/templates/               interface Jinja
app/static/                  arquivos estaticos e PWA
data/                        SQLite, JSON e relatorios
uploads/                     anexos e fotos
backups/                     backups ZIP e snapshots
scripts/                     inicializacao, migration e backup
tests/                       testes unittest
desktop/                     produto Electron/PostgreSQL separado
mobile/                      cliente Expo em desenvolvimento
installer/                   instaladores e instrucoes
docs/                        documentacao
```

## 4. Arquivos principais

- `app/main.py`: Flask, sessoes, permissoes, dados, rotas legadas e tela principal.
- `app/templates/index.html`: interface principal e menu por abas.
- `app/db/schema.sql`: tabelas SQLite para instalacoes novas.
- `app/repositories/sqlite_repository.py`: inicializacao e escrita SQLite.
- `app/services/sqlite_store.py`: ponte entre SQLite e espelhos JSON.
- `app/services/sqlite_migration.py`: catalogo de fontes JSON e importacao.
- `app/routes/fleet.py`: rotas atuais da Frota.
- `app/services/fleet.py`: normalizacao e validacao de veiculos e documentos.
- `app/services/fleet_migration.py`: migration anterior da Frota.
- `app/services/backup.py`: criacao, validacao e restauracao dos backups.
- `scripts/plan_routes.py`: motor atual de roteirizacao.
- `scripts/start_local.sh`: inicializacao no macOS/Linux.
- `scripts/start_windows.ps1` e `scripts/windows_portable_bootstrap.py`: Windows.

## 5. Modulos existentes e reaproveitamento

### Usuarios

- Dados: `data/users.json` e tabela `users`.
- Fluxos: login, logout, convite, redefinicao e troca de senha em `app/main.py`.
- Reaproveitamento: `current_user`, `has_permission`, `require_permission` e `record_audit`.

### Funcionarios e motoristas

Nao existe entidade dedicada de funcionario no Flask. O motorista habitual e texto dentro do veiculo, e o responsavel pode aparecer no evento ou rota. A linha Electron possui perfil `MOTORISTA`, mas nao e a fonte ativa do Flask.

`usual_driver_id` deve ser opcional nesta fase. A vinculacao formal depende de uma futura entidade de funcionarios/motoristas.

### Rotas

- Motor: `scripts/plan_routes.py`.
- Dados: `data/route_history.json` e `preview/`.
- Integracao: eventos referenciam `vehicle_ids`.
- Restricao: nenhuma regra nova de escala ou bloqueio automatico nesta fase.

### Almoxarifado

- Dados: `warehouse_items.json` e `warehouse_movements.json`.
- Reaproveitamento futuro: movimentacao confirmada de pecas.
- Restricao: nenhuma baixa de estoque sera vinculada a Frota agora.

### Financeiro

- Rotas: `app/routes/finance.py`.
- Dados: recebimentos, lancamentos e fechamentos em JSON e SQLite.
- Reaproveitamento futuro: custos e centro de custo.
- Restricao: nenhum lancamento automatico nesta fase.

### Anexos

- Gerais: `data/attachments.json` e `uploads/assets/`.
- Frota: `uploads/Frota/Veiculos/PLACA/`.
- Reaproveitamento: validacao, limite de tamanho, rota protegida e backup.

### Logs e configuracoes

- Auditoria: `data/audit_log.json` e tabela `audit_log`.
- Logs tecnicos: `logs/`.
- Configuracoes: `data/settings.json`, `.env.local` e `.env.example`.
- Metadados disponiveis: usuario, data, IP, metodo, rota e user-agent.

## 6. Armazenamento atual

| Tipo | Uso | Fonte principal |
| --- | --- | --- |
| SQLite | Dados estruturados | `data/sannygold.db` |
| JSON | Espelho e modulos genericos | `data/*.json` |
| Arquivos locais | Fotos, anexos e PDFs | `uploads/` e `preview/` |
| Dropbox | Copia de backups ZIP | Nunca banco ativo |
| PostgreSQL | Linha Electron preparada | Nao ativo no Flask |
| Banco remoto Flask | Nao identificado | Inexistente nesta configuracao |

O modelo Flask atual e hibrido. As novas tabelas devem preservar compatibilidade com os payloads JSON ate uma migracao completa.

## 7. Windows e macOS

### Windows

- Inicializacao por PowerShell, bootstrap Python ou pacote portatil.
- Waitress usa por padrao a porta 5007.
- Caminhos sao construidos com `pathlib`.
- Banco e uploads ativos devem ficar fora do Dropbox.

### macOS

- Inicializacao por `scripts/start_local.sh`, launcher e opcionalmente LaunchAgent.
- Waitress e usado na operacao local.
- Os `.dmg` Electron pertencem a outra arquitetura.

### Requisitos da migration

- somente Python e SQLite da biblioteca padrao;
- `pathlib` para caminhos;
- nenhum comando exclusivo de Bash ou PowerShell;
- testes em diretorio temporario independente da plataforma.

## 8. Problemas encontrados

1. `app/main.py` e `app/templates/index.html` concentram muitas responsabilidades.
2. Ha duas arquiteturas no repositorio sem migracao concluida entre elas.
3. Nao existe entidade de funcionarios/motoristas no Flask.
4. Parte dos dados estruturados permanece em `payload_json`.
5. Documentos usam nomes legados como `issued_at`, `expires_at` e `responsible`.
6. Nao existem tabelas dedicadas de quilometragem e auditoria de veiculo.
7. A Frota funcional existente e mais ampla que a tela vazia solicitada. Remove-la causaria regressao.
8. O Flask usa perfis fixos; nao ha editor de permissoes arbitrarias por usuario.

## 9. Riscos

### Perda de dados

Risco medio. SQLite e JSON podem divergir se forem gravados separadamente. Mitigacao: transacao SQLite, espelho apos sucesso, snapshot e rollback testado.

### Duplicidade

Risco alto para placa, Renavam e chassi. Mitigacao: normalizacao, pre-validacao e indices unicos parciais.

### Caminhos locais e plataformas

Risco medio. Instalacoes usam pastas diferentes. Mitigacao: `ROTAFLOW_STORAGE_DIR`, `SANNYGOLD_SQLITE_PATH`, `pathlib` e migration Python unica.

### Dropbox

Risco alto se o banco ativo for sincronizado. O sistema ja diagnostica caminhos inseguros. Somente o ZIP pronto deve ser copiado para Dropbox.

### Migrations e backup

Existe infraestrutura, mas faltam as quatro entidades completas. O backup inclui `data/`, `uploads/` e `preview/`. Permanecem os riscos de backup antigo, Dropbox indisponivel e restauracao nao exercitada.

### Permissoes

Risco medio. Toda operacao deve validar permissao no backend, nao apenas ocultar botoes.

### Login

Controles existentes: hash, CSRF, cookies HttpOnly/SameSite, limite de tentativas, expiracao, convite e redefinicao. Riscos restantes: segredo aleatorio quando `SANNYGOLD_SECRET_KEY` nao esta configurado fora de producao, perfis sem escopo por registro e HTTP sem TLS na rede local.

## 10. Dependencias

Nenhuma dependencia nova e necessaria. A fundacao usa Flask ja instalado, SQLite, `pathlib`, `json`, `shutil`, `datetime` e a infraestrutura atual.

Nao serao instalados ORM, SDK Dropbox, biblioteca Detran ou cliente de banco remoto.

## 11. Estrutura de dados recomendada

As entidades serao tabelas SQLite, preservando `vehicle_id` e `document_id` para compatibilidade. Colunas `id` serao aliases unicos.

- `Vehicle`: amplia `vehicles`; identificadores normalizados e `deleted_at`.
- `VehicleDocument`: amplia `fleet_documents`; preserva colunas legadas e usa `deleted_at`.
- `VehicleMileage`: nova tabela `vehicle_mileage`, com linhas imutaveis por veiculo.
- `VehicleAuditLog`: nova tabela `vehicle_audit_logs`, com dados anterior/novo em JSON.

## 12. Migrations necessarias

1. `20260620_01_fleet_vehicle_entity`: amplia `vehicles` e valida indices.
2. `20260620_02_fleet_vehicle_documents`: amplia `fleet_documents`.
3. `20260620_03_fleet_vehicle_mileage`: cria `vehicle_mileage` e marco inicial.
4. `20260620_04_fleet_vehicle_audit_logs`: cria `vehicle_audit_logs` e log inicial.

As quatro migrations serao aplicadas em uma execucao transacional e registradas separadamente em `schema_migrations`.

## 13. Estrategia de rollback

1. Executar `--dry-run` para verificar banco e duplicidades.
2. Criar snapshot em `backups/migrations/20260620_fleet_foundation-AAAAMMDD-HHMMSS/`.
3. Copiar SQLite e JSON relevantes existentes.
4. Aplicar as quatro migrations em transacao.
5. Validar IDs, colunas, indices e tabelas.
6. Em falha, restaurar automaticamente o snapshot.
7. Para rollback manual, restaurar o snapshot com o sistema parado.

O rollback restaura o SQLite anterior; nao tenta desfazer `ALTER TABLE` coluna por coluna.

## 14. Ordem recomendada

1. Manter Flask/SQLite como alvo.
2. Criar GET `/fleet` protegido por `fleet.view`.
3. Registrar as permissoes basicas sem remover as granulares existentes.
4. Ampliar o schema para instalacoes novas.
5. Criar migration transacional e rollback.
6. Adaptar apenas aliases de persistencia necessarios.
7. Testar schema, unicidade, exclusao logica, historico, auditoria e rollback.
8. Rodar regressao completa.
9. Nao iniciar Fase 2 enquanto houver falhas.

## 15. Fases futuras

- Fase 1 atual: fundacao, veiculos, documentos, quilometragem e auditoria.
- Fase 2: manutencoes, planos, custos e anexos tecnicos.
- Fase 3: checklists, bloqueio operacional, rotas e almoxarifado.
- Fase 4: dashboard, indicadores, PDF e Excel.
- Fase 5: multas manuais e preparacao para integracoes oficiais.

Nenhuma fase futura e implementada nesta etapa.

## 16. Comandos de analise e validacao

```bash
git status --short --branch
find app scripts docs tests -maxdepth 2 -type f | sort
rg -n "fleet|vehicles|permissions|backup|Dropbox|warehouse|financial" app scripts tests docs README.md
python3 scripts/migrate_fleet_foundation.py apply --dry-run
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest tests.test_fleet_foundation
PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest discover tests
git diff --check
```

## 17. Como testar manualmente

1. Fechar o SannyGold para evitar escrita concorrente no SQLite.
2. Confirmar que existe backup local recente em `backups/`.
3. Executar `python3 scripts/migrate_fleet_foundation.py apply --dry-run`.
4. Confirmar `can_apply: true` e listas de duplicidade vazias.
5. Executar `python3 scripts/migrate_fleet_foundation.py apply`.
6. Confirmar que o resultado possui `validation.ok: true` e um `snapshot_dir`.
7. Abrir novamente o SannyGold e entrar como Administrador.
8. Abrir `/fleet` e confirmar redirecionamento para a aba `Frota`.
9. Sair da conta, abrir `/fleet` e confirmar que o login e exigido.
10. Conferir no SQLite as tabelas `vehicle_mileage` e `vehicle_audit_logs` e os quatro IDs em `schema_migrations`.
11. Cadastrar um veiculo apenas em ambiente de homologacao e tentar repetir placa, Renavam e chassi.
12. Arquivar o registro e confirmar que ele permanece no banco com `deleted_at`.
13. Para testar rollback, usar primeiro uma copia do banco e executar `python3 scripts/migrate_fleet_foundation.py rollback --snapshot CAMINHO_DO_SNAPSHOT`.

## 18. Arquivos desta etapa

### Criados

- `docs/ANALISE_MODULO_FROTA.md`;
- `app/services/fleet_foundation_migration.py`;
- `scripts/migrate_fleet_foundation.py`;
- `tests/test_fleet_foundation.py`.

### Alterados

- `README.md`;
- `app/db/schema.sql`;
- `app/main.py`;
- `app/repositories/sqlite_repository.py`;
- `app/routes/fleet.py`;
- `app/services/fleet.py`;
- `app/services/sqlite_migration.py`;
- `app/services/sqlite_store.py`;
- `app/templates/index.html`;
- `docs/backend-route-map.md`;
- `docs/frota-fase1.md`;
- `tests/test_fleet_phase1.py`.

O repositorio ja possuia varias alteracoes locais antes desta etapa. Elas foram preservadas e nao foram revertidas.

## 19. Limitacoes restantes

- A migration real nao foi aplicada durante esta etapa porque o servidor local estava aberto. Foi feito `dry-run` somente leitura no banco real e aplicacao/rollback em bancos temporarios.
- `usual_driver_id` permanece opcional porque nao existe entidade de funcionario/motorista no Flask.
- O log global continua sendo a trilha operacional usada pelas rotas atuais; `vehicle_audit_logs` inicia a estrutura dedicada e recebe o marco de migration.
- `vehicle_mileage` recebe o marco inicial; uma tela especifica de lancamento fica para evolucao posterior da Fase 1.
- A validacao Windows foi estatica e por testes de codigo, pois PowerShell nao esta instalado no macOS usado nesta analise.
- A tela de Frota ja era funcional. Ela foi preservada, em vez de ser substituida por uma tela vazia.
- Nenhuma manutencao, checklist, multa, dashboard ou integracao Detran foi criada.

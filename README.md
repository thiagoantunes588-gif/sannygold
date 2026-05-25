# Sistema Geral SannyGold

README tecnico do sistema interno da SannyGold. O objetivo e permitir manutencao, testes, backup e evolucao sem depender de uma unica pessoa.

Caminho oficial do projeto:

```text
/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna
```

## O que o sistema faz

- Cadastro de clientes, eventos/locacoes, banheiros, trailers, climatizadores e pontos de hidratacao.
- Controle de equipamentos, veiculos, rotas, ordens de servico e PDFs operacionais.
- Financeiro basico: contas a receber, recebimentos, lancamentos, recibos e painel gerencial.
- Usuarios por perfil, auditoria, backup local e validacoes antes de gerar documentos.

## Documentacao por publico

- Equipe operacional/financeira: [docs/manual-equipe.md](docs/manual-equipe.md)
- Administradores: [docs/manual-admin.md](docs/manual-admin.md)
- Refatoracao de backend: [docs/backend-route-map.md](docs/backend-route-map.md)
- Migracao JSON para SQLite: [docs/sqlite-migration-plan.md](docs/sqlite-migration-plan.md)

## Instalar localmente

```bash
cd "/Users/thiagoantunes/Documents/Projetos/SannyGold/operacao-interna"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Rodar localmente

Modo recomendado:

```bash
bash scripts/start_local.sh
```

Abra:

```text
http://127.0.0.1:5007
```

Modo manual:

```bash
source .venv/bin/activate
export SANNYGOLD_ENV=local
export SANNYGOLD_SECRET_KEY="$(openssl rand -hex 32)"
export FLASK_DEBUG=0
python3 -m app.main
```

Abra:

```text
http://127.0.0.1:5000
```

## Variaveis de ambiente

Use `.env.example` como referencia, sem colocar senhas reais no repositorio.

Obrigatorias em producao:

- `SANNYGOLD_ENV=production`
- `SANNYGOLD_SECRET_KEY`: chave aleatoria com 32+ caracteres. Gere com `openssl rand -hex 32`.
- `SANNYGOLD_ADMIN_EMAIL`
- `SANNYGOLD_ADMIN_PASSWORD`
- `SANNYGOLD_ADMIN_NAME`
- `ROTAFLOW_STORAGE_DIR`: pasta persistente dos dados, por exemplo `/var/data`.
- `FLASK_DEBUG=0`

Opcionais:

- `SANNYGOLD_SESSION_COOKIE_SECURE=1`: usar quando o acesso for HTTPS e o provedor nao for detectado automaticamente.
- `SANNYGOLD_CSRF_DISABLED=0`: manter `0`; usar outro valor apenas em teste controlado.
- `GOOGLE_MAPS_API_KEY`: melhora geocodificacao quando configurada.
- `SANNYGOLD_APP_VERSION`: identifica a versao no painel/status.

Em producao, a aplicacao nao inicia se a chave secreta estiver ausente, fraca ou se `FLASK_DEBUG` estiver ativo.

## Estrutura de pastas

- `app/main.py`: aplicacao Flask e rotas ainda nao separadas.
- `app/routes/`: rotas extraidas por modulo, como backup e financeiro.
- `app/services/`: servicos reutilizaveis, como backup e migracao.
- `app/repositories/`: camada preparada para SQLite.
- `app/templates/`: telas HTML.
- `app/static/`: imagens e assets fixos.
- `data/`: arquivos JSON locais usados pela versao atual.
- `backups/`: backups `.zip` gerados pelo sistema.
- `preview/`: PDF/JSON da rota mais recente.
- `uploads/`: arquivos enviados pela equipe.
- `docs/`: documentacao de uso, administracao e evolucao.
- `scripts/`: inicializacao, rota, exportacao e migracao.
- `tests/`: testes automatizados.

## Rodar testes

Rodar tudo:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/rotaflow-pycache python3 -m compileall app tests
python3 -m unittest discover tests
```

Rodar apenas os fluxos principais:

```bash
python3 -m unittest tests.test_core_business_flows
```

Os testes usam dados falsos e armazenamento temporario. Nao dependem dos dados reais da empresa.

## Backup

Pelo sistema:

1. Entrar com usuario `admin`.
2. Abrir o painel administrativo/backup.
3. Clicar em `Gerar backup agora`.
4. Baixar o ultimo backup se precisar guardar uma copia fora da maquina.

Pelo endpoint interno autenticado:

- `POST /backup/generate`: gera backup manual.
- `GET /backup/latest.zip`: baixa o ultimo backup.
- `GET /backup/system.zip`: gera e baixa um backup novo.

O backup fica em `backups/` e usa o padrao:

```text
sannygold-data-backup-AAAAMMDD-HHMMSS-xxxxxxxx.zip
```

O sistema mantem os ultimos 30 backups.

## Restaurar backup

Restauracao manual segura:

1. Parar a aplicacao.
2. Fazer uma copia da pasta `data/` atual antes de mexer.
3. Extrair o `.zip` do backup em uma pasta temporaria.
4. Copiar os arquivos de `data/` do backup para a pasta `data/` usada pelo sistema.
5. Subir a aplicacao.
6. Abrir `/health` e conferir clientes, eventos, financeiro e usuarios.

Exemplo local:

```bash
mkdir -p restore-tmp
unzip backups/sannygold-data-backup-ARQUIVO.zip -d restore-tmp
cp restore-tmp/data/*.json data/
python3 -m app.main
```

Em producao, restaure dentro de `ROTAFLOW_STORAGE_DIR`, nao necessariamente na pasta do codigo.

## Migracao JSON para SQLite

A aplicacao ainda usa JSON como armazenamento principal. A infraestrutura SQLite existe para migracao gradual, sem apagar os JSON.

Validar sem gravar:

```bash
python3 scripts/migrate_json_to_sqlite.py --dry-run
```

Gerar/atualizar `data/sannygold.db`:

```bash
python3 scripts/migrate_json_to_sqlite.py
```

Com caminhos explicitos:

```bash
python3 scripts/migrate_json_to_sqlite.py \
  --data-dir data \
  --db data/sannygold.db \
  --report data/migration_reports/sqlite-migration-manual.json
```

O relatorio informa importados, ignorados e erros. Nao ative leitura/escrita SQLite em producao sem uma etapa separada de validacao.

## Regras de manutencao

- Fazer backup antes de mudancas em dados, templates ou migracao.
- Rodar testes antes e depois de alteracoes relevantes.
- Nao versionar senhas, chaves, backups reais, uploads reais ou dados sensiveis.
- Nao mudar URLs publicas ou nomes de templates sem necessidade.
- Preservar compatibilidade dos JSON enquanto a migracao SQLite nao for ativada.

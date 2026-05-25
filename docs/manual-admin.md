# Manual do administrador

Guia curto para quem administra acessos, auditoria, backup, financeiro e pendencias criticas do Sistema Geral SannyGold.

## Responsabilidades do admin

- Manter usuarios e perfis corretos.
- Revisar auditoria quando houver duvida operacional.
- Gerar e baixar backups.
- Acompanhar painel financeiro.
- Conferir pendencias criticas antes de liberar rotina da equipe.
- Evitar que dados sensiveis fiquem expostos.

## Perfis de usuario

- `Admin`: acesso total.
- `Operacional`: Central do Dia, clientes, eventos, rotas, OS, equipamentos e veiculos.
- `Financeiro`: clientes, eventos com valor, contas a receber, recebimentos e relatorios financeiros.
- `Leitura`: consulta dados principais sem editar, excluir ou gerar acoes criticas.

## Criar usuario

1. Entre como admin.
2. Abra `Acessos` ou o painel administrativo.
3. Informe nome, e-mail, perfil e status.
4. Crie senha inicial ou gere convite, conforme o fluxo disponivel.
5. Oriente a pessoa a trocar a senha no primeiro acesso, quando solicitado.

Nao envie senha por canais publicos. Prefira convite ou combinacao segura.

## Alterar perfil

1. Abra `Acessos`.
2. Localize o usuario.
3. Clique em editar.
4. Altere o perfil.
5. Salve.
6. Peca para a pessoa sair e entrar novamente se o menu nao atualizar.

Use o menor acesso necessario. Quem apenas consulta deve ficar como `Leitura`.

## Inativar usuario

1. Abra `Acessos`.
2. Edite o usuario.
3. Altere status para inativo.
4. Salve.

Use isso quando alguem sair da equipe ou nao precisar mais do sistema.

## Consultar auditoria

1. Abra o painel de auditoria.
2. Filtre por usuario, acao, periodo ou entidade.
3. Procure a acao: login, criacao, edicao, exclusao, rota, OS/PDF, financeiro, backup ou acesso negado.
4. Confira antes/depois quando existir.

Use a auditoria para responder perguntas como:

- Quem alterou o valor de uma locacao?
- Quem gerou a rota?
- Quem excluiu um cliente?
- Quem tentou acessar tela sem permissao?

## Gerar backup

1. Abra o painel administrativo de backup.
2. Confira a data do ultimo backup.
3. Clique em `Gerar backup agora`.
4. Baixe o ultimo backup se for fazer manutencao, migracao ou grande alteracao.

Regra pratica:

- backup antes de mexer em dados;
- backup antes de publicar mudancas;
- backup ao final de dias com muita operacao.

## Restaurar backup

Restauracao deve ser feita com cuidado:

1. Pare o sistema.
2. Guarde uma copia da pasta `data/` atual.
3. Extraia o backup `.zip`.
4. Copie os arquivos de `data/` do backup para a pasta de dados usada pelo sistema.
5. Suba o sistema.
6. Valide `/health`, clientes, eventos, financeiro e usuarios.

Se o sistema estiver em producao, confirme o caminho real de `ROTAFLOW_STORAGE_DIR` antes de copiar arquivos.

## Consultar painel financeiro

Admin e financeiro conseguem ver:

- total previsto no mes;
- total recebido no mes;
- aberto;
- vencido;
- vencendo nos proximos 7 dias;
- clientes com maior valor em aberto;
- clientes com atraso;
- eventos sem valor.

Use esse painel para decidir cobrancas prioritarias e revisar eventos sem valor antes de fechar a semana.

## Revisar pendencias criticas

Comece pela `Central do Dia`.

Prioridade alta:

- evento sem endereco;
- evento sem equipamento;
- rota sem veiculo;
- servico sem responsavel;
- cliente sem telefone;
- recebimento vencido;
- equipamento em manutencao vinculado a evento.

Corrija ou delegue antes de gerar rota, OS ou PDF.

## Rotina semanal recomendada

1. Revisar usuarios ativos.
2. Inativar acessos desnecessarios.
3. Conferir auditoria de alteracoes criticas.
4. Gerar backup.
5. Conferir financeiro vencido e sem valor.
6. Revisar eventos dos proximos 7 dias.
7. Conferir equipamentos em manutencao ou retorno pendente.

## Cuidados de seguranca

- Nao compartilhe login.
- Nao registre senha em anotacao dentro do sistema.
- Nao baixe backup em computador compartilhado.
- Nao envie backup por conversa sem necessidade.
- Nao altere `SANNYGOLD_SECRET_KEY` em producao sem planejar, pois usuarios podem precisar entrar novamente.
- Nao ligue `FLASK_DEBUG` em producao.

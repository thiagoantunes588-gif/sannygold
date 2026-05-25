# Manual rapido da equipe

Guia curto para quem usa o Sistema Geral SannyGold no dia a dia da operacao e financeiro.

## Como acessar

1. Abra o endereco informado pelo administrador.
2. Clique em `Entrar`.
3. Use seu e-mail e senha.
4. Se aparecer `Acesso restrito`, seu perfil nao tem permissao para aquela acao.

Perfis comuns:

- `Operacional`: clientes, eventos, rotas, ordens de servico, equipamentos e veiculos.
- `Financeiro`: clientes, valores, contas a receber, recebimentos e relatorios financeiros.
- `Leitura`: consulta, sem criar, excluir ou gerar acoes criticas.

## Central do Dia

Comece por ela. A Central do Dia mostra:

- eventos de hoje;
- proximos 7 dias;
- rotas pendentes;
- ordens de servico pendentes;
- equipamentos reservados, em uso ou com retorno pendente;
- pendencias criticas.

Se aparecer alerta no topo, resolva antes de gerar rota, OS ou PDF.

## Criar cliente

1. Abra `Clientes`.
2. Clique em criar/adicionar cliente.
3. Preencha nome, telefone e endereco completo.
4. Informe o tipo de atendimento: banheiro quimico, trailer, climatizador ou ponto de hidratacao.
5. Informe quantidade, janela de atendimento e observacoes importantes.
6. Salve.

Exemplo: `Cliente Obra Alfa`, telefone do responsavel, endereco com numero, 2 banheiros quimicos, atendimento entre 08:00 e 17:00.

## Criar evento ou locacao

1. Abra `Eventos`.
2. Crie o evento/locacao.
3. Informe nome, data inicial e data final.
4. Vincule o cliente.
5. Vincule veiculo, se ja estiver definido.
6. Informe responsavel interno.
7. Escreva observacoes operacionais: acesso, portaria, horario, contato no local.
8. Informe valor quando o financeiro precisar acompanhar a cobranca.
9. Salve.

Exemplo: `Evento Praia`, 4 banheiros luxo, retirada no dia seguinte, acesso pela entrada de servico.

## Gerar rota

1. Abra `Central do Dia` ou `Validar/Gerar`.
2. Selecione o evento.
3. Clique em validar operacao, se disponivel.
4. Corrija pendencias: endereco, telefone, equipamento, veiculo, responsavel ou quantidade.
5. Clique em gerar rota.
6. Confira o PDF/roteiro antes de enviar para a equipe.

O sistema bloqueia rota com dados incompletos, como evento sem endereco ou cliente sem telefone.

## Gerar ordem de servico ou PDF

1. Abra o evento.
2. Confira cliente, local, data, horario, servico/equipamento e quantidade.
3. Confira observacoes operacionais e responsavel interno.
4. Clique em gerar ordem de servico/PDF.
5. Salve ou imprima o PDF para a equipe.

Se a OS tambem for usada pelo financeiro, informe o valor antes de gerar.

## Lancar recebimento

1. Abra `Financeiro`.
2. Localize `Contas a receber` ou `Recebimentos`.
3. Escolha cliente/evento.
4. Informe valor, vencimento, status e forma de pagamento.
5. Salve.
6. Se o cliente pagou, registre o recebimento para tirar da lista de pendencias.

Exemplo: recebimento via Pix de uma locacao de trailer luxo.

## Consultar pendencias

Use:

- `Central do Dia`: pendencias operacionais urgentes.
- `Eventos`: eventos incompletos ou sem OS.
- `Financeiro`: cobrancas vencidas, vencendo e eventos sem valor.
- `Equipamentos`: itens em manutencao, reservados ou com retorno pendente.
- `Auditoria`: apenas admin consulta historico completo.

## O que nao fazer

- Nao crie cliente duplicado para o mesmo local sem necessidade.
- Nao gere rota antes de corrigir endereco, telefone e equipamento.
- Nao gere OS sem observacao operacional.
- Nao apague cliente, evento ou equipamento sem avisar o administrador.
- Nao use senha de outra pessoa.
- Nao anexe documentos pessoais desnecessarios.
- Nao altere valores financeiros sem alinhamento com o financeiro/admin.

## Erros comuns

`Sessao expirada`

- Entre novamente e repita a acao.

`Acesso restrito`

- Seu perfil nao permite essa acao. Peça ao administrador para revisar seu acesso.

`Rota bloqueada por dados incompletos`

- Leia a lista de itens faltantes e clique no botao de correcao.

`Arquivo invalido`

- Envie apenas o formato aceito. Excel de clientes deve ser `.xlsx`; rota usa `.csv`.

`PDF nao gerou`

- Confira cliente, local, data, horario, servico, quantidade, observacao e responsavel interno.

`Cliente sem telefone`

- Abra o cliente e informe telefone do responsavel no local.

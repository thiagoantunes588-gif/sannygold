# Playbook de entrega do PDF operacional

## Objetivo

Garantir que administrativo e operacional gerem uma rota clara em PDF para repassar ao motorista ou equipe de campo.

## Checklist do administrativo/operacional

- Validar evento, clientes, equipamentos e veículos antes de gerar.
- Gerar a rota apenas quando a validação estiver apta.
- Conferir o PDF gerado com cliente, data, horário, local, contato e telefone.
- Repassar somente o PDF ao motorista ou equipe de campo.
- Manter o acesso ao sistema restrito ao administrativo e operacional.

## Requisitos de dados

- Manter dados de cliente completos para o romaneio: contato, telefone, endereço e equipamento.
- Incluir data inicial, data final e diárias do evento.
- Registrar observações operacionais no evento quando precisarem sair no PDF.

## Resiliência

- Se o motorista não tiver acesso ao sistema, centralizar ajustes no administrativo/operacional.
- Em caso de mudança de rota, gerar novo PDF e substituir a versão enviada anteriormente.
- Usar o histórico e confirmações internas para auditoria após a execução.

## Operação diária

1. Validar a operação no sistema.
2. Gerar a rota.
3. Abrir o PDF operacional.
4. Conferir dados essenciais antes da saída.
5. Repassar o PDF ao motorista ou equipe.
6. Registrar internamente qualquer ajuste ou confirmação de campo.

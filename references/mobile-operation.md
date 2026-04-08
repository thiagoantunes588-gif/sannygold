# Playbook de operação mobile

## Objetivo

Garantir execução de rota no celular com baixa latência, baixa fricção e boa tolerância a conectividade instável.

## Checklist do app de motorista

- Mostrar `next_stop` no topo da tela.
- Exibir botões de ação rápida: `Iniciar`, `Cheguei`, `Concluída`, `Não atendida`.
- Permitir reenvio automático de eventos quando a rede voltar.
- Mostrar progresso de rota: paradas concluídas / totais.
- Exibir ETA da próxima parada com atualização periódica.

## Requisitos de dados

- Consumir JSON com campos mínimos de navegação e execução.
- Manter payload por rota enxuto para reduzir custo de rede móvel.
- Incluir coordenadas em todas as paradas para abrir navegação externa.

## Resiliência

- Implementar fila local de eventos em modo offline.
- Sincronizar eventos por ordem de criação.
- Marcar conflitos de sincronização para auditoria.

## Operação diária

1. Baixar rota antes da saída da base.
2. Confirmar geolocalização ativa e bateria suficiente.
3. Executar paradas em sequência e registrar status.
4. Sincronizar exceções (`unassigned`, não atendidas, atrasos) com o despacho.

# SannySystem - análise UX e redesign operacional

## Diagnóstico

O sistema estava funcional, mas com linguagem visual mais técnica do que operacional. Para equipes de eventos, logística e estrutura, isso cria fricção porque o usuário precisa interpretar estados do sistema antes de agir.

Principais problemas encontrados:

- Dashboard inicial focado em infraestrutura, não na operação do dia.
- Navegação sem agrupamento por intenção de uso.
- Ações críticas como check-in, checklist e conflitos ficavam distantes.
- Cards e tabelas tinham hierarquia visual parecida, reduzindo leitura rápida.
- Formulários exibiam muitos campos no mesmo peso.
- Status de conexão, fila e perfil não estavam integrados ao fluxo principal.
- Mobile herdava colapso do desktop em vez de priorizar ações rápidas.

## Princípios do redesign

- Primeira tela deve responder: o que está acontecendo agora, o que está atrasado e qual ação vem primeiro.
- Ações de campo precisam estar a um clique do dashboard.
- Campos técnicos devem ficar recolhidos quando não forem decisão operacional.
- Status deve ser semântico: verde para OK, amarelo para pendente, vermelho para risco, azul para informação.
- Tabelas devem ser densas, limpas e escaneáveis.
- Cards devem representar unidades de decisão, não decoração.
- Mobile-first significa priorizar check-in, checklist, foto, assinatura e ocorrência antes de relatórios.

## Novo layout padrão

Estrutura:

- Sidebar agrupada por `Operação`, `Cadastros` e `Sistema`.
- Topbar com busca global, conexão, fila de sincronização, perfil e ações de sistema.
- Dashboard operacional como primeira tela.
- Cards de KPI focados em ordens ativas, fila offline, conflitos e Dropbox.
- Linha do tempo de operações em andamento.
- Painel de alertas para riscos imediatos.
- Tabela compacta de ordens de serviço.
- Painel técnico recolhido em `details`, evitando poluição visual.

## Design system

Estilo:

- Fundo escuro elegante.
- Superfícies em carvão, sem excesso de gradientes.
- Acento dourado para ações primárias.
- Verde, amarelo, vermelho e azul para status.
- Bordas sutis.
- Raio máximo de 8px em cards e controles.
- Tipografia compacta, legível e com pesos claros.

Componentes padronizados:

- `metric`: KPI operacional.
- `panel`: bloco de decisão.
- `status-chip`: estado de OS.
- `alert-card`: risco ou aviso.
- `timeline-item`: operação em andamento.
- `table-wrap`: tabela operacional.
- `connection-pill`, `sync-pill`, `role-pill`: contexto global.

## Redução de cliques

Antes:

- Usuário entrava no painel técnico, mudava para sincronização ou operação offline e só então executava ação.

Depois:

- Dashboard já mostra conflitos e fila.
- Atalhos levam direto para check-in, checklist e resolução de conflitos.
- Busca global filtra ordens no painel.
- Status de conexão e fila ficam sempre visíveis.

## Fluxo recomendado para operação

1. Abrir o sistema e olhar o dashboard.
2. Resolver alertas vermelhos primeiro.
3. Sincronizar pendências amarelas.
4. Usar `Check-in rápido` ou `Checklist` para ação em campo.
5. Registrar fotos, assinatura e ocorrências pela tela offline.
6. Conferir conflitos no fim da operação.

## Próximas melhorias recomendadas

- Criar dashboard de frota e estoque com dados reais agregados.
- Adicionar busca global real no backend.
- Criar templates de checklist por tipo de evento.
- Criar modo TV operacional com atualização automática.
- Adicionar permissões por módulo visual.
- Adicionar filtros salvos por perfil.
- Unificar tokens visuais entre desktop e mobile.

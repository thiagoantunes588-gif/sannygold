# Finalização v1.0 - Sistema SannyGold

Este documento organiza os passos finais para transformar a versão local em uma versão pronta para uso real pela equipe.

## 1. Revisão funcional

- Login em modo visitante, admin, operacional, financeiro e leitura.
- Clientes: cadastrar, editar, buscar, filtrar e exportar.
- Eventos: criar, vincular clientes/veículos, validar e finalizar.
- Frota e equipamentos: cadastrar, editar, enviar para manutenção e liberar.
- Almoxarifado: cadastrar material, repor, dar baixa, ajustar quantidade e exportar PDF.
- Financeiro: contas a receber, fluxo de caixa, inadimplência, fechamento mensal e PDF.
- Operação: validar rota, gerar PDF, abrir mapa, repassar material e registrar finalização interna.
- Backup: baixar backup completo e fechamento diário.

## 2. Segurança antes de publicar

- Trocar a senha inicial do admin.
- Definir `SANNYGOLD_SECRET_KEY` forte no ambiente de produção.
- Definir `SANNYGOLD_ADMIN_EMAIL=contato@sannygold.com`, `SANNYGOLD_ADMIN_PASSWORD` e `SANNYGOLD_ADMIN_NAME`.
- Manter `ROTAFLOW_STORAGE_DIR` em um volume persistente.
- Usar HTTPS no domínio final.
- Criar usuários reais com roles corretas.

## 3. Dados iniciais

- Cadastrar veículos reais.
- Cadastrar equipamentos reais.
- Cadastrar materiais do almoxarifado.
- Importar clientes ativos.
- Registrar contas a receber em aberto.
- Registrar saldos iniciais do almoxarifado.

## 4. Rotina operacional

1. Abrir o sistema e entrar com usuário interno.
2. Revisar o Dashboard de Pendências.
3. Criar ou selecionar evento.
4. Validar operação.
5. Gerar rota.
6. Conferir PDF, mapa e links de endereço.
7. Repassar o material para a equipe no formato combinado.
8. Registrar ajustes e finalização interna.
9. Movimentar almoxarifado quando necessário.
10. Registrar financeiro.
11. Baixar fechamento diário.
12. Baixar backup.

## 5. Deploy recomendado

O arquivo `render.yaml` está preparado para Render com:

- serviço Python com Gunicorn
- disco persistente montado em `/var/data`
- `ROTAFLOW_STORAGE_DIR=/var/data`
- variáveis secretas fora do repositório

Antes de publicar, confirme no Render:

- plano com suporte a disco persistente
- domínio e HTTPS
- variáveis secretas configuradas
- backup periódico do disco ou exportação manual recorrente

## 6. Checklist de aceite v1.0

- O sistema abre sem login e não expõe dados sensíveis.
- Admin consegue acessar todos os módulos.
- Operacional não vê financeiro sensível.
- Financeiro acessa contas, fluxo e fechamento.
- Leitura acessa visão sem ações críticas.
- Rotas protegidas não abrem por URL sem login.
- PDFs e Excels são baixados corretamente.
- Backup inclui dados operacionais e financeiros.
- O Assistente Operacional está disponível no próprio sistema para orientar a equipe.
- O endpoint `/health` responde corretamente para deploy e monitoramento.
- O painel mostra versão, ambiente e status geral do sistema.

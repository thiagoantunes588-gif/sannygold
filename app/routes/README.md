# Rotas do backend

Esta pasta concentra handlers HTTP retirados gradualmente de `app/main.py`.

Regra da refatoracao:

- preservar URLs publicas e nomes de endpoint usados por `url_for`;
- registrar rotas em funcoes `register_*_routes(app, deps)`;
- receber dependencias por `deps`, evitando import circular com `app/main.py`;
- mover um grupo por vez, sempre com testes depois.

## Modulos atuais

- `backup.py`: backup manual, download do backup atual e download gerado na hora.
- `finance.py`: contas a receber, baixa de pagamento, recibos, lancamentos e fechamento mensal.

Os demais grupos ainda permanecem em `app/main.py` ate a proxima rodada segura de separacao.

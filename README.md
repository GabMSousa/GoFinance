# SaaS Finance

Sistema web pessoal de controle financeiro, feito com Django + SQLite + Bootstrap 5 + Chart.js.

Uso previsto: uma única pessoa, em servidor Linux interno. Não há cadastro de múltiplos usuários.

## Requisitos

- Python 3.10 ou superior
- pip

## Instalação no Ubuntu/Debian

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_initial_data
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver 0.0.0.0:8000
```

Acesse `http://IP_DO_SERVIDOR:8000`.

Admin: `http://IP_DO_SERVIDOR:8000/admin/`.

Copie `.env.example` para `.env` e altere `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` e `DJANGO_ALLOWED_HOSTS`.

## Login inicial

Defina `DJANGO_ADMIN_PASSWORD` no `.env` e execute `python manage.py seed_initial_data`. O comando cria ou atualiza o administrador `gabriel.sousa` (ou o valor de `DJANGO_ADMIN_USERNAME`) sem gravar a senha no código. Depois, entre em `/login/`.

## Dados iniciais

O comando `seed_initial_data` cria, sem duplicar:



Referências de salário (não calculam líquido novo):



## Regras principais

- Receita aumenta o saldo; despesa reduz o saldo.
- Gasto fixo com `Incluído no cartão = Sim` entra na fatura e não é somado novamente fora do cartão.
- Compra parcelada no cartão gera uma linha por parcela, com valor total, parcela atual, restante, primeira e última.
- Gastos de terceiros entram na fatura; valores recebidos não permanecem como gasto pessoal líquido.
- VR não é salário e não reduz saldo bancário.
- Pagamento dividido: compra de R$ 80 com R$ 50 em VR e R$ 30 no cartão registra o consumo total, reduz o VR em 50 e impacta o saldo em 30.
- Investimentos reduzem o saldo disponível do mês, mas aparecem separados das despesas de consumo.
- Dashboard e Resumo Mensal usam a mesma lógica em `finance/services.py`.
- Contas fixas e assinaturas possuem recorrência, vencimento, status de pagamento e CRUD completo.
- Metas financeiras possuem valor objetivo, progresso, prazo e CRUD completo.
- Compras no cartão usam `Eu` ou `Outro + nome`; o mesmo responsável é propagado para todas as parcelas.
- Pagamento da parcela (`paid/paid_at`) é independente do reembolso (`reimbursed_amount/reimbursed_at`).

## Interface simplificada

O fluxo diário fica concentrado em `Início`: use `+ Adicionar` para Compra, Receita ou Investimento. Cartão, VR e movimentações aparecem em filtros, cards e modais no próprio início. `Configurações` concentra salário, VR mensal, gastos fixos, categorias, pessoas legadas e tema claro/escuro/sistema.

## Backup do SQLite

```bash
cp db.sqlite3 backup_$(date +%Y-%m-%d).sqlite3
```

Com o serviço parado, ou usando uma cópia consistente, preserve o arquivo `db.sqlite3`.

## Importação de fatura Nubank

Para importar compras de uma fatura sem duplicar cobranças recorrentes ou pagamentos recebidos:

```bash
python manage.py import_nubank_csv /caminho/Nubank_2026-10-08.csv --invoice-date 2026-10-01
```

O comando é idempotente, registra parcelas identificadas no título e mantém Seguro Connecta/Spotify como fixos no cartão quando já existem no cadastro.

## Produção com Gunicorn + Nginx + systemd

1. Copie o projeto para `/opt/saas_finance`.
2. Crie o ambiente virtual e instale `requirements.txt`.
3. Configure `.env` com `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY` forte e `DJANGO_ALLOWED_HOSTS` com o IP/hostname.
4. Execute:

```bash
python manage.py migrate
python manage.py seed_initial_data
python manage.py collectstatic --noinput
```

5. Copie `deploy/saas-finance.service` para `/etc/systemd/system/saas-finance.service` e ajuste usuário, IP e chave.
6. Copie `deploy/nginx.conf` para `/etc/nginx/sites-available/saas-finance` e habilite o site.
7. Valide e reinicie:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now saas-finance
sudo nginx -t
sudo systemctl reload nginx
```

## Testes

```bash
python manage.py test
```

# Entrega por etapas

## 1. Criar projeto Django
Arquivos: `manage.py`, `finance_control/settings.py`, `finance_control/urls.py`, `finance_control/wsgi.py`, `finance_control/asgi.py`, `finance/apps.py`, `requirements.txt`.

## 2. Criar models
Arquivo: `finance/models.py`.
Models: `Category`, `Person`, `Transaction`, `FixedExpense`, `CreditCardExpense`, `Investment`, `VRMovement`.

## 3. Criar migrations
Arquivo: `finance/migrations/0001_initial.py`.

## 4. Criar admin
Arquivo: `finance/admin.py`.

## 5. Criar telas
Arquivos em `finance/templates/finance/` e `finance/static/finance/css/app.css`.

## 6. Criar formulários
Arquivo: `finance/forms.py`.
Inclui formulários CRUD, compra parcelada e `+ Novo Gasto` com pagamento dividido usando VR.

## 7. Criar dashboard
Arquivos: `finance/views.py`, `finance/services.py`, `finance/templates/finance/dashboard.html`.

## 8. Criar gráficos
Arquivo: `finance/templates/finance/dashboard.html`.
Gráficos Chart.js: receitas x despesas, categoria, evolução mensal, fixos x variáveis e cartão x fora do cartão.

## 9. Criar filtros
Arquivos: `finance/views.py` e `finance/templates/finance/transaction_list.html`.
Filtros: mês, ano, descrição, categoria, pagamento e responsável.

## 10. Criar deploy
Arquivos: `deploy/financeiro.service`, `deploy/nginx.conf`, `README.md`.
Inclui modo simples com `runserver 0.0.0.0:8000` e modelo de Gunicorn + Nginx.

## Dados iniciais
Comando: `python manage.py seed_initial_data`.
Arquivo: `finance/management/commands/seed_initial_data.py`.

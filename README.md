# GoFinance

Sistema web pessoal de controle financeiro, feito com Django + MariaDB/MySQL + Bootstrap 5 + Chart.js.

**Instalação:** consulte o [Guia de instalação](GUIA_INSTALACAO.md) para configurar Python, MariaDB/MySQL, o administrador, acesso pela rede, migração de dados e importação de CSVs.

Para subir tudo com Docker Compose, copie `.env.docker.example` para `.env` e execute `docker compose up -d --build`. O Compose inicia MariaDB, Gunicorn e Nginx com volumes persistentes. O procedimento completo, incluindo localhost, servidor Linux e Nginx, está no guia.

O sistema possui usuários, perfis e uma área Admin para criar acessos separados. Consulte também a [política de segurança](SECURITY.md): antes de usar uma única base com dados de pessoas diferentes, conclua a migração de isolamento financeiro por usuário.

## Requisitos

- Python 3.10 ou superior
- pip

## MariaDB/MySQL no servidor

Em Debian/Raspberry Pi OS, instale o servidor e as dependências do driver:

```bash
sudo apt update
sudo apt install -y mariadb-server default-libmysqlclient-dev build-essential pkg-config
sudo mysql_secure_installation
```

Crie o banco e o usuário dedicado, alterando a senha antes de executar:

```bash
sudo mysql < deploy/mysql-init.sql
```

No `.env`, use `DJANGO_DB_ENGINE=mysql`, uma senha forte em `MYSQL_PASSWORD` e `DJANGO_DEBUG=0`. Para uma instalação atrás de HTTPS, ative também `DJANGO_SECURE_SSL_REDIRECT=1`, `DJANGO_SESSION_COOKIE_SECURE=1`, `DJANGO_CSRF_COOKIE_SECURE=1` e defina `DJANGO_SECURE_HSTS_SECONDS=31536000`.

Para transferir dados entre servidores, use `mysqldump` e restaure o arquivo SQL em uma base MariaDB/MySQL vazia. O procedimento completo está no [Guia de instalação](GUIA_INSTALACAO.md).

## Login inicial

Defina `DJANGO_ADMIN_PASSWORD` no `.env` e execute `python manage.py seed_initial_data`. O comando cria ou atualiza o administrador `admin` (ou o valor de `DJANGO_ADMIN_USERNAME`) sem gravar a senha no código. Depois, entre em `/login/`.

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

## Backup do MariaDB/MySQL

```bash
mysqldump --single-transaction --routines --triggers -h 127.0.0.1 -P 3306 -u saas_finance -p saas_finance > backup_$(date +%Y-%m-%d).sql
```

No Windows, use `mysqldump.exe` e informe a senha quando solicitado. Preserve também `media/` e o `.env` em local protegido. O procedimento completo de restauração está em [GUIA_INSTALACAO.md](GUIA_INSTALACAO.md).

## Importação de fatura Nubank

Para importar compras de uma fatura sem duplicar cobranças recorrentes ou pagamentos recebidos:

```bash
python manage.py import_nubank_csv /caminho/bank_export.csv
```

O comando é idempotente, registra parcelas identificadas no título e mantém Example Insurance/Spotify como fixos no cartão quando já existem no cadastro.

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

O Nginx inclui headers de hardening e limitação básica de tentativas em `/login/`. Em produção, exponha apenas o Nginx, mantenha Gunicorn ligado em `127.0.0.1`, não publique a porta 3306 e prefira HTTPS com certificado válido.

## Controles de segurança aplicados

- ORM do Django para acesso parametrizado ao banco; não há consultas SQL concatenadas no código da aplicação.
- MySQL/MariaDB com `utf8mb4`, modo estrito e timeout de conexão configurados.
- CSRF, cookies `HttpOnly`, `SameSite=Lax`, `X-Frame-Options`, `nosniff`, `Referrer-Policy` e `Permissions-Policy`.
- CSP configurável, inicialmente em modo `Report-Only` para não quebrar os scripts existentes; após validar a interface, use `DJANGO_CSP_REPORT_ONLY=0`.
- Validadores de senha com mínimo de 12 caracteres.
- Upload CSV limitado a 5 MB, extensão/tipo validados e máximo de 10.000 linhas.
- Rate limit de login no Nginx; para exposição externa, complemente com WAF/fail2ban e HTTPS.

## Testes

```bash
python manage.py test
```

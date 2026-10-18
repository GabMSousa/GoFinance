# Guia de instalação do GoFinance

Este é o procedimento recomendado para instalar o GoFinance em uma máquina Windows ou em um servidor Linux. A instalação oficial usa **MariaDB/MySQL**. O SQLite não deve ser usado em produção ou quando mais de uma pessoa acessará o sistema.

## 1. Requisitos

- Python 3.10 ou superior;
- Git;
- MariaDB ou MySQL 8;
- acesso administrativo à máquina para instalar serviços;
- no servidor Linux: Nginx e systemd.

O projeto usa Django, MariaDB/MySQL, Gunicorn, Nginx e Chart.js. O arquivo `requirements.txt` instala as dependências Python, inclusive o driver `mysqlclient`.

## 2. Baixar o projeto

```bash
git clone https://github.com/GabMSousa/GoFinance.git
cd GoFinance
```

Para instalar exatamente uma versão já validada:

```bash
git checkout ID_DO_COMMIT
```

Não copie o `.env` para o GitHub. Ele contém senhas e configurações específicas da máquina.

## 3. Instalar Python e criar o ambiente

### Windows PowerShell

Instale o Python pelo instalador oficial, marque **Add Python to PATH** e confirme:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se a ativação for bloqueada:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git build-essential pkg-config default-libmysqlclient-dev
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Instalar e preparar MariaDB/MySQL

### Windows

Instale o MariaDB Server ou MySQL Server e deixe o serviço iniciado. Depois, abra o cliente `mariadb` ou `mysql` como administrador e execute o script do projeto:

```powershell
Get-Service MariaDB
mariadb -u root -p < deploy/mysql-init.sql
```

Antes de executar, altere `ALTERE_ESTA_SENHA` em `deploy/mysql-init.sql` para uma senha forte. Não reutilize a senha do administrador do GoFinance.

### Ubuntu/Debian/Raspberry Pi

```bash
sudo apt update
sudo apt install -y mariadb-server default-libmysqlclient-dev build-essential pkg-config
sudo systemctl enable --now mariadb
sudo mariadb-secure-installation
```

Altere a senha no arquivo `deploy/mysql-init.sql` e crie o banco e o usuário dedicado:

```bash
sudo mariadb < deploy/mysql-init.sql
```

O GoFinance usa o banco `saas_finance`, o usuário `saas_finance` e a porta `3306` por padrão. Não exponha a porta 3306 à internet; ela deve aceitar conexões apenas do servidor da aplicação.

## 5. Configurar o `.env`

Copie o modelo:

```powershell
Copy-Item .env.example .env
```

No Linux:

```bash
cp .env.example .env
chmod 600 .env
```

### Máquina local ou rede interna sem HTTPS

Use estes valores no `.env` e troque todas as senhas:

```env
DJANGO_SECRET_KEY=gere-uma-chave-aleatoria-com-mais-de-50-caracteres
DJANGO_DEBUG=1
DJANGO_DB_ENGINE=mysql
MYSQL_DATABASE=saas_finance
MYSQL_USER=saas_finance
MYSQL_PASSWORD=senha-do-usuario-do-banco
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,IP_DA_MAQUINA
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1,http://IP_DA_MAQUINA
DJANGO_ADMIN_USERNAME=gabriel.sousa
DJANGO_ADMIN_PASSWORD=senha-temporaria-forte
DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_SESSION_COOKIE_SECURE=0
DJANGO_CSRF_COOKIE_SECURE=0
```

### Servidor com domínio e HTTPS

No servidor, use `DJANGO_DEBUG=0`, uma chave secreta exclusiva com pelo menos 50 caracteres e apenas os hosts reais:

```env
DJANGO_DEBUG=0
DJANGO_DB_ENGINE=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
DJANGO_ALLOWED_HOSTS=financeiro.exemplo.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://financeiro.exemplo.com
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SECURE_HSTS_SECONDS=31536000
```

Nunca use a senha do banco, a senha do administrador ou a `DJANGO_SECRET_KEY` mostrada em exemplos.

## 6. Criar as tabelas e o administrador inicial

Com o ambiente virtual ativado e o `.env` configurado:

```bash
python manage.py check
python manage.py migrate
python manage.py seed_initial_data
python manage.py collectstatic --noinput
```

O `seed_initial_data` cria o administrador definido por `DJANGO_ADMIN_USERNAME` e os dados iniciais pertencentes a esse usuário. No primeiro acesso, a senha deverá ser trocada.

Abra:

```text
http://localhost:8000/login/
```

Depois do login, a aba **Admin** permite criar usuários, ativar/desativar acessos e resetar senhas. Cada novo usuário começa sem lançamentos, contas, faturas, VR ou investimentos de outra pessoa.

## 7. Iniciar em uma máquina Windows

Para teste ou rede interna:

```powershell
python manage.py runserver 0.0.0.0:8000
```

Também é possível usar `iniciar_sistema.bat`. Acesse `http://IP_DA_MAQUINA:8000/login/` a partir dos outros computadores.

Libere a porta 8000 apenas na rede necessária no Firewall do Windows. Para uso permanente, prefira um servidor Linux com Nginx e HTTPS.

## 8. Instalação em servidor Linux com Gunicorn e Nginx

Exemplo usando `/opt/saas_finance`:

```bash
sudo mkdir -p /opt/saas_finance
sudo chown "$USER":"$USER" /opt/saas_finance
git clone https://github.com/GabMSousa/GoFinance.git /opt/saas_finance
cd /opt/saas_finance
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure `.env`, MariaDB e execute:

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py seed_initial_data
python manage.py collectstatic --noinput
sudo chown -R www-data:www-data /opt/saas_finance
```

Instale os arquivos fornecidos:

```bash
sudo cp deploy/saas-finance.service /etc/systemd/system/saas-finance.service
sudo cp deploy/nginx.conf /etc/nginx/sites-available/saas-finance
sudo ln -s /etc/nginx/sites-available/saas-finance /etc/nginx/sites-enabled/saas-finance
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now saas-finance
sudo systemctl reload nginx
```

Ajuste `server_name` em `deploy/nginx.conf` para o domínio ou IP real. Para HTTPS, configure o certificado antes de ativar o redirecionamento seguro no `.env`.

Verifique o serviço:

```bash
sudo systemctl status saas-finance
sudo journalctl -u saas-finance -n 100 --no-pager
```

## 9. Instalação completa com Docker Compose

Use esta opção quando quiser instalar aplicação, Nginx e MariaDB juntos, sem instalar Python ou MariaDB diretamente no sistema operacional.

### Preparar o Docker

No Windows, instale o Docker Desktop, inicie-o e confirme no PowerShell:

```powershell
docker --version
docker compose version
```

No Ubuntu/Debian, uma instalação simples pelos pacotes da distribuição é:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

Se a distribuição não fornecer `docker-compose-plugin`, instale o Docker Engine e o plugin Compose seguindo a documentação oficial da distribuição antes de continuar.

Na raiz do projeto:

```bash
cp .env.docker.example .env
```

No Windows PowerShell:

```powershell
Copy-Item .env.docker.example .env
```

Edite o `.env` e substitua `DJANGO_SECRET_KEY`, `DJANGO_ADMIN_PASSWORD`, `MYSQL_PASSWORD` e `MARIADB_ROOT_PASSWORD`. Os valores precisam ser diferentes entre si. O `MYSQL_HOST` deve permanecer `db` no Docker.

Valide e suba os três serviços:

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs -f web
```

Abra `http://localhost:8000/login/`. O Nginx do Compose serve os arquivos estáticos, encaminha as requisições para o Gunicorn e limita tentativas de login. O banco, as fotos e os arquivos estáticos ficam em volumes persistentes.

Na primeira inicialização, as migrações são executadas e o administrador definido no `.env` é criado. Em reinicializações posteriores, a senha não é redefinida automaticamente.

Comandos de operação:

```bash
docker compose restart
docker compose logs -f nginx
docker compose stop
docker compose start
docker compose down
```

`docker compose down` preserva os volumes. **Não use `docker compose down -v` sem backup**, pois isso apaga o banco MariaDB, as fotos e os arquivos persistentes.

Para atualizar a versão:

```bash
git pull --ff-only
docker compose up -d --build
docker compose exec web python manage.py check
```

Para expor outra porta HTTP, altere `GOFINANCE_HTTP_PORT` no `.env`. Para HTTPS real, coloque um proxy reverso com certificado na frente do Nginx do Compose e ajuste `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` e os cookies seguros.

## 10. Migrar o banco atual do SQLite para MariaDB/MySQL

Use este procedimento somente para levar os dados atuais para um servidor. Preserve o `db.sqlite3` original até validar tudo no MariaDB.

Na máquina que possui os dados atuais, com o projeto na mesma versão do Git:

```bash
python manage.py migrate
python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 > gofinance-dados.json
```

Se o `.env` já aponta para MySQL, execute o `dumpdata` usando temporariamente um `.env` configurado para SQLite ou defina `DJANGO_DB_ENGINE=sqlite` somente para esse comando.

No servidor MariaDB/MySQL:

```bash
python manage.py migrate
python manage.py loaddata gofinance-dados.json
python manage.py collectstatic --noinput
```

Não execute `seed_initial_data` depois de importar um banco completo sem necessidade; o usuário administrador e os dados já estarão no arquivo exportado. Valide login, contas, faturas, gráficos, VR, investimentos e isolamento entre usuários antes de apagar qualquer cópia.

## 11. CSVs, fotos e outros arquivos pessoais

O GitHub armazena somente o código. Os dados ficam no MariaDB/MySQL e os arquivos enviados ficam em `media/`.

- A importação CSV grava os lançamentos no banco e não arquiva automaticamente o CSV original.
- Guarde os CSVs originais fora do repositório se precisar reprocessá-los.
- Ao migrar de máquina, copie `media/` preservando permissões.
- Não copie o `db.sqlite3` para uma instalação que usa MariaDB/MySQL.

Para importar uma fatura Nubank pelo terminal:

```bash
python manage.py import_nubank_csv /caminho/Nubank_2026-10-08.csv
```

Também é possível importar pela tela **Importar CSV**. A importação é idempotente e não deve duplicar uma fatura já processada.

## 12. Backup e restauração do MariaDB/MySQL

O backup oficial de produção é um dump do MariaDB/MySQL, não uma cópia do SQLite.

### Linux

```bash
mkdir -p backups
mysqldump --single-transaction --routines --triggers -h 127.0.0.1 -P 3306 -u saas_finance -p saas_finance > backups/gofinance-$(date +%Y%m%d-%H%M).sql
```

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
mysqldump.exe --single-transaction --routines --triggers -h 127.0.0.1 -P 3306 -u saas_finance -p saas_finance > "backups\gofinance-$(Get-Date -Format yyyyMMdd-HHmm).sql"
```

Restaure em um banco vazio após confirmar o arquivo:

```bash
mariadb -h 127.0.0.1 -P 3306 -u saas_finance -p saas_finance < backups/gofinance-AAAAmmdd-HHMM.sql
```

Faça backup também de `media/` e do `.env`, mas armazene o `.env` em local protegido. Teste periodicamente uma restauração em uma base separada.

## 13. Atualizar a instalação pelo Git

Faça backup do MariaDB/MySQL e de `media/` antes de atualizar:

```bash
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart saas-finance
```

No Windows, substitua `source .venv/bin/activate` pela ativação do PowerShell e reinicie o `runserver`.

## Problemas comuns

### Erro de conexão com o banco

Confira `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER` e `MYSQL_PASSWORD`. Confirme se MariaDB está ativo e se o usuário possui acesso ao banco `saas_finance`.

### Erro 403 de CSRF

O endereço usado no navegador precisa estar em `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS`. Em HTTPS, use `https://` no valor de `DJANGO_CSRF_TRUSTED_ORIGINS`.

### Usuário ou senha inválidos

Confira `DJANGO_ADMIN_USERNAME` e `DJANGO_ADMIN_PASSWORD`. Para um administrador já existente, use a aba **Admin** para resetar a senha; o usuário deverá trocar a senha temporária no próximo login.

### O sistema abre, mas não aparecem os dados

Confirme que a aplicação está apontando para o mesmo banco MariaDB/MySQL usado na migração e que `python manage.py migrate` foi executado. Não misture um `.env` de SQLite com um `.env` de MariaDB.

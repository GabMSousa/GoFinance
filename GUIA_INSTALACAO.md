# Guia rápido de instalação do GoFinance

Este guia prepara o GoFinance para uso local ou em uma máquina da sua rede.

## 1. O que você precisa

- Windows 10/11 ou Ubuntu/Debian;
- Python 3.10 ou superior;
- Git;
- acesso à rede, se outras pessoas forem usar o sistema.

Para uma instalação simples, use SQLite. O sistema também suporta MySQL/MariaDB para uso com várias pessoas ao mesmo tempo.

## 2. Baixar o projeto

```bash
git clone https://github.com/GabMSousa/GoFinance.git
cd GoFinance
```

Se quiser instalar exatamente uma versão específica, consulte o commit desejado no GitHub e execute:

```bash
git checkout ID_DO_COMMIT
```

## 3. Criar o ambiente Python

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o PowerShell bloquear a ativação, abra o terminal como usuário e execute uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Configurar o `.env`

Copie o exemplo:

```powershell
Copy-Item .env.example .env
```

No Linux:

```bash
cp .env.example .env
```

Abra o arquivo `.env` e, para uma instalação simples com SQLite, use estes valores:

```env
DJANGO_SECRET_KEY=troque-por-uma-chave-grande-e-secreta
DJANGO_DEBUG=1
DJANGO_DB_ENGINE=sqlite
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1

DJANGO_ADMIN_USERNAME=admin
DJANGO_ADMIN_PASSWORD=TroqueEstaSenha123!

DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_SESSION_COOKIE_SECURE=0
DJANGO_CSRF_COOKIE_SECURE=0
```

Use uma senha diferente e forte. O arquivo `.env` não deve ser enviado ao GitHub.

## 5. Criar o banco e o administrador inicial

Com o ambiente virtual ativado:

```bash
python manage.py migrate
python manage.py seed_initial_data
python manage.py collectstatic --noinput
```

O comando `seed_initial_data` cria o administrador definido no `.env`. No primeiro login, ele será direcionado para trocar a senha.

## 6. Iniciar o sistema

### Windows

```powershell
python manage.py runserver 0.0.0.0:8000
```

Ou execute o arquivo `iniciar_sistema.bat`.

### Linux

```bash
python manage.py runserver 0.0.0.0:8000
```

Abra no navegador:

```text
http://127.0.0.1:8000/login/
```

## 7. Permitir acesso de outras máquinas

Descubra o IP da máquina que está executando o GoFinance:

- Windows: `ipconfig`;
- Linux: `hostname -I`.

Se o IP for `192.168.1.50`, ajuste o `.env`:

```env
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1,http://192.168.1.50
```

Reinicie o servidor e acesse de outro computador:

```text
http://192.168.1.50:8000/login/
```

Também pode ser necessário liberar a porta 8000 no Firewall do Windows ou no firewall do Linux.

## 8. Criar usuários para outras pessoas

Entre com o administrador e abra a aba **Admin**. Nela é possível criar usuários com nome de exibição, e-mail e senha.

Os novos usuários trocam a senha no primeiro acesso. A criação de usuários não cria contas, lançamentos, investimentos ou qualquer outro dado financeiro.

O painel oficial do Django também fica em:

```text
http://IP_DO_SERVIDOR:8000/admin/
```

## 9. CSVs, banco e arquivos pessoais

O GitHub armazena o código, não os dados pessoais. Estes arquivos ficam somente na máquina:

- `db.sqlite3`: usuários, contas, lançamentos, investimentos e dados importados dos CSVs;
- `media/`: fotos de perfil e uploads;
- `.env`: senhas, chaves e configurações.

O GoFinance guarda os registros importados do CSV no banco, mas não arquiva automaticamente o arquivo CSV original. Guarde os CSVs originais em uma pasta de backup se precisar deles depois.

## 10. Levar tudo para outro computador

Para copiar exatamente o sistema atual:

1. Pare o servidor antigo.
2. Faça backup de `db.sqlite3`, `media/` e `.env`.
3. No novo computador, clone o projeto e instale as dependências.
4. Copie esses três itens para a pasta do projeto.
5. Execute `python manage.py migrate`.
6. Inicie o servidor.

Ao copiar o `db.sqlite3`, os usuários, o administrador, as contas e os dados importados permanecem iguais. Não execute `seed_initial_data` nessa cópia se não quiser inserir ou atualizar os dados iniciais novamente.

## 11. Backup do SQLite

Com o servidor parado, copie o arquivo do banco:

```powershell
Copy-Item db.sqlite3 "backup-db-$(Get-Date -Format yyyyMMdd-HHmm).sqlite3"
```

No Linux:

```bash
cp db.sqlite3 "backup-db-$(date +%Y%m%d-%H%M).sqlite3"
```

Faça backup também da pasta `media/` e do `.env`, armazenando o `.env` em local protegido.

## 12. Personalizar o sistema

Depois de entrar, o usuário pode ajustar:

- tema claro, escuro ou sistema;
- nome de exibição e foto de perfil;
- categorias, salário e VR;
- contas fixas e assinaturas;
- usuários pela aba Admin, se for administrador.

Para alterações de código, faça commits no Git e, na outra máquina, execute `git pull` antes de reiniciar o sistema.

## Problemas comuns

### “Usuário ou senha inválidos”

Confira `DJANGO_ADMIN_USERNAME` e `DJANGO_ADMIN_PASSWORD` no `.env` e execute novamente:

```bash
python manage.py seed_initial_data
```

### Erro 403 de CSRF

Confirme que o endereço usado no navegador aparece em `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS`. Depois reinicie o servidor e faça `Ctrl + F5`.

### A página não abre de outro computador

Confirme que o servidor foi iniciado com `0.0.0.0:8000`, que o IP está correto e que a porta 8000 está liberada no firewall.

### Quando usar MySQL/MariaDB

Use MySQL/MariaDB quando várias pessoas forem acessar e alterar dados ao mesmo tempo. Nesse caso, configure as variáveis `MYSQL_*` do `.env`, crie o banco e execute `python manage.py migrate`.

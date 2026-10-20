# Segurança do GoFinance

## Estado atual

O projeto possui autenticação Django, proteção CSRF, cookies de sessão protegidos, validação de uploads, limites para requisições, headers de segurança e bloqueio de cache em páginas autenticadas.

Há uma limitação importante antes de liberar a aplicação para várias pessoas: parte dos modelos financeiros legados ainda é global no banco. Lançamentos, contas fixas, metas, faturas, salários, categorias, pessoas e movimentos de VR não têm isolamento completo por usuário em todos os caminhos. Portanto, não use uma única base com dados pessoais de usuários diferentes até a migração de ownership ser implementada e validada.

## Produção

1. Gere uma chave aleatória exclusiva com pelo menos 50 caracteres em `DJANGO_SECRET_KEY`.
2. Mantenha `DJANGO_DEBUG=0`.
3. Configure `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` somente com os endereços reais.
4. Use HTTPS e mantenha `DJANGO_SECURE_SSL_REDIRECT=1`, `DJANGO_SESSION_COOKIE_SECURE=1` e `DJANGO_CSRF_COOKIE_SECURE=1`.
5. Depois de confirmar que todo o acesso é HTTPS, habilite HSTS com `DJANGO_SECURE_HSTS_SECONDS` e avalie `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`.
6. Nunca versione `.env`, `media/`, CSVs ou backups.
7. Faça backup protegido do banco e de `media/`; teste também a restauração.
8. Não exponha a porta do Django diretamente na internet. Use um proxy HTTPS e firewall restrito.

## Conta administrativa

O administrador inicial é criado somente quando `DJANGO_ADMIN_PASSWORD` está definida. Usuários criados pela aba Admin precisam trocar a senha no primeiro acesso. Não reutilize a senha do arquivo `.env` em outros serviços.

## Ao corrigir o isolamento multiusuário

A migração deve atribuir os dados existentes a um usuário escolhido explicitamente, substituir consultas globais por escopos com `request.user`, revisar constraints únicas por usuário e adicionar testes que confirmem que dois usuários não conseguem listar, editar, excluir, exportar ou importar dados um do outro.

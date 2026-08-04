> 🇧🇷 **Português** · [🇬🇧 English](deploy.md)

# Implantação

Como colocar o Rastro no ar num servidor Linux com Docker. Funciona em qualquer
provedor — Hetzner, DigitalOcean, Contabo, Oracle Free Tier, Vultr — porque não
depende de nada específico de nenhum deles.

> **O que este guia não faz por você:** criar a conta no provedor, registrar o
> domínio e pagar a fatura. Isso é seu. O guia cobre tudo a partir do momento em
> que você tem uma máquina e um domínio.

---

## 1. O que você precisa antes

| Item | Mínimo | Observação |
|---|---|---|
| Máquina | 2 vCPU, 2 GB de RAM, 20 GB de disco | O Argon2 usa 64 MiB por verificação de senha; com 1 GB o banco e a API brigam por memória |
| Sistema | Ubuntu 22.04 ou 24.04 | Qualquer Linux com Docker serve |
| Domínio | um subdomínio, ex.: `rastro.seudominio.com.br` | Precisa apontar para o IP **antes** de subir |
| Portas | 80 e 443 abertas | O Let's Encrypt valida pela 80 |
| SMTP | conta em qualquer provedor | Brevo, Resend, Mailgun e Gmail servem |

Custo típico: **US$ 4 a 6 por mês** de VPS. Domínio `.com.br` sai por volta de
R$ 40 ao ano. SMTP tem plano gratuito suficiente para começar.

## 2. Apontar o domínio

No painel de DNS do seu registrador, crie um registro A:

```
rastro    A    <IP-da-sua-maquina>
```

Confira antes de continuar — o Caddy pede o certificado no primeiro start e
falha se o domínio ainda não resolve:

```bash
dig +short rastro.seudominio.com.br
```

Propagação pode levar de minutos a algumas horas.

## 3. Preparar a máquina

```bash
ssh root@<IP>

# Docker
curl -fsSL https://get.docker.com | sh

# Usuário sem privilégio para rodar a aplicação.
# Rodar container como root é desnecessário e amplia o estrago de qualquer falha.
adduser --disabled-password --gecos "" rastro
usermod -aG docker rastro

# Firewall: só SSH e web.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

> **Endureça o SSH.** Desative login por senha (`PasswordAuthentication no` em
> `/etc/ssh/sshd_config`) e use chave. Servidor com senha na porta 22 recebe
> tentativa de invasão em minutos — não é exagero, é o tráfego de fundo da
> internet.

## 4. Instalar a aplicação

```bash
su - rastro
git clone https://github.com/madeiragab/rastro.git /opt/rastro 2>/dev/null || \
  git clone https://github.com/madeiragab/rastro.git ~/rastro
cd ~/rastro

cp .env.production.example .env.production
```

Preencha o `.env.production`. Gere os segredos na própria máquina:

```bash
echo "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
```

Cole os valores no arquivo, junto com `DOMINIO`, `ACME_EMAIL` e os dados de SMTP.

## 5. Subir

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

O primeiro start:

1. sobe o banco e espera ficar saudável;
2. aplica as migrações do Alembic;
3. cria a fazenda de demonstração e a conta inicial;
4. o Caddy pede o certificado ao Let's Encrypt.

Acompanhe:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f
```

**Anote a senha inicial.** Se você deixou `ADMIN_SENHA` vazia, ela aparece no log
uma única vez, no bloco `ACESSO INICIAL`.

Abra `https://rastro.seudominio.com.br` e troque a senha no primeiro acesso.

## 6. Verificar

```bash
D=https://rastro.seudominio.com.br

# Prontidão: responde "pronto" só se o banco estiver alcançável
curl -sS $D/health/pronto

# A API recusa quem não tem credencial
curl -sS -o /dev/null -w "%{http_code}\n" $D/api/animais          # 401

# Cabeçalhos de segurança no HTML principal
curl -sSI $D/ | grep -iE "content-security-policy|strict-transport|x-frame"

# Cookie de sessão com os três atributos
curl -sSI -X POST $D/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"x@x.com","senha":"x"}' | grep -i set-cookie
```

> **Não teste `/docs`.** Ele responde 200 e isso está certo: a documentação
> interativa da API está desligada, mas `/docs` não é rota da API — cai no
> fallback da SPA, como qualquer caminho desconhecido. Quem responde a API é
> `/api/*`. (Este guia mandava checar 404 aqui; estava errado.)

Teste a recuperação de senha de ponta a ponta: peça o link, confirme que o
e-mail chega, redefina. Se não chegar, o SMTP está errado — e você só vai
descobrir isso quando alguém precisar, se não testar agora.

## 6.1. Ensaio antes de ir para o servidor

Dá para rodar a **mesma** configuração de produção na sua máquina antes de
subir. Sem bind mount, sem reload, simulador desligado, nginx no lugar do dev
server — trocando só o certificado (autoridade local) e o SMTP (um coletor que
mostra o e-mail em vez de entregar):

```bash
cp Caddyfile.prod-local.example Caddyfile.prod-local
cp .env.production.example .env.production.local   # ajuste DOMINIO=localhost

docker compose -f docker-compose.prod.yml -f docker-compose.prod-local.yml \
  --env-file .env.production.local -p rastroprod up -d --build
```

App em `https://localhost`, e-mails capturados em `http://localhost:8025`.

Vale o trabalho: descobrir no servidor que o build quebra, a migração falha ou o
e-mail não sai é caro e público.

## 7. Backup

```bash
chmod +x deploy/backup.sh
./deploy/backup.sh

crontab -e
# 0 3 * * * cd ~/rastro && ./deploy/backup.sh >> ~/rastro-backup.log 2>&1
```

**O script guarda o backup na mesma máquina do banco.** Se a máquina se perder,
o backup se perde junto. Copie para fora — `rclone` para um bucket, ou `scp`
para outro servidor.

E restaure uma vez, agora, enquanto não é urgente:

```bash
./deploy/backup.sh --restaurar backups/rastro_2026-08-04_0300.sql.gz
```

Backup nunca restaurado não é backup — é um arquivo.

## 8. Atualizar

```bash
cd ~/rastro
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

As migrações rodam sozinhas na subida. **Faça backup antes de atualizar** quando
a versão nova trouxer migração — Alembic sobe sem drama, mas voltar atrás com
dado real é bem mais chato que restaurar.

---

## O que continua faltando

Isto coloca o produto no ar de forma funcional e razoavelmente segura. Não é
infraestrutura de produção madura:

| Falta | Consequência | Quando resolver |
|---|---|---|
| Servidor único | Máquina cai, produto cai | Quando houver cliente pagante |
| Sem monitoramento | Você descobre que caiu pelo usuário | Já: um Uptime Robot gratuito resolve o básico |
| Segredos em arquivo | Quem tem acesso à máquina lê tudo | Cofre, quando houver mais de uma pessoa com acesso |
| Sem segundo fator | Senha vazada = acesso total | Antes do primeiro cliente pagante |
| Backup no mesmo disco | Perda da máquina leva tudo | Junto com o primeiro dado real |
| Deploy manual | `git pull` no servidor | Quando a frequência incomodar |

A lista completa de lacunas de segurança está em [segurança](seguranca.md).

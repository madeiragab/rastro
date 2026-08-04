> [🇧🇷 Português](implantacao.md) · 🇬🇧 **English**

# Deployment

How to put Rastro online on a Linux server with Docker. Works on any provider —
Hetzner, DigitalOcean, Contabo, Oracle Free Tier, Vultr — because it depends on
nothing specific to any of them.

> **What this guide does not do for you:** create the provider account, register
> the domain, pay the bill. That is yours. The guide covers everything from the
> moment you have a machine and a domain.

---

## 1. Prerequisites

| Item | Minimum | Note |
|---|---|---|
| Machine | 2 vCPU, 2 GB RAM, 20 GB disk | Argon2 uses 64 MiB per password verification; at 1 GB the database and API fight for memory |
| OS | Ubuntu 22.04 or 24.04 | Any Linux with Docker works |
| Domain | a subdomain, e.g. `rastro.yourdomain.com` | Must point at the IP **before** you start |
| Ports | 80 and 443 open | Let's Encrypt validates over 80 |
| SMTP | an account with any provider | Brevo, Resend, Mailgun and Gmail all work |

Typical cost: **US$ 4–6/month** for the VPS. SMTP has a free tier that is plenty
to start with.

## 2. Point the domain

In your registrar's DNS panel, create an A record:

```
rastro    A    <your-machine-IP>
```

Check before continuing — Caddy requests the certificate on first start and
fails if the domain does not resolve yet:

```bash
dig +short rastro.yourdomain.com
```

Propagation can take minutes to hours.

## 3. Prepare the machine

```bash
ssh root@<IP>

# Docker
curl -fsSL https://get.docker.com | sh

# An unprivileged user to run the application.
# Running containers as root is unnecessary and widens the blast radius of any
# failure.
adduser --disabled-password --gecos "" rastro
usermod -aG docker rastro

# Firewall: SSH and web only.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

> **Harden SSH.** Disable password login (`PasswordAuthentication no` in
> `/etc/ssh/sshd_config`) and use a key. A server with password auth on port 22
> gets intrusion attempts within minutes — that is not an exaggeration, it is
> the internet's background traffic.

## 4. Install the application

```bash
su - rastro
git clone https://github.com/madeiragab/rastro.git ~/rastro
cd ~/rastro

cp .env.production.example .env.production
```

Fill in `.env.production`. Generate the secrets on the machine itself:

```bash
echo "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
```

Paste those in, along with `DOMINIO`, `ACME_EMAIL` and your SMTP details.

## 5. Start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

The first start:

1. brings up the database and waits for it to be healthy;
2. applies the Alembic migrations;
3. creates the demo farm and the initial account;
4. Caddy requests the certificate from Let's Encrypt.

Follow along:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f
```

**Write down the initial password.** If you left `ADMIN_SENHA` empty, it appears
in the log exactly once, in the `ACESSO INICIAL` block.

Open `https://rastro.yourdomain.com` and change the password on first login.

## 6. Verify

```bash
# Valid TLS and service up
curl -sS https://rastro.yourdomain.com/health

# Security headers
curl -sSI https://rastro.yourdomain.com/ | grep -iE "strict-transport|x-frame|x-content"

# Interactive docs MUST be off in production
curl -sS -o /dev/null -w "%{http_code}\n" https://rastro.yourdomain.com/docs   # 404
```

Test password recovery end to end: request the link, confirm the email arrives,
reset. If it does not arrive, SMTP is misconfigured — and you will only find out
when someone actually needs it, unless you test now.

## 7. Backups

```bash
chmod +x deploy/backup.sh
./deploy/backup.sh

crontab -e
# 0 3 * * * cd ~/rastro && ./deploy/backup.sh >> ~/rastro-backup.log 2>&1
```

**The script stores backups on the same machine as the database.** If the machine
is lost, the backups go with it. Copy them off — `rclone` to a bucket, or `scp`
to another server.

And restore once, now, while it is not urgent:

```bash
./deploy/backup.sh --restaurar backups/rastro_2026-08-04_0300.sql.gz
```

A backup never restored is not a backup — it is a file.

## 8. Updating

```bash
cd ~/rastro
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Migrations run automatically on start. **Back up before updating** when a release
carries a migration — Alembic goes forward cleanly, but rolling back with real
data is considerably more painful than restoring.

---

## What is still missing

This gets the product online in a functional and reasonably secure way. It is
not mature production infrastructure:

| Gap | Consequence | When to fix |
|---|---|---|
| Single server | Machine down, product down | When there is a paying customer |
| No monitoring | You learn it is down from a user | Now: a free Uptime Robot covers the basics |
| Secrets in a file | Anyone with machine access reads everything | A vault, once more than one person has access |
| No second factor | Leaked password means full access | Before the first paying customer |
| Backups on the same disk | Losing the machine loses everything | Alongside the first real data |
| Manual deploys | `git pull` on the server | When the frequency starts to hurt |

The full list of security gaps is in [security](security.md).

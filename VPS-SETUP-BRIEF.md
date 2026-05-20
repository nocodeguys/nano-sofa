# VPS Setup Brief — Nano Sofa dual deployment

> **For**: Claude Code session on the VPS
> **Goal**: Two apps under one domain, each on its own subdomain, with HTTPS via Let's Encrypt.

## Overview

| App | Subdomain | Docker image | Internal port | Compose file |
|-----|-----------|-------------|---------------|-------------|
| Main studio | `sofa.testonix.pl` | `ghcr.io/nocodeguys/nano-sofa:latest` | 7861 | `docker-compose.yml` |
| WebGL 3D experiment | `3d.testonix.pl` | `ghcr.io/nocodeguys/nano-sofa:webgl` | 7862 | `docker-compose.webgl.yml` |

DNS is handled by Hostinger panel (user will create A records for both subdomains pointing to VPS IP).

## Pre-requisites (check first)

- Docker and Docker Compose installed
- Nginx installed (`apt install nginx` if missing)
- Certbot installed (`apt install certbot python3-certbot-nginx` if missing)
- Ports 80 and 443 open in firewall (`ufw allow 80 && ufw allow 443`)
- Both subdomains (`sofa.testonix.pl`, `3d.testonix.pl`) resolving to this VPS IP (verify with `dig +short sofa.testonix.pl` and `dig +short 3d.testonix.pl`)

## Step 1 — Clone repo and start both Docker apps

```bash
# Clone (or pull if already cloned)
cd /opt
git clone https://github.com/nocodeguys/nano-sofa.git nano-sofa || (cd nano-sofa && git pull)
cd /opt/nano-sofa

# Pull and start the main app (port 7861)
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d

# Pull and start the WebGL experiment (port 7862)
docker compose -f docker-compose.webgl.yml pull
docker compose -f docker-compose.webgl.yml up -d

# Verify both are healthy
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.webgl.yml ps
curl -s http://localhost:7861/healthz
curl -s http://localhost:7862/healthz
```

## Step 2 — Nginx reverse proxy

Create two server blocks. Each proxies a subdomain to the corresponding Docker container on localhost.

### `/etc/nginx/sites-available/sofa.testonix.pl`

```nginx
server {
    listen 80;
    server_name sofa.testonix.pl;

    location / {
        proxy_pass http://127.0.0.1:7861;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (needed if live reload is ever added)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Allow large image uploads (base photos, references)
        client_max_body_size 50M;
    }
}
```

### `/etc/nginx/sites-available/3d.testonix.pl`

```nginx
server {
    listen 80;
    server_name 3d.testonix.pl;

    location / {
        proxy_pass http://127.0.0.1:7862;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        client_max_body_size 50M;
    }
}
```

### Enable both sites

```bash
ln -sf /etc/nginx/sites-available/sofa.testonix.pl /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/3d.testonix.pl /etc/nginx/sites-enabled/

# Remove default site if it exists (it catches all traffic otherwise)
rm -f /etc/nginx/sites-enabled/default

# Test config and reload
nginx -t && systemctl reload nginx
```

## Step 3 — SSL with Let's Encrypt (Certbot)

```bash
# Get certs for both subdomains in one command
certbot --nginx -d sofa.testonix.pl -d 3d.testonix.pl --non-interactive --agree-tos -m maciej@mstudio.digital

# Certbot auto-modifies the nginx configs to add SSL blocks and redirects.
# Verify:
nginx -t && systemctl reload nginx
```

After this, both sites should be live at `https://sofa.testonix.pl` and `https://3d.testonix.pl`.

Certbot auto-renews via a systemd timer. Verify it exists:
```bash
systemctl list-timers | grep certbot
```

## Step 4 — Verify everything works

```bash
# HTTPS should return 200
curl -sI https://sofa.testonix.pl | head -5
curl -sI https://3d.testonix.pl | head -5

# Health checks through nginx
curl -s https://sofa.testonix.pl/healthz
curl -s https://3d.testonix.pl/healthz
```

## Step 5 — Block direct port access (optional, recommended)

Close ports 7861 and 7862 from the outside so traffic only flows through Nginx:

```bash
ufw deny 7861
ufw deny 7862
```

## Auto-updates

Both compose files have Watchtower enabled. When CI pushes a new `:latest` or `:webgl` image to GHCR, Watchtower (running inside each compose stack) will detect it within 5 minutes and auto-update the container. No manual action needed after initial setup.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `502 Bad Gateway` | Docker container not running. Check `docker compose -f <file> ps` and `docker compose -f <file> logs` |
| DNS not resolving | Wait for Hostinger DNS propagation (up to 15 min). Check with `dig +short sofa.testonix.pl` |
| Certbot fails | DNS must resolve first. Run certbot after confirming `dig` returns the VPS IP |
| Port conflict | Check nothing else uses 7861/7862: `ss -tlnp | grep 786` |
| Upload too large | `client_max_body_size` in nginx config — increase if needed |
| GHCR pull auth error | The repo/packages must be public, or `docker login ghcr.io` with a PAT |

## File layout on VPS after setup

```
/opt/nano-sofa/
├── docker-compose.yml          # main app → :7861
├── docker-compose.webgl.yml    # WebGL app → :7862
├── outputs/                    # main app generated images
└── outputs-webgl/              # WebGL app generated images

/etc/nginx/sites-available/
├── sofa.testonix.pl            # → 127.0.0.1:7861
└── 3d.testonix.pl              # → 127.0.0.1:7862

/etc/letsencrypt/live/
├── sofa.testonix.pl/           # SSL cert + key
└── 3d.testonix.pl/             # SSL cert + key (or combined)
```

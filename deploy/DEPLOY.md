# AWS Deployment Guide – Woodfamily AI

Deploy Woody (Telegram bot) + Dashboard to AWS. Two main options:

1. **EC2 + Docker Compose** (recommended for getting started)
2. **ECS Fargate** (scalable, no server management)

---

## Prerequisites

- AWS account
- Domain (e.g. woodfamily.ai) with Route53 or external DNS
- SSL certificate (AWS ACM) for HTTPS
- Secrets: Telegram token, OpenAI key, Google/Yahoo OAuth credentials

---

## Option A: EC2 + Docker Compose

### 1. Launch EC2 instance

- **AMI**: Amazon Linux 2023 or Ubuntu 22.04
- **Instance type**: t3.small or t3.medium (2 vCPU, 4 GB RAM)
- **Storage**: 20–30 GB gp3 (or add separate EBS for data)
- **Security group**: Allow 22 (SSH), 80 (HTTP), 443 (HTTPS)
- **IAM**: Instance role with ECR pull (if using ECR) and Secrets Manager read (optional)

### 2. Install Docker

```bash
# Amazon Linux 2023
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Ubuntu
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker ubuntu
```

Log out and back in for group changes.

### 3. Clone and configure

```bash
git clone <your-repo> woodfamily-ai
cd woodfamily-ai
```

### 4. Create production env file

```bash
cp .env.example .env
# Edit .env with real values - NEVER commit .env
```

**Required for production:**

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_CLIENT_ID` | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Google OAuth |
| `GOOGLE_REDIRECT_URI` | `https://woodfamily.ai/api/integrations/google/callback` |
| `YAHOO_CLIENT_ID` | Yahoo OAuth (if used) |
| `YAHOO_CLIENT_SECRET` | Yahoo OAuth |
| `YAHOO_REDIRECT_URI` | `https://woodfamily.ai/api/integrations/yahoo/callback` |
| `DASHBOARD_URL` | `https://woodfamily.ai` |
| `DASHBOARD_USER` | Basic auth username (or use Google Auth) |
| `DASHBOARD_PASSWORD` | Basic auth password |
| `SESSION_SECRET` | For Google Auth: random string (e.g. `openssl rand -hex 32`) |
| `CALENDAR_TIMEZONE` | e.g. `America/Los_Angeles` |

### 5. Update OAuth redirect URIs

In **Google Cloud Console** → APIs & Services → Credentials → your OAuth client:

- Add authorized redirect URIs: `https://woodfamily.ai/api/integrations/google/callback`, `https://woodfamily.ai/api/auth/google/callback`
- Add authorized JavaScript origin: `https://woodfamily.ai`

In **Yahoo Developer** (if used):

- Add redirect URI: `https://woodfamily.ai/api/integrations/yahoo/callback`

### 6. (Optional) Migrate existing data

If you have local `.google_tokens.json`, `.yahoo_tokens.json`, or DBs to migrate:

```bash
chmod +x deploy/scripts/init-data-volume.sh
./deploy/scripts/init-data-volume.sh
```

This copies tokens and DBs into the Docker volume. Run before first `up`, or reconnect Google/Yahoo in the dashboard after deploy.

### 7. Run with production compose

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 8. HTTPS with Nginx (reverse proxy)

Install Nginx and Certbot:

```bash
sudo yum install -y nginx certbot python3-certbot-nginx   # Amazon Linux
# or
sudo apt install -y nginx certbot python3-certbot-nginx   # Ubuntu
```

Configure Nginx to proxy to `localhost:8000` (dashboard) and obtain SSL:

```bash
sudo certbot --nginx -d woodfamily.ai
```

Example Nginx config (`/etc/nginx/conf.d/woodfamily.conf`):

```nginx
server {
    listen 80;
    server_name woodfamily.ai;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name woodfamily.ai;
    ssl_certificate /etc/letsencrypt/live/woodfamily.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/woodfamily.ai/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 9. Data persistence

`docker-compose.prod.yml` uses a named volume `app_data` mounted at `/data` for both services. Data survives container restarts.

**Directory structure in volume:**
- `/data/woody/app.db` – Woody DB
- `/data/dashboard/dashboard.db` – Dashboard DB
- `/data/chroma_db/` – ChromaDB (memories)
- `/data/.google_tokens.json` – Google OAuth tokens
- `/data/.yahoo_tokens.json` – Yahoo OAuth tokens

**Migrating from local:** Copy `.google_tokens.json` and `.yahoo_tokens.json` into the volume before first run, or reconnect Google/Yahoo in the dashboard after deploy.

**Backup:**
```bash
# Volume name = <project>_app_data (project = directory name)
docker run --rm -v woodfamily-ai-v2_app_data:/data -v $(pwd):/backup alpine tar czf /backup/woodfamily-backup-$(date +%Y%m%d).tar.gz -C /data .
```

---

## Option B: ECS Fargate

For a managed, scalable setup:

1. **Push images to ECR**
2. **Create EFS** for persistent storage (SQLite, ChromaDB, tokens)
3. **Task definitions** for woody and dashboard
4. **ALB** with ACM certificate for HTTPS
5. **Secrets** in Secrets Manager, referenced in task definitions

See `deploy/ecs/` for task definition examples (create if needed).

---

## Health checks

- **Woody**: `http://localhost:9000/health`
- **Dashboard**: `http://localhost:8000/health`

---

## Troubleshooting

| Issue | Fix |
|------|-----|
| OAuth "redirect_uri_mismatch" | Ensure Google/Yahoo redirect URIs exactly match (https, no trailing slash) |
| Woody can't reach dashboard | Set `DASHBOARD_URL` to internal URL if same host, or public URL |
| SQLite "database is locked" | Woody and dashboard share woody DB; ensure only one writer. Consider moving to RDS for high concurrency |
| ChromaDB errors | Ensure `chroma_db/` volume is writable |

---

## Security checklist

- [ ] `.env` is in `.gitignore` and never committed
- [ ] `DASHBOARD_USER` and `DASHBOARD_PASSWORD` are set
- [ ] OAuth redirect URIs use HTTPS
- [ ] Security group allows only 22, 80, 443 (no 8000/9000 from internet)
- [ ] Consider AWS Secrets Manager for production secrets

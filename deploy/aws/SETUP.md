# AWS Setup – Woodfamily AI

End-to-end setup to get Woody + Dashboard running on EC2 with automated deploys from GitHub.

---

## Overview

1. **Create EC2 instance** (key pair, security group, launch)
2. **Bootstrap** (Docker, clone repo, .env)
3. **Configure GitHub secrets** (for deploy workflow)
4. **First deploy** (manual or via merge)
5. **Optional**: Domain + HTTPS with Nginx + Certbot

---

## Prerequisites

- AWS account
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and configured (`aws configure`)
- Your production secrets ready (Telegram token, OpenAI key, Google OAuth, etc.)

---

## Step 1: Launch EC2

### Option A: AWS CLI (recommended)

```bash
cd deploy/aws
chmod +x launch-ec2.sh
./launch-ec2.sh
```

Follow the prompts. The script creates a key pair, security group, and EC2 instance. **Save the private key** it outputs – you need it for SSH and GitHub.

### Option B: AWS Console

1. **EC2 → Key Pairs → Create key pair**
   - Name: `woodfamily-deploy`
   - Format: `.pem` (for SSH)
   - Save the `.pem` file

2. **EC2 → Security Groups → Create**
   - Name: `woodfamily-sg`
   - Inbound: SSH (22), HTTP (80), HTTPS (443) from your IP or `0.0.0.0/0` (less secure)

3. **EC2 → Launch Instance**
   - Name: `woodfamily-ai`
   - AMI: Amazon Linux 2023
   - Instance type: t3.small
   - Key pair: `woodfamily-deploy`
   - Security group: `woodfamily-sg`
   - Storage: 20 GB gp3
   - **Advanced → User data**: Paste contents of `ec2-user-data.sh`

4. **Launch**, then note the **Public IPv4 address**.

---

## Step 2: Bootstrap (first-time setup on EC2)

SSH into the instance:

```bash
ssh -i woodfamily-deploy.pem ec2-user@<PUBLIC_IP>
```

If the launch script created the instance, Docker and the repo may already be set up. Otherwise, run:

```bash
# Install Docker (Amazon Linux 2023)
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Install Docker Compose plugin
sudo yum install -y docker-compose-plugin

# Clone repo
git clone https://github.com/jackwood1/woodfamily-ai-v2.git
cd woodfamily-ai-v2

# Create .env from template
cp .env.example .env
```

Edit `.env` with your production values (see [deploy/DEPLOY.md](../DEPLOY.md)). Then:

```bash
# Log out and back in for docker group, or:
newgrp docker

# First deploy
docker compose -f docker-compose.prod.yml up -d
```

Verify:

```bash
curl http://localhost:8000/health
curl http://localhost:9000/health
```

---

## Step 3: GitHub secrets for deploy workflow

In **GitHub → Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | EC2 public IP or hostname |
| `DEPLOY_USER` | `ec2-user` |
| `DEPLOY_SSH_KEY` | Contents of your `.pem` file (the full private key) |
| `DEPLOY_REPO_PATH` | `~/woodfamily-ai-v2` (or leave empty for default) |

To copy the private key:

```bash
cat woodfamily-deploy.pem
# Paste entire output into DEPLOY_SSH_KEY
```

---

## Step 4: Test automated deploy

1. Make a small change (e.g. edit README)
2. Push to `main` (or merge a PR)
3. Check **Actions** tab – the Deploy workflow should run
4. Verify the app is updated on your EC2 instance

---

## Step 5: Domain + HTTPS (optional)

When you have a domain (e.g. woodfamily.ai):

1. **Point DNS** – Create an A record for your domain → EC2 public IP

2. **Install Nginx + Certbot** on EC2:

```bash
sudo yum install -y nginx certbot python3-certbot-nginx
sudo systemctl enable nginx
```

3. **Get SSL certificate**:

```bash
sudo certbot --nginx -d your-domain.com
```

4. **Update .env** – Set `DASHBOARD_URL`, `GOOGLE_REDIRECT_URI`, etc. to `https://your-domain.com/...`

5. **Update Google OAuth** – Add `https://your-domain.com/api/auth/google/callback` to redirect URIs

6. **Restart**:

```bash
cd ~/woodfamily-ai-v2
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

---

## Private repo

If the repo is private, create a **deploy key**:

```bash
ssh-keygen -t ed25519 -C "deploy" -f woodfamily-deploy-key -N ""
```

- Add `woodfamily-deploy-key.pub` to GitHub: **Settings → Deploy keys → Add**
- Use `woodfamily-deploy-key` (private) as `DEPLOY_SSH_KEY` in GitHub Actions
- On EC2, add the deploy key to `~/.ssh/` and configure `~/.ssh/config` for SSH to GitHub

Or use a **Personal Access Token** with `repo` scope for HTTPS clone (store in GitHub secrets, use in user data).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| SSH "Permission denied" | `chmod 600 your-key.pem`; ensure correct user (`ec2-user` for Amazon Linux) |
| Deploy workflow fails | Check DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY; verify EC2 security group allows SSH from GitHub IPs |
| Docker "permission denied" | Run `newgrp docker` or log out and back in after `usermod -aG docker` |
| Port 8000 not reachable | Use Nginx to proxy; don't expose 8000/9000 directly to the internet |

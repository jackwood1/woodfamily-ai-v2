# Deploy Agent

The Deploy workflow runs automatically when code is merged to `main`. It SSHs to your EC2 instance and runs `git pull` + `docker compose up`.

## Setup

### 0. First-time AWS setup

If you don't have EC2 yet, follow [deploy/aws/SETUP.md](../deploy/aws/SETUP.md) to launch an instance and bootstrap it.

### 1. One-time EC2 setup

On your EC2 instance:

```bash
# Clone the repo (if not already)
git clone https://github.com/jackwood1/woodfamily-ai-v2.git
cd woodfamily-ai-v2

# Configure .env (see deploy/DEPLOY.md)
cp .env.example .env
# Edit .env with production values

# Ensure Docker is running
sudo systemctl start docker
```

### 2. GitHub secrets

Add these in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | EC2 hostname or IP (e.g. `ec2-xx-xx-xx-xx.compute.amazonaws.com`) |
| `DEPLOY_USER` | SSH user (`ec2-user` for Amazon Linux, `ubuntu` for Ubuntu) |
| `DEPLOY_SSH_KEY` | Private SSH key for EC2 (contents of `~/.ssh/id_rsa` or your deploy key) |
| `DEPLOY_REPO_PATH` | *(Optional)* Repo path on server. Default: `~/woodfamily-ai-v2` |

### 3. SSH key setup

Generate a deploy key or use your existing key:

```bash
# On your machine – copy the private key
cat ~/.ssh/your-deploy-key
# Paste into DEPLOY_SSH_KEY secret
```

Ensure the public key is in `~/.ssh/authorized_keys` on the EC2 instance.

## Behavior

- **Trigger**: Push to `main` (skips if only `.md` or `.github/` files changed)
- **Actions**: SSH → `git pull` → `docker compose -f docker-compose.prod.yml build` → `docker compose up -d`
- **Health check**: Verifies dashboard (8000) and Woody (9000) after deploy

## Manual deploy

To deploy without merging, run on the EC2 instance:

```bash
cd ~/woodfamily-ai-v2  # or your DEPLOY_REPO_PATH
./deploy/scripts/deploy.sh
```

#!/bin/bash
# EC2 user data – runs on first boot (Amazon Linux 2023)
# Installs Docker, clones repo, prepares for first deploy.
# You must still: edit .env, run docker compose up

set -e
exec > >(tee /var/log/user-data.log) 2>&1

echo "==> Installing Docker..."
yum update -y
yum install -y docker docker-compose-plugin
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

echo "==> Cloning repo..."
su - ec2-user -c "git clone https://github.com/jackwood1/woodfamily-ai-v2.git ~/woodfamily-ai-v2"

echo "==> Creating .env template..."
su - ec2-user -c "cp ~/woodfamily-ai-v2/.env.example ~/woodfamily-ai-v2/.env"

echo "==> Bootstrap complete. Next: SSH in, edit ~/woodfamily-ai-v2/.env, then run:"
echo "    cd ~/woodfamily-ai-v2 && docker compose -f docker-compose.prod.yml up -d"

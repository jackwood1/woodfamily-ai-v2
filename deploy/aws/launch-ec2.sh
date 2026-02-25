#!/bin/bash
# Launch EC2 instance for Woodfamily AI
# Prerequisites: AWS CLI configured (aws configure)
#
# Usage: ./launch-ec2.sh [options]
#   --region REGION       (default: us-east-1)
#   --key-name NAME      Use existing key pair (skip key creation)
#   --instance-type TYPE (default: t3.small)
#   --no-user-data       Skip user-data bootstrap

set -e

# Prefer Homebrew aws on Mac (avoids broken x86 /usr/local/bin/aws on Apple Silicon)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/bin:$SCRIPT_DIR/../../.venv/bin:$HOME/.local/bin:$PATH"

REGION="${REGION:-us-east-1}"
KEY_NAME=""
INSTANCE_TYPE="t3.small"
USE_USER_DATA=true
REPO_OWNER="jackwood1"
REPO_NAME="woodfamily-ai-v2"

while [[ $# -gt 0 ]]; do
  case $1 in
    --region) REGION="$2"; shift 2 ;;
    --key-name) KEY_NAME="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --no-user-data) USE_USER_DATA=false; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

SG_NAME="woodfamily-sg"
KEY_FILE=""

# Create key pair if not specified
if [[ -z "$KEY_NAME" ]]; then
  KEY_NAME="woodfamily-deploy-$(date +%Y%m%d-%H%M)"
  echo "Creating key pair: $KEY_NAME"
  KEY_FILE="$SCRIPT_DIR/${KEY_NAME}.pem"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --region "$REGION" \
    --query 'KeyMaterial' --output text > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
  echo "  Saved to: $KEY_FILE"
fi

# Create or get security group
echo "Setting up security group: $SG_NAME"
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" --region "$REGION" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
  SG_ID=$(aws ec2 create-security-group \
    --group-name "$SG_NAME" \
    --description "Woodfamily AI - SSH, HTTP, HTTPS" \
    --region "$REGION" \
    --query 'GroupId' --output text)
fi

# Allow SSH, HTTP, HTTPS (from anywhere - tighten in production)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
  --protocol tcp --port 22 --cidr 0.0.0.0/0 2>/dev/null || true
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 2>/dev/null || true
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 2>/dev/null || true

# Get AMI (Amazon Linux 2023)
AMI=$(aws ssm get-parameters \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --region "$REGION" \
  --query 'Parameters[0].Value' --output text 2>/dev/null || \
  aws ec2 describe-images --owners amazon --region "$REGION" \
    --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,values=available" \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

# User data
USER_DATA_ARG=""
if [[ "$USE_USER_DATA" == true && -f "$SCRIPT_DIR/ec2-user-data.sh" ]]; then
  USER_DATA_ARG="--user-data file://$SCRIPT_DIR/ec2-user-data.sh"
fi

# Launch instance
echo "Launching EC2 instance ($INSTANCE_TYPE)..."
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=woodfamily-ai}]" \
  --region "$REGION" \
  $USER_DATA_ARG \
  --query 'Instances[0].InstanceId' --output text)

echo "Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo ""
echo "=========================================="
echo "EC2 instance launched successfully"
echo "=========================================="
echo "Instance ID:  $INSTANCE_ID"
echo "Public IP:   $PUBLIC_IP"
echo ""
[[ -n "$KEY_FILE" ]] && echo "SSH:  ssh -i $KEY_FILE ec2-user@$PUBLIC_IP" || echo "SSH:  ssh -i <your-key.pem> ec2-user@$PUBLIC_IP"
echo ""
echo "Bootstrap may take 2-3 minutes. Then:"
echo "  1. SSH in and edit ~/woodfamily-ai-v2/.env"
echo "  2. Run: cd ~/woodfamily-ai-v2 && docker compose -f docker-compose.prod.yml up -d"
echo "  3. Add GitHub secrets: DEPLOY_HOST=$PUBLIC_IP, DEPLOY_USER=ec2-user, DEPLOY_SSH_KEY=<contents of your .pem>"
echo "=========================================="

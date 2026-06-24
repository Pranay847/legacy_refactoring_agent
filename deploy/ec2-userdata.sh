#!/bin/bash
# ============================================================================
# EC2 user-data bootstrap (Amazon Linux 2023).
# Installs Docker + the compose plugin and clones the repo. It deliberately
# does NOT create .env (no secrets in user-data) — you do that over SSH.
#
# Paste this into the "User data" field when launching the instance.
# ============================================================================
set -euxo pipefail

dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

# Docker Compose v2 plugin
DOCKER_CONFIG=/usr/local/lib/docker
mkdir -p "$DOCKER_CONFIG/cli-plugins"
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"

# Clone the app (public repo). Change the URL if you deploy from a fork.
cd /home/ec2-user
git clone https://github.com/Pranay847/legacy_refactoring_agent.git
chown -R ec2-user:ec2-user legacy_refactoring_agent

cat > /home/ec2-user/NEXT_STEPS.txt <<'EOF'
Bootstrap complete. Finish the deploy:

  cd ~/legacy_refactoring_agent
  cp .env.example .env
  nano .env              # set NEO4J_PASSWORD, ANTHROPIC_API_KEY, FRONTEND_URL=http://<public-ip>
  docker compose -f docker-compose.prod.yml up -d --build

Then open http://<public-ip>/
EOF
chown ec2-user:ec2-user /home/ec2-user/NEXT_STEPS.txt

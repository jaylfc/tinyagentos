#!/bin/bash

# TinyAgentOS image customization
# This runs inside the chroot during Armbian image build
#
# Available variables from Armbian:
#   $RELEASE  — bookworm, jammy, etc.
#   $BOARD    — orangepi5-plus, rock-5b, etc.
#   $BRANCH   — vendor, current, edge
#   $ARCH     — arm64, armhf

set -euo pipefail

echo ">>> TinyAgentOS: Installing system dependencies"

apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget \
    incus-client \
    docker.io docker-compose \
    avahi-daemon

# Node.js 22 LTS via NodeSource
echo ">>> TinyAgentOS: Installing Node.js 22 LTS"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y -qq nodejs

# Clone TinyAgentOS
echo ">>> TinyAgentOS: Cloning repository"
git clone https://github.com/jaylfc/tinyagentos.git /opt/tinyagentos
cd /opt/tinyagentos

# Python venv and install
echo ">>> TinyAgentOS: Creating venv and installing"
python3 -m venv venv
venv/bin/pip install -e . -q

# Default config
cp data/config.yaml.example data/config.yaml

# Systemd services
cp tinyagentos.service /etc/systemd/system/
systemctl enable tinyagentos

# Enable Docker
systemctl enable docker

# Clone app catalog
echo ">>> TinyAgentOS: Cloning app catalog"
if [ -d /opt/tinyagentos/app-catalog ]; then
    echo "    app-catalog already present (from repo clone)"
else
    git clone https://github.com/jaylfc/tinyagentos-app-catalog.git /opt/tinyagentos/app-catalog || \
        echo "    WARNING: app-catalog clone failed — will be fetched on first boot"
fi

# First-boot trigger: runs once on initial startup
touch /opt/tinyagentos/.first-boot

echo ">>> TinyAgentOS: Image customization complete"

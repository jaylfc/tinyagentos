#!/bin/bash
# TinyAgentOS installer — for users on stock Armbian/Debian who want to install without a pre-built image.
# Usage: curl -sL https://raw.githubusercontent.com/jaylfc/tinyagentos/master/install.sh | bash

set -e

INSTALL_DIR="/opt/tinyagentos"
DATA_DIR="/opt/tinyagentos/data"
CATALOG_REPO="https://github.com/jaylfc/tinyagentos.git"

echo "======================================"
echo "  TinyAgentOS Installer"
echo "======================================"
echo ""

# Check for root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo bash install.sh"
    exit 1
fi

# Detect architecture
ARCH=$(uname -m)
echo "Detected architecture: $ARCH"

# Install system dependencies
echo ""
echo "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nodejs npm git curl avahi-daemon

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Clone or update TinyAgentOS
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating TinyAgentOS..."
    cd "$INSTALL_DIR"
    git pull --ff-only
else
    echo "Installing TinyAgentOS to $INSTALL_DIR..."
    git clone "$CATALOG_REPO" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create virtual environment
if [ ! -d "$INSTALL_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
fi

# Install TinyAgentOS
echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install -e "." -q

# Create data directory
mkdir -p "$DATA_DIR"

# Create default config if it doesn't exist
if [ ! -f "$DATA_DIR/config.yaml" ]; then
    echo "Creating default config..."
    cp "$INSTALL_DIR/data/config.yaml" "$DATA_DIR/config.yaml"
fi

# Install host firewall scripts (allow incus bridge through docker's FORWARD DROP)
echo ""
echo "Installing host firewall scripts..."
mkdir -p /opt/tinyagentos/scripts
for fw_script in host-firewall-up.sh host-firewall-down.sh; do
    cp "$INSTALL_DIR/scripts/$fw_script" /opt/tinyagentos/scripts/
    chmod +x /opt/tinyagentos/scripts/$fw_script
done
cp "$INSTALL_DIR/systemd/tinyagentos-host-firewall.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tinyagentos-host-firewall.service
echo "Host firewall service status: $(systemctl is-active tinyagentos-host-firewall.service)"

# Install systemd service
echo "Installing systemd service..."
cat > /etc/systemd/system/tinyagentos.service << EOF
[Unit]
Description=TinyAgentOS Web GUI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn tinyagentos.app:create_app --factory --host 0.0.0.0 --port 6969
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tinyagentos

# Detect if rkllama is available (Rockchip NPU)
if [ -e "/dev/rknpu" ]; then
    echo ""
    echo "Rockchip NPU detected! Consider installing rkllama for NPU-accelerated inference."
    echo "  pip install rkllama"
fi

# Start TinyAgentOS
echo ""
echo "Starting TinyAgentOS..."
systemctl start tinyagentos

# Get IP address
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "======================================"
echo "  TinyAgentOS installed successfully!"
echo "======================================"
echo ""
echo "  Open: http://$IP:6969"
echo ""
echo "  Service: systemctl status tinyagentos"
echo "  Logs:    journalctl -u tinyagentos -f"
echo ""

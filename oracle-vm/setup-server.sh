#!/usr/bin/env bash
set -euo pipefail

# Automated setup script for JioTV Go on Ubuntu (Oracle Cloud VM).
# Run with sudo or as root.

if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root (or with sudo)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JIOTV_VERSION="v3.22.0"
DOMAIN="tv.trylocalhost.com"

echo "==> 1. Applying persistent IPv6 fix (disables broken Oracle RA routes)..."
cp "$SCRIPT_DIR/99-disable-ipv6.conf" /etc/sysctl.d/99-disable-ipv6.conf
sysctl -p /etc/sysctl.d/99-disable-ipv6.conf
ip -6 route del default 2>/dev/null || true

echo "==> 2. Installing required system packages..."
apt-get update -y
apt-get install -y curl certbot python3-certbot-nginx nginx

echo "==> 3. Setting up /opt/jiotv_go..."
mkdir -p /opt/jiotv_go/data
chown -R ubuntu:ubuntu /opt/jiotv_go

if [ ! -f /opt/jiotv_go/jiotv_go ]; then
  echo "==> Downloading jiotv_go ${JIOTV_VERSION} for linux-amd64..."
  curl -sL -o /opt/jiotv_go/jiotv_go "https://github.com/JioTV-Go/jiotv_go/releases/download/${JIOTV_VERSION}/jiotv_go-linux-amd64"
  chmod +x /opt/jiotv_go/jiotv_go
  ln -sf /opt/jiotv_go/jiotv_go /usr/local/bin/jiotv_go
fi

echo "==> 4. Installing jiotv_go.yaml and systemd service..."
cp "$SCRIPT_DIR/jiotv_go.yaml" /opt/jiotv_go/jiotv_go.yaml
chown ubuntu:ubuntu /opt/jiotv_go/jiotv_go.yaml
cp "$SCRIPT_DIR/jiotv_go.service" /etc/systemd/system/jiotv_go.service
systemctl daemon-reload
systemctl enable --now jiotv_go

echo "==> 5. Setting up Nginx cache and reverse proxy..."
mkdir -p /var/cache/nginx/jiotv
chown -R www-data:www-data /var/cache/nginx/jiotv

cat << 'EOF' > /etc/nginx/conf.d/jiotv_cache.conf
proxy_cache_path /var/cache/nginx/jiotv levels=1:2 keys_zone=jiotv_cache:10m max_size=500m inactive=30d use_temp_path=off;
EOF

cp "$SCRIPT_DIR/nginx-tv.conf" "/etc/nginx/sites-available/${DOMAIN}.conf"
ln -sf "/etc/nginx/sites-available/${DOMAIN}.conf" "/etc/nginx/sites-enabled/"

echo "==> 6. Testing Nginx config..."
nginx -t
systemctl reload nginx

echo "==> Setup complete!"
echo "If this is a fresh setup, obtain SSL certificate by running:"
echo "  sudo certbot --nginx -d ${DOMAIN} --redirect"
echo "Then log in using your Jio number:"
echo "  jiotv_go -c /opt/jiotv_go/jiotv_go.yaml login otp"
echo "And restart the service:"
echo "  sudo systemctl restart jiotv_go"

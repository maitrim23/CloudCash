#!/bin/bash
# EC2 "user data" for CostGoblin on Amazon Linux 2023 (x86_64). Paste this whole file into
# Launch instance -> Advanced details -> User data. Runs once at first boot, as root.
#
# Result: Docker + two containers (the app, and Caddy as an HTTPS reverse proxy). HTTPS uses a free
# hostname "<ip-with-dashes>.sslip.io" that resolves to this server's public IP, so no domain is needed.
#
# A systemd timer re-runs `costgoblin-start` every 15 minutes. It is idempotent: it does nothing unless
#   (a) the public IP changed (e.g. you attached an Elastic IP after launch),
#   (b) a newer image was published (build-image workflow), or
#   (c) a container is missing.
# So you never need to log in to the server. See deploy/aws/README.md.
set -euo pipefail
exec > >(tee /var/log/costgoblin-setup.log) 2>&1

IMAGE="ghcr.io/maitrim23/costgoblin:latest"   # must be a PUBLIC package

dnf install -y docker
systemctl enable --now docker
mkdir -p /opt/costgoblin

cat > /usr/local/bin/costgoblin-start <<'SCRIPT'
#!/bin/bash
set -euo pipefail
IMAGE="__IMAGE__"
STATE=/opt/costgoblin

# IMDSv2: ask the instance metadata service for our public IPv4 (needs a short-lived token).
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
IP=""
for _ in $(seq 1 30); do   # the public IP can appear a few seconds after boot
  IP=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
  [ -n "$IP" ] && break
  sleep 2
done
[ -n "$IP" ] || { echo "no public IPv4 yet (attach a public/Elastic IP); will retry on the next timer run"; exit 0; }
DOMAIN="${IP//./-}.sslip.io"

docker pull -q "$IMAGE" >/dev/null || echo "image pull failed (is the GHCR package public?)"
NEW_ID=$(docker image inspect -f '{{.Id}}' "$IMAGE" 2>/dev/null || echo none)
CUR_ID=$(docker inspect -f '{{.Image}}' app 2>/dev/null || echo none)
RUNNING=$(docker ps --format '{{.Names}}' | grep -cE '^(app|caddy)$' || true)

if [ "$(cat $STATE/domain 2>/dev/null || true)" = "$DOMAIN" ] && [ "$NEW_ID" = "$CUR_ID" ] && [ "$RUNNING" = "2" ]; then
  exit 0   # nothing changed
fi
[ "$NEW_ID" != "none" ] || { echo "no image available; giving up until next run"; exit 0; }

echo "(re)starting: domain=$DOMAIN image=$NEW_ID"
cat > $STATE/Caddyfile <<CADDY
$DOMAIN {
    encode gzip
    reverse_proxy app:8000
}
CADDY
docker network inspect costgoblin >/dev/null 2>&1 || docker network create costgoblin
docker pull -q caddy:2 >/dev/null
docker rm -f app caddy >/dev/null 2>&1 || true

# Named volume (not a host folder) so the container's non-root user can write scenarios.db; it survives re-creation.
docker run -d --name app --network costgoblin --restart unless-stopped \
  -v costgoblin-data:/data -e COOKIE_SECURE=1 "$IMAGE" >/dev/null
docker run -d --name caddy --network costgoblin --restart unless-stopped \
  -p 80:80 -p 443:443 \
  -v $STATE/Caddyfile:/etc/caddy/Caddyfile:ro -v caddy_data:/data \
  caddy:2 >/dev/null
echo "$DOMAIN" > $STATE/domain
echo "serving https://$DOMAIN"
SCRIPT
sed -i "s|__IMAGE__|$IMAGE|" /usr/local/bin/costgoblin-start
chmod +x /usr/local/bin/costgoblin-start

cat > /etc/systemd/system/costgoblin.service <<'UNIT'
[Unit]
Description=CostGoblin (re)start check
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/costgoblin-start
UNIT

cat > /etc/systemd/system/costgoblin.timer <<'UNIT'
[Unit]
Description=Run the CostGoblin start check every 15 minutes

[Timer]
OnBootSec=30s
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now costgoblin.timer
systemctl start costgoblin.service || true   # first run right now; the timer retries if it could not finish

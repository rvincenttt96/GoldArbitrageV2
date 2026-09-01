#!/usr/bin/env bash
# Runs on the Iranian VPS. Collects two things and uploads them:
#   1. why inbound SSH is being filtered
#   2. the public price endpoints of melligold.com and tala30.ir
#
# Reads only. Places no orders and needs no login.

set +e
OUT=/tmp/goldarb-discovery.txt
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
exec > >(tee "$OUT") 2>&1

hr() { printf '\n===== %s =====\n' "$1"; }

hr "HOST"
hostname; date -u
echo "public ip: $(curl -s -m 10 https://api.ipify.org)"
curl -s -m 10 "http://ip-api.com/line/?fields=country,isp,query"

hr "SSH: what is listening"
ss -lntp | grep -E ':(22|2222)\b'
echo "--- bindv6only (1 means IPv6 sockets do NOT accept IPv4) ---"
sysctl -n net.ipv6.bindv6only
echo "--- sshd directives ---"
grep -nE '^\s*(Port|ListenAddress|AddressFamily)' /etc/ssh/sshd_config
echo "--- loopback reachability ---"
for p in 22 2222; do
  timeout 5 bash -c "echo > /dev/tcp/127.0.0.1/$p" 2>&1 \
    && echo "127.0.0.1:$p reachable" || echo "127.0.0.1:$p NOT reachable"
done
IP4=$(curl -s -m 10 https://api.ipify.org)
for p in 22 2222; do
  timeout 5 bash -c "echo > /dev/tcp/$IP4/$p" 2>&1 \
    && echo "$IP4:$p reachable from itself" || echo "$IP4:$p NOT reachable from itself"
done
echo "--- firewall ---"
iptables -S 2>/dev/null | head -25
nft list ruleset 2>/dev/null | head -25
ufw status 2>/dev/null | head -5

# --------------------------------------------------------------------------
# The part that actually matters: public price endpoints.
# --------------------------------------------------------------------------

probe() {
  local label="$1" url="$2"
  printf '\n--- %s\n    %s\n' "$label" "$url"
  curl -s -m 15 -A "$UA" -H 'Accept: application/json' \
       -w '    HTTP %{http_code}  %{content_type}  %{size_download}B\n' \
       -o /tmp/body.$$ "$url"
  head -c 700 /tmp/body.$$; echo
  rm -f /tmp/body.$$
}

hr "MELLIGOLD: landing page and bundles"
curl -s -m 25 -A "$UA" -c /tmp/mg.jar -b /tmp/mg.jar -L --max-redirs 5 \
     -o /tmp/mg.html -w 'landing HTTP %{http_code} size=%{size_download}\n' https://melligold.com/
echo "--- api-looking strings in the landing HTML ---"
grep -oE '"/(api|v1|v2|services|gateway)[a-zA-Z0-9/_.-]*"' /tmp/mg.html | sort -u | head -40
grep -oE 'https://[a-zA-Z0-9.-]*melligold[a-zA-Z0-9./_-]*' /tmp/mg.html | grep -v cdn | sort -u | head -20
echo "--- fetching JS chunks and grepping them for api paths ---"
for js in $(grep -oE '/_next/static/chunks/[a-zA-Z0-9._-]+\.js' /tmp/mg.html | sort -u | head -12); do
  curl -s -m 20 -A "$UA" "https://melligold.com$js" -o /tmp/chunk.js
  grep -ohE '"/(api|v1|v2)[a-zA-Z0-9/_{}$.-]*"' /tmp/chunk.js
done | sort -u | head -60

hr "MELLIGOLD: guessing public price endpoints"
for p in \
  /api/v1/price /api/price /api/v1/public/price /api/v1/gold/price \
  /api/v1/prices/current /api/v1/public/gold-price /api/v1/rate \
  /api/v1/landing/price /api/v1/home/price /api/v1/trade/price ; do
  probe "melligold$p" "https://melligold.com$p"
done

hr "TALA30: landing page"
curl -s -m 25 -A "$UA" -c /tmp/t30.jar -b /tmp/t30.jar -L --max-redirs 5 \
     -o /tmp/t30.html -w 'landing HTTP %{http_code} size=%{size_download}\n' https://tala30.ir/
head -c 400 /tmp/t30.html; echo
echo "--- api-looking strings ---"
grep -oE '"/(api|v1|v2)[a-zA-Z0-9/_.-]*"' /tmp/t30.html | sort -u | head -40
grep -oE 'https://[a-zA-Z0-9.-]*tala30[a-zA-Z0-9./_-]*' /tmp/t30.html | sort -u | head -20
echo "--- js bundles ---"
for js in $(grep -oE '/[a-zA-Z0-9/_.-]+\.js' /tmp/t30.html | sort -u | head -12); do
  curl -s -m 20 -A "$UA" "https://tala30.ir$js" -o /tmp/chunk.js
  grep -ohE '"/(api|v1|v2)[a-zA-Z0-9/_{}$.-]*"' /tmp/chunk.js
done | sort -u | head -60

hr "TALA30: guessing public price endpoints"
for p in \
  /api/v1/price /api/price /api/v1/public/price /api/gold/price \
  /api/v1/prices /api/v1/rate /api/v1/home ; do
  probe "tala30$p" "https://tala30.ir$p"
done

hr "CONTROL: venues that already work, to prove the method"
probe "milli price" "https://milli.gold/api/v1/public/milli-price/detail"
probe "goldika price" "https://api.goldika.ir/api/public/price"

hr "DONE"
echo "report saved to $OUT"

# Upload so it can be read remotely. Nothing here is secret: no credentials are
# sent anywhere and no logged-in session is used.
sleep 1
echo
echo "############ UPLOAD ############"
URL=$(curl -s -m 90 --data-binary "@$OUT" https://paste.rs/)
case "$URL" in
  https://*) ;;
  *) URL=$(curl -s -m 90 -F "content=<$OUT" https://dpaste.com/api/v2/ 2>/dev/null) ;;
esac
echo "REPORT URL: $URL"
echo "(if no URL appeared, send /tmp/goldarb-discovery.txt by hand)"

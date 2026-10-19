#!/usr/bin/env bash
# Certbot deploy hook for the two existing serverA certificates.
set -Eeuo pipefail

: "${RENEWED_LINEAGE:?Certbot must provide RENEWED_LINEAGE}"
domain=$(basename -- "$RENEWED_LINEAGE")
case "$domain" in fangcunmount.cn|yangshujie.com) ;; *) echo 'Unreviewed certificate lineage' >&2; exit 1 ;; esac
test "$(id -u)" = 0
openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -noout -checkend 86400 >/dev/null
certificate_key=$(openssl x509 -in "$RENEWED_LINEAGE/cert.pem" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum | cut -d' ' -f1)
private_key=$(openssl pkey -in "$RENEWED_LINEAGE/privkey.pem" -pubout -outform DER | sha256sum | cut -d' ' -f1)
test "$certificate_key" = "$private_key"

work=$(mktemp -d /data/ssl/.renew-XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
certificate="/data/ssl/certs/$domain.crt"
key="/data/ssl/private/$domain.key"
backup="/data/ssl/archive/$(date -u +%Y%m%dT%H%M%SZ)-$domain-$$"
install -d -m 700 "$backup"
cp -p -- "$certificate" "$backup/certificate.crt"
cp -p -- "$key" "$backup/private.key"
install -m 644 -o 2000 -g 2000 "$RENEWED_LINEAGE/fullchain.pem" "$work/certificate.crt"
install -m 640 -o 2000 -g 2000 "$RENEWED_LINEAGE/privkey.pem" "$work/private.key"
mv -- "$work/certificate.crt" "$certificate"
mv -- "$work/private.key" "$key"

if [ "$(docker inspect --format '{{.State.Running}}' nginx 2>/dev/null || true)" = true ]; then
  if ! docker exec nginx nginx -t || ! docker exec nginx nginx -s reload; then
    cp -p -- "$backup/certificate.crt" "$certificate"
    cp -p -- "$backup/private.key" "$key"
    echo 'Nginx rejected renewed certificates; restored the previous pair' >&2
    exit 1
  fi
fi
echo "Installed validated certificate: $domain"

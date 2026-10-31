FROM redis:7.4.2-alpine
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    apk add --no-cache bash sudo util-linux coreutils findutils python3
RUN adduser -D deploy && mkdir -p /var/lib/fangcun-image-retention \
    && touch /var/lib/fangcun-image-retention/deploy.lock \
    && chmod 0755 /var/lib/fangcun-image-retention \
    && chmod 0666 /var/lib/fangcun-image-retention/deploy.lock
COPY install.sh image-retention.py /work/

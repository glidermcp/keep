FROM caddy:2.11.7-builder AS builder
RUN xcaddy build v2.11.7 --with github.com/caddy-dns/cloudflare@v0.2.4 \
    && setcap -r /usr/bin/caddy
FROM caddy:2.11.7
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
COPY entrypoint.sh /usr/local/bin/keep-caddy
RUN chmod 755 /usr/local/bin/keep-caddy \
    && mkdir -p /data/caddy /config/caddy \
    && chown -R 10001:10001 /data /config
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/keep-caddy"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

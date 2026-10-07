FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

ARG KEEP_VERSION
ARG KEEP_BINARY_SHA256
LABEL org.opencontainers.image.title="Keep" \
      org.opencontainers.image.source="https://github.com/glidermcp/keep" \
      org.opencontainers.image.version="${KEEP_VERSION}" \
      io.glidermcp.keep.binary-sha256="${KEEP_BINARY_SHA256}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 keep \
    && useradd --uid 10001 --gid 10001 --home-dir /data --no-create-home keep \
    && mkdir -p /data/documents /models /usr/share/keep \
    && chown -R 10001:10001 /data /models

COPY --chmod=755 native/keep /usr/local/bin/keep
COPY native/LICENSE native/THIRD-PARTY-NOTICES.txt native/INSTALL.txt /usr/share/keep/
COPY --chmod=755 entrypoint.sh healthcheck.sh token.sh /usr/local/lib/keep/
RUN printf '%s  /usr/local/bin/keep\n' "$KEEP_BINARY_SHA256" | sha256sum --check --status \
    && keep --version | grep -F "$KEEP_VERSION"

ENV HOME=/data
USER 10001:10001
WORKDIR /data
EXPOSE 7340
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 CMD ["/usr/local/lib/keep/healthcheck.sh"]
ENTRYPOINT ["/usr/local/lib/keep/entrypoint.sh"]
CMD ["--transport", "http", "--bind-address", "0.0.0.0", "--port", "7340", "--data-dir", "/data/documents"]

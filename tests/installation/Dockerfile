# CI-only image; never delivered. Reuses locked test fixtures and real parser.
FROM scientific-ragagent-backend:local
USER 0
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --frozen --extra parsing --extra models && uv cache clean
USER 10001:10001

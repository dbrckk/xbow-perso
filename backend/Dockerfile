FROM python:3.14-slim

ARG TARGETARCH
ARG KATANA_VERSION=1.7.0
ARG HTTPX_VERSION=1.12.0
ARG SUBFINDER_VERSION=2.16.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && ARCH="${TARGETARCH:-$(dpkg --print-architecture)}" \
    && case "$ARCH" in amd64|arm64) ;; *) echo "unsupported architecture: $ARCH" >&2; exit 1 ;; esac \
    && for spec in \
         "katana:${KATANA_VERSION}:katana-${KATANA_VERSION}-checksums.txt" \
         "httpx:${HTTPX_VERSION}:httpx_${HTTPX_VERSION}_checksums.txt" \
         "subfinder:${SUBFINDER_VERSION}:subfinder_${SUBFINDER_VERSION}_checksums.txt"; do \
         tool="$(printf '%s' "$spec" | cut -d: -f1)"; \
         version="$(printf '%s' "$spec" | cut -d: -f2)"; \
         checksum_file="$(printf '%s' "$spec" | cut -d: -f3)"; \
         archive="${tool}_${version}_linux_${ARCH}.zip"; \
         release="https://github.com/projectdiscovery/${tool}/releases/download/v${version}"; \
         curl --fail --location --proto '=https' --tlsv1.2 "$release/$archive" -o "/tmp/$archive"; \
         curl --fail --location --proto '=https' --tlsv1.2 "$release/$checksum_file" -o "/tmp/$checksum_file"; \
         expected="$(grep -E "[[:space:]]${archive}$" "/tmp/$checksum_file" | head -n 1)"; \
         test -n "$expected"; \
         printf '%s\n' "$expected" | (cd /tmp && sha256sum -c -); \
         unzip -q "/tmp/$archive" "$tool" -d /usr/local/bin; \
         chmod 0755 "/usr/local/bin/$tool"; \
         "/usr/local/bin/$tool" -version; \
       done \
    && rm -rf /tmp/* /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY app ./app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

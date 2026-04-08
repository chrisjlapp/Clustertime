FROM debian:bookworm-slim

# Install linuxptp, iproute2 (macvlan management), ping, and Python
RUN apt-get update && apt-get install -y --no-install-recommends \
        linuxptp \
        iproute2 \
        iputils-ping \
        python3 \
        python3-yaml \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application source
COPY clustertime/ clustertime/
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Config and runtime directories
RUN mkdir -p /etc/clustertime /var/run/clustertime

# Config volume — mount your config.yaml here
VOLUME ["/etc/clustertime"]

# ptp4l runtime files
VOLUME ["/var/run/clustertime"]

ENTRYPOINT ["/entrypoint.sh"]

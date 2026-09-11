# Build only on the authorized remote host. A locally built binary is supplied
# from that same recorded source snapshot; never publish from this workflow.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 openvswitch-common ca-certificates && rm -rf /var/lib/apt/lists/*
COPY bin/ani-network-service /usr/local/bin/ani-network-service
ENTRYPOINT ["/usr/local/bin/ani-network-service"]

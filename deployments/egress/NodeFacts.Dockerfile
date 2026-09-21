# Build only on the authorized remote host. A locally built binary is supplied
# from that same recorded source snapshot; never publish from this workflow.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 openvswitch-switch ca-certificates \
    && ip -Version && ovs-vsctl --version && rm -rf /var/lib/apt/lists/*
COPY bin/ani-resource-service /usr/local/bin/ani-resource-service
ENTRYPOINT ["/usr/local/bin/ani-resource-service"]

FROM debian@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171
COPY probe /probe
COPY probe-entrypoint.sh /probe-entrypoint.sh
USER 65532:65532
ENTRYPOINT ["/bin/sh", "/probe-entrypoint.sh"]

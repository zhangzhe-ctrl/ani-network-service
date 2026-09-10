FROM docker.io/library/postgres@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280
COPY --chmod=0555 ani-network-service /ani-network-service
ENTRYPOINT ["/ani-network-service"]

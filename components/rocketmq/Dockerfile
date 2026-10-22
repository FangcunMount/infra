FROM eclipse-temurin:17-jre-jammy@sha256:b3054a20e1a851574cdb1692dd0db5310c647e62214a2a7abecbec1b9e3ae8f1 AS verify
RUN apt-get update && apt-get install -y --no-install-recommends unzip gnupg && rm -rf /var/lib/apt/lists/*
WORKDIR /release
COPY rocketmq.zip rocketmq.zip.asc KEYS ./
RUN echo "21555d9bd79792ac89f246566f19f58e300784c59b96289fd0c74db14787861081fb60ebb95cf541bf20a3e508bf3b70feb9596ea3ba6dc5dc88fa6081f00577  rocketmq.zip" | sha512sum -c - && gpg --batch --import KEYS && gpg --batch --status-fd 1 --verify rocketmq.zip.asc rocketmq.zip | tee /tmp/verify.status && grep -q "VALIDSIG 09D58134D2DA90B296ABCB77D5C871BAC9D394D2" /tmp/verify.status && unzip -q rocketmq.zip -d /opt

FROM eclipse-temurin:17-jre-jammy@sha256:b3054a20e1a851574cdb1692dd0db5310c647e62214a2a7abecbec1b9e3ae8f1
LABEL org.opencontainers.image.title="RocketMQ" org.opencontainers.image.version="5.5.1" org.opencontainers.image.source="https://github.com/apache/rocketmq/tree/rocketmq-all-5.5.1"
RUN groupadd -g 3000 rocketmq && useradd -u 3000 -g 3000 -m -d /home/rocketmq rocketmq
COPY --from=verify /opt/rocketmq-all-5.5.1-bin-release /opt/rocketmq
COPY --chmod=0555 entrypoint.sh /opt/rocketmq/entrypoint.sh
ENV ROCKETMQ_HOME=/opt/rocketmq HOME=/home/rocketmq NAMESRV_ADDR=nameserver:9876
# Applies also to explicit MQAdmin invocations. Pin trust to the mounted server
# certificate; never enable insecure trust when encrypting internal remoting.
ENV JAVA_TOOL_OPTIONS="-Dtls.enable=true -Dtls.client.authServer=true -Dtls.client.trustCertPath=/etc/rocketmq/tls/server.crt"
WORKDIR /opt/rocketmq
USER 3000:3000
ENTRYPOINT ["/opt/rocketmq/entrypoint.sh"]

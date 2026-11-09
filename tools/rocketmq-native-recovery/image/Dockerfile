# The build context contains only the exact sources, verified archive, and
# source-bound Linux recovery binary. No credentials or coordinator inputs.
FROM --platform=$BUILDPLATFORM eclipse-temurin:17-jdk-jammy@sha256:057a0daec60e87c96571bf5c9c7792065bcb19e804d584cd37d4144038a35717 AS helper
WORKDIR /build
COPY rocketmq.zip NativeHalfIdentity.java NativeHalfManaged.java ./
RUN set -eu; \
    echo "21555d9bd79792ac89f246566f19f58e300784c59b96289fd0c74db14787861081fb60ebb95cf541bf20a3e508bf3b70feb9596ea3ba6dc5dc88fa6081f00577  rocketmq.zip" | sha512sum -c -; \
    jar xf rocketmq.zip; \
    mkdir classes; \
    javac --release 17 -g:none -cp 'rocketmq-all-5.5.1-bin-release/lib/*' -d classes NativeHalfIdentity.java NativeHalfManaged.java; \
    jar --create --file native-managed.jar --no-manifest --date=1980-01-01T00:00:02Z \
      -C classes NativeHalfIdentity.class -C classes NativeHalfManaged.class; \
    jar --create --file native-managed-repeat.jar --no-manifest --date=1980-01-01T00:00:02Z \
      -C classes NativeHalfIdentity.class -C classes NativeHalfManaged.class; \
    cmp native-managed.jar native-managed-repeat.jar; \
    printf 'NativeHalfIdentity.class\nNativeHalfManaged.class\n' > expected-members.txt; \
    jar --list --file native-managed.jar > actual-members.txt; \
    cmp expected-members.txt actual-members.txt; \
    javac -version > javac-version.txt 2>&1; \
    find rocketmq-all-5.5.1-bin-release/lib -type f -exec chmod 0444 {} +; \
    find rocketmq-all-5.5.1-bin-release/lib -type d -exec chmod 0555 {} +

FROM eclipse-temurin:17-jre-jammy@sha256:b3054a20e1a851574cdb1692dd0db5310c647e62214a2a7abecbec1b9e3ae8f1
ARG SOURCE_SHA
ARG CLI_SHA256
LABEL org.opencontainers.image.title="RocketMQ named native recovery candidate" \
      org.opencontainers.image.revision="${SOURCE_SHA}"
WORKDIR /opt/native-recovery
COPY --from=helper --chmod=0444 /build/native-managed.jar /build/javac-version.txt ./
COPY --from=helper /build/rocketmq-all-5.5.1-bin-release/lib/ ./lib/
COPY --chmod=0555 native-recovery managed-java.sh ./
RUN set -eu; \
    echo "${CLI_SHA256}  native-recovery" | sha256sum -c -; \
    ./native-recovery version > version.json; \
    grep -F "\"source_sha\":\"${SOURCE_SHA}\"" version.json; \
    chmod 0444 version.json
ENV HOME=/tmp
USER 3000:3000
ENTRYPOINT ["/opt/native-recovery/native-recovery"]
CMD ["version"]

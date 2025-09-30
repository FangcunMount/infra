FROM jenkins/jenkins:lts

ARG http_proxy
ARG https_proxy

ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

USER root
RUN apt-get update \
    && apt-get install -y make wget tar ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    # 安装 Go（官方二进制包，版本可按需调整）\
    && GO_VERSION="1.22.3" \
    && wget -q https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz \
    && rm go${GO_VERSION}.linux-amd64.tar.gz \
    && echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile.d/go.sh

ENV PATH="/usr/local/go/bin:${PATH}"
USER jenkins

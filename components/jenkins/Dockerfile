FROM jenkins/jenkins:lts

# --- 构建时测试代理连通性 ---
RUN echo "[DEBUG] 当前 http_proxy: $http_proxy" \
    && echo "[DEBUG] 当前 https_proxy: $https_proxy" \
    && curl -I --max-time 10 https://www.google.com || (echo '[WARN] 代理不可用或被墙，继续构建'; exit 0)

ARG http_proxy
ARG https_proxy

ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

USER root
RUN apt-get update \
    && apt-get install -y make git curl wget unzip tar ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    # 安装 Go（官方二进制包，版本可按需调整）\
    && GO_VERSION="1.22.3" \
    && wget -q https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz \
    && rm go${GO_VERSION}.linux-amd64.tar.gz \
    && echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile.d/go.sh

ENV PATH="/usr/local/go/bin:${PATH}"
USER jenkins

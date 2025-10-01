FROM jenkins/jenkins:lts

# 统一支持大小写代理参数，避免宿主机 127.0.0.1 镜像构建失败
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# 归一化代理环境变量，优先使用小写，其次回退到大写参数
ENV http_proxy=${http_proxy:-${HTTP_PROXY}}
ENV https_proxy=${https_proxy:-${HTTPS_PROXY}}
ENV no_proxy=${no_proxy:-${NO_PROXY}}
ENV HTTP_PROXY=$http_proxy
ENV HTTPS_PROXY=$https_proxy
ENV NO_PROXY=$no_proxy

USER root
RUN set -eux; \
    proxy_url="${http_proxy:-${https_proxy:-}}"; \
    if [ -n "$proxy_url" ]; then \
        proxy_target="$proxy_url"; \
        proxy_clean=${proxy_target#*://}; \
        if [ "$proxy_clean" != "$proxy_target" ]; then proxy_target="$proxy_clean"; fi; \
        if [[ "$proxy_target" == *@* ]]; then proxy_target=${proxy_target#*@}; fi; \
        proxy_host=${proxy_target%%[:/]*}; \
        proxy_port=; \
        if [[ "$proxy_target" == *:* ]]; then \
            proxy_port=${proxy_target#*:}; \
            proxy_port=${proxy_port%%/*}; \
        fi; \
        if [[ -z "$proxy_port" || "$proxy_port" == "$proxy_target" ]]; then proxy_port=80; fi; \
        if [[ -z "$proxy_host" ]]; then \
            echo "[WARN] 无法解析构建代理 $proxy_url，自动禁用代理"; \
            http_proxy= HTTPS_PROXY= https_proxy= HTTP_PROXY=; \
            export http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; \
        elif ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$proxy_host/$proxy_port" >/dev/null 2>&1; then \
            echo "[WARN] 构建代理 $proxy_url 不可达，自动禁用代理"; \
            http_proxy= HTTPS_PROXY= https_proxy= HTTP_PROXY=; \
            export http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; \
        fi; \
    fi; \
    apt-get update; \
    apt-get install -y make git curl wget unzip tar ca-certificates; \
    rm -rf /var/lib/apt/lists/*; \
    GO_VERSION="1.22.3"; \
    wget -q https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz; \
    tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz; \
    rm go${GO_VERSION}.linux-amd64.tar.gz; \
    echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile.d/go.sh

ENV PATH="/usr/local/go/bin:${PATH}"
USER jenkins

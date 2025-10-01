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
ENV NVM_DIR=/usr/local/nvm

USER root
RUN set -eux; \
    proxy_url="${http_proxy:-${https_proxy:-}}"; \
    if [ -n "$proxy_url" ]; then \
        proxy_target="$proxy_url"; \
        proxy_clean=${proxy_target#*://}; \
        if [ "$proxy_clean" != "$proxy_target" ]; then proxy_target="$proxy_clean"; fi; \
        if [ "${proxy_target#*@}" != "$proxy_target" ]; then proxy_target=${proxy_target#*@}; fi; \
        proxy_host=${proxy_target%%[:/]*}; \
        case "$proxy_target" in \
            *:*) \
                proxy_port=${proxy_target#*:}; \
                proxy_port=${proxy_port%%/*}; \
                ;; \
            *) \
                proxy_port=""; \
                ;; \
        esac; \
        if [ -z "$proxy_port" ] || [ "$proxy_port" = "$proxy_target" ]; then proxy_port=80; fi; \
        if [ -z "$proxy_host" ]; then \
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
    apt-get install -y make git curl wget unzip tar ca-certificates build-essential python3 gnupg lsb-release; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --batch --dearmor -o /etc/apt/keyrings/docker.gpg; \
    chmod a+r /etc/apt/keyrings/docker.gpg; \
    release=$(. /etc/os-release && echo "$VERSION_CODENAME"); \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $release stable" > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y docker-ce-cli; \
    mkdir -p "$NVM_DIR"; \
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash; \
    bash -lc ". \"$NVM_DIR/nvm.sh\" \
        && nvm install 20 \
        && nvm install 14 \
        && nvm alias default 20 \
        && nvm use default \
        && npm install -g npm@latest \
        && corepack enable \
        && default_node=\$(nvm version default) \
        && ln -sf \"$NVM_DIR/versions/node/\$default_node/bin/node\" /usr/local/bin/node \
        && ln -sf \"$NVM_DIR/versions/node/\$default_node/bin/npm\" /usr/local/bin/npm \
        && ln -sf \"$NVM_DIR/versions/node/\$default_node/bin/npx\" /usr/local/bin/npx"; \
    printf 'export NVM_DIR="%s"\n[ -s "$NVM_DIR/nvm.sh" ] && \\ \. "$NVM_DIR/nvm.sh"\n' "$NVM_DIR" >/etc/profile.d/nvm.sh; \
    rm -rf /var/lib/apt/lists/*; \
    GO_VERSION="1.22.3"; \
    wget -q https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz; \
    tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz; \
    rm go${GO_VERSION}.linux-amd64.tar.gz; \
    echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile.d/go.sh

ENV PATH="/usr/local/go/bin:${PATH}"
USER jenkins

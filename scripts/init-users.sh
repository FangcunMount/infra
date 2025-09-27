#!/usr/bin/env bash
set -euo pipefail

# ====== 变量（按需填写公钥；也可以先留空，后续用 ssh-copy-id 推）======
# SSH 端口
SSH_PORT="22"              

# www 的公钥
PUBKEY_WWW="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHvBjrJ2LGlLPg2trSjHhHyMGxOJXo5DcozWvSl+TtIT yshujie@163.com"
# yangshujie 的公钥              
PUBKEY_YSJ="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB8klofmhwGpv5gHrj7x9pBEKn5flNVtALIXVo8EnL0G yshujie@163.com"

# ====== 基础工具 ======
apt-get update -y && apt-get upgrade -y
apt-get install -y curl wget git htop vim ufw ca-certificates gnupg lsb-release jq unzip

# ====== 创建账户 ======
# www：系统管理员（可 sudo，可 docker）
if ! id -u www >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" www
fi
usermod -aG sudo www

# yangshujie：个人用户（默认无 sudo、无 docker）
if ! id -u yangshujie >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" yangshujie
fi

# ====== SSH 基线（禁止 root 登陆+口令登陆，仅密钥）======
for U in www yangshujie; do
  install -d -m 700 -o "$U" -g "$U" /home/$U/.ssh
done

if [ -n "$PUBKEY_WWW" ]; then
  echo "$PUBKEY_WWW" >/home/www/.ssh/authorized_keys
  chown www:www /home/www/.ssh/authorized_keys
  chmod 600 /home/www/.ssh/authorized_keys
fi

if [ -n "$PUBKEY_YSJ" ]; then
  echo "$PUBKEY_YSJ" >/home/yangshujie/.ssh/authorized_keys
  chown yangshujie:yangshujie /home/yangshujie/.ssh/authorized_keys
  chmod 600 /home/yangshujie/.ssh/authorized_keys
fi

# 强化 SSHD
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i "s/^#\?Port .*/Port ${SSH_PORT}/" /etc/ssh/sshd_config
systemctl restart ssh

# ====== UFW 基线 ======
ufw default deny incoming
ufw default allow outgoing
ufw allow ${SSH_PORT}/tcp
ufw allow 80,443/tcp
ufw --force enable

# ====== Docker 安装（仅 www 用；root 也可）======
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) stable" \
>/etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker www
systemctl enable --now docker

# ====== sudo 策略 ======
# 1) 默认策略：sudo 组需要输入密码
echo "%sudo ALL=(ALL) ALL" >/etc/sudoers.d/90-sudo-default
chmod 0440 /etc/sudoers.d/90-sudo-default

# 如需给 www 增加免密执行的“有限命令清单”，放开下段注释并按需增减：
: <<'OPTIONAL_NOPASSWD'
cat >/etc/sudoers.d/91-www-nopasswd <<'EOF'
www ALL=(ALL) NOPASSWD:/usr/bin/systemctl *,/usr/bin/journalctl *,/usr/bin/docker *,/usr/bin/apt-get update,/usr/bin/apt-get install *
EOF
chmod 0440 /etc/sudoers.d/91-www-nopasswd
OPTIONAL_NOPASSWD

# ====== 目录与所有权（服务归 www 管理）======
install -d -o www -g www -m 755 /srv/infra
install -d -o www -g www -m 755 /srv/infra/{compose,nginx,mysql,redis,mongodb,portainer,vpn}
# 将来挂载点由 www 拥有，便于运维与备份

# ====== .bashrc 常用别名 ======
append_aliases () {
  local U="$1"
  local BRC="/home/${U}/.bashrc"
  [ "$U" = "root" ] && BRC="/root/.bashrc"
  if ! grep -q "# === custom aliases ===" "$BRC" 2>/dev/null; then
    cat <<'EOF' >>"$BRC"

# === custom aliases ===
export HISTTIMEFORMAT="%F %T "
export EDITOR=vim
alias ll='ls -alF'
alias dps='docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
alias dlog='docker logs -f'
alias dcu='docker compose up -d'
alias dcd='docker compose down'
EOF
  fi
}
append_aliases root
append_aliases www
append_aliases yangshujie

echo "✅ 初始化完成：root(禁密) / www(系统管理员) / yangshujie(个人用户)。"
echo "👉 下一步：以 www 登录做 Docker/服务部署；yangshujie 保持纯用户角色。"

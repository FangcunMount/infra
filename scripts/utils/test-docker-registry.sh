#!/bin/bash

# Docker 镜像拉取性能测试脚本
# 测试不同镜像源的拉取速度

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 测试镜像列表
TEST_IMAGES=(
    "alpine:latest"
    "nginx:alpine"
    "node:alpine"
)

# 镜像源列表
REGISTRY_MIRRORS=(
    "docker.io"
    "docker.m.daocloud.io"
    "dockerproxy.com" 
    "docker.mirrors.ustc.edu.cn"
    "docker.nju.edu.cn"
)

echo "========================================"
echo "🚀 Docker 镜像拉取性能测试"
echo "========================================"

# 检查 Docker 是否可用
if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker 未安装"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    log_error "Docker 服务未运行"
    exit 1
fi

log_success "Docker 服务正常"

# 清理现有镜像
log_info "清理测试镜像..."
for image in "${TEST_IMAGES[@]}"; do
    docker rmi "$image" >/dev/null 2>&1 || true
done

echo
echo "========================================"
echo "📊 镜像拉取速度测试"
echo "========================================"

# 测试默认配置
log_info "测试当前 Docker 配置的拉取速度..."
echo

total_time=0
success_count=0

for image in "${TEST_IMAGES[@]}"; do
    log_info "拉取镜像: $image"
    
    start_time=$(date +%s.%N)
    if timeout 60 docker pull "$image" >/dev/null 2>&1; then
        end_time=$(date +%s.%N)
        pull_time=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
        
        # 如果 bc 不可用，使用整数计算
        if [[ "$pull_time" == "0" ]]; then
            start_int=$(date +%s)
            sleep 0.1  # 小延迟确保时间差
            end_int=$(date +%s)
            pull_time=$((end_int - start_int + 1))
        fi
        
        log_success "✅ $image - 耗时: ${pull_time}s"
        total_time=$(echo "$total_time + $pull_time" | bc 2>/dev/null || echo $((${total_time%.*} + ${pull_time%.*})))
        success_count=$((success_count + 1))
        
        # 获取镜像大小
        size=$(docker images "$image" --format "{{.Size}}" 2>/dev/null || echo "unknown")
        echo "   镜像大小: $size"
    else
        log_warn "⚠️  $image - 拉取失败或超时"
    fi
    
    # 删除镜像为下次测试做准备
    docker rmi "$image" >/dev/null 2>&1 || true
    echo
done

if [[ $success_count -gt 0 ]]; then
    avg_time=$(echo "scale=2; $total_time / $success_count" | bc 2>/dev/null || echo $((${total_time%.*} / success_count)))
    log_success "📊 测试完成: 成功 $success_count/$((${#TEST_IMAGES[@]})) 个镜像"
    log_success "📊 总耗时: ${total_time}s, 平均耗时: ${avg_time}s"
else
    log_error "所有镜像拉取均失败"
fi

echo
echo "========================================"
echo "⚙️  当前镜像加速器配置"
echo "========================================"

# 显示当前配置
if [[ -f /etc/docker/daemon.json ]] && grep -q "registry-mirrors" /etc/docker/daemon.json; then
    log_success "✅ 镜像加速器配置:"
    grep -A 10 "registry-mirrors" /etc/docker/daemon.json | grep "https://" | sed 's/^[ \t]*/   /'
else
    log_warn "⚠️  未检测到镜像加速器配置"
fi

echo
echo "========================================"
echo "🔧 优化建议"
echo "========================================"

if [[ $success_count -eq ${#TEST_IMAGES[@]} ]]; then
    log_success "✅ 所有镜像拉取成功，配置良好"
    echo "  • 镜像加速器工作正常"
    echo "  • 可以正常使用 Docker"
elif [[ $success_count -gt 0 ]]; then
    log_warn "⚠️  部分镜像拉取成功"
    echo "  • 检查网络连接"
    echo "  • 考虑更换镜像加速器"
else
    log_error "❌ 所有镜像拉取失败"
    echo "  • 检查 Docker 配置: cat /etc/docker/daemon.json"
    echo "  • 检查网络连接: ping docker.io"
    echo "  • 重启 Docker 服务: systemctl restart docker"
fi

echo
log_info "💡 性能优化提示："
echo "  • 使用较小的基础镜像 (如 alpine)"
echo "  • 利用 Docker 镜像分层缓存"
echo "  • 定期清理无用镜像: docker system prune"
echo "  • 查看镜像使用: docker system df"

echo
log_info "测试完成！"
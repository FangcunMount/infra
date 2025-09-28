#!/usr/bin/env bash
set -euo pipefail

# 服务器网络环境初始化脚本
# 配置 mihomo (Clash.Meta) VPN 客户端
# 支持重复执行，已安装的组件将被跳过
# 需要在 init-users.sh 执行完毕后运行

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

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

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

log_debug() {
    if [[ "${DEBUG:-}" == "true" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# 错误处理函数
handle_error() {
    local line_number=$1
    local last_command="${BASH_COMMAND}"
    log_error "脚本在第 $line_number 行执行失败"
    log_error "失败的命令: $last_command"
    
    # 提供常见错误的解决建议
    if [[ "$last_command" =~ apt-get ]]; then
        log_info "包安装失败，可能的原因："
        echo "  1. 网络连接问题"
        echo "  2. 软件源配置问题" 
        echo "  3. 磁盘空间不足"
        echo "  4. 权限不足（请确保使用 sudo 运行）"
    elif [[ "$last_command" =~ curl|wget ]]; then
        log_info "网络下载失败，可能的原因："
        echo "  1. 网络连接不稳定"
        echo "  2. DNS 解析问题"
        echo "  3. 防火墙阻止访问"
    fi
    
    log_info "清理可能的残留文件..."
    cleanup_on_error
    exit 1
}

# 错误清理函数
cleanup_on_error() {
    log_warn "安装过程中出现错误，进行清理..."
    
    # 停止并清理可能的残留
    if systemctl is-active --quiet mihomo.service 2>/dev/null; then
        systemctl stop mihomo.service 2>/dev/null || true
    fi
    
    echo
    log_warn "问题排查建议："
    echo "  1. 运行诊断工具: sudo ./scripts/diagnose-network.sh"
    echo "  2. 检查 mihomo 进程: ps aux | grep mihomo"
    echo "  3. 检查配置目录: ls -la /opt/mihomo/"
    echo "  4. 检查系统日志: journalctl -u mihomo.service --no-pager"
    echo "  5. 重新运行脚本: sudo $0"
    
    echo
    log_info "常见问题解决方案："
    echo "  - 网络问题: 检查网络连接和 DNS 设置"
    echo "  - 权限问题: 确保使用 sudo 运行脚本"  
    echo "  - 空间不足: 清理磁盘空间后重试"
    echo "  - 包管理器问题: 更新软件源后重试"
}

# 状态检查函数
check_mihomo_installed() {
    [[ -f "/usr/local/bin/mihomo" ]] && /usr/local/bin/mihomo -v >/dev/null 2>&1
}

check_directories_setup() {
    [[ -d "/opt/mihomo" ]] && [[ -d "/opt/mihomo/config" ]] && [[ -d "/opt/mihomo/data" ]]
}

check_geodata_downloaded() {
    [[ -f "/opt/mihomo/data/GeoSite.dat" ]] && [[ -f "/opt/mihomo/data/GeoIP.metadb" ]]
}

check_base_config_created() {
    [[ -f "/opt/mihomo/config/config.yaml" ]]
}

check_systemd_service_setup() {
    systemctl list-units --all --type=service | grep -q mihomo.service
}

check_mihomo_service_running() {
    systemctl is-active --quiet mihomo.service 2>/dev/null
}

check_global_proxy_setup() {
    [[ -f "/etc/profile.d/mihomo-proxy.sh" ]] || [[ -f "/etc/environment" ]] && grep -q "http_proxy" /etc/environment
}

check_management_scripts_created() {
    [[ -f "/usr/local/bin/mihomo-control" ]] && [[ -f "/usr/local/bin/diagnose-network.sh" ]]
}

# 可重复执行的安装步骤
install_mihomo_binary_repeatable() {
    if check_mihomo_installed; then
        log_success "✅ mihomo 二进制文件已安装，跳过安装步骤"
        return 0
    fi

    log_step "安装 mihomo 二进制文件..."
    install_mihomo_binary
}

setup_directories_repeatable() {
    if check_directories_setup; then
        log_success "✅ 配置目录已创建，跳过目录创建步骤"
        return 0
    fi

    log_step "创建配置目录..."
    setup_directories
}

download_geodata_repeatable() {
    if check_geodata_downloaded; then
        log_success "✅ 地理位置数据文件已下载，跳过下载步骤"
        return 0
    fi

    log_step "下载地理位置数据文件..."
    download_geodata
}

create_base_config_repeatable() {
    if check_base_config_created; then
        log_success "✅ 基础配置文件已创建，跳过配置步骤"
        return 0
    fi

    log_step "创建基础配置文件..."
    create_base_config
}

setup_systemd_service_repeatable() {
    if check_systemd_service_setup; then
        log_success "✅ systemd 服务已配置，跳过服务配置步骤"
        return 0
    fi

    log_step "配置 systemd 服务..."
    setup_systemd_service
}

start_mihomo_service_repeatable() {
    if check_mihomo_service_running; then
        log_success "✅ mihomo 服务正在运行，跳过启动步骤"
        return 0
    fi

    log_step "启动 mihomo 服务..."
    start_mihomo_service
}

setup_global_proxy_repeatable() {
    if check_global_proxy_setup; then
        log_success "✅ 全局代理环境变量已配置，跳过代理配置步骤"
        return 0
    fi

    log_step "配置全局代理环境变量..."
    setup_global_proxy
}

create_management_scripts_repeatable() {
    if check_management_scripts_created; then
        log_success "✅ 管理脚本已创建，跳过脚本创建步骤"
        return 0
    fi

    log_step "创建管理脚本..."
    create_management_scripts
}

# 检查运行环境
check_prerequisites() {
    log_step "检查运行环境..."
    
    # 检查是否为 root 用户
    if [[ ${EUID} -ne 0 ]]; then
        log_error "此脚本必须以 root 用户身份运行"
        echo "使用方法: sudo $0"
        exit 1
    fi
    
    # 检查操作系统（仅支持 Ubuntu）
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法检测操作系统信息"
        exit 1
    fi
    
    local os_id=$(grep '^ID=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    local os_name=$(grep '^PRETTY_NAME=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    
    if [[ "$os_id" != "ubuntu" ]]; then
        log_error "此脚本仅支持 Ubuntu 系统"
        log_error "当前系统: $os_name"
        log_info "如需支持其他系统，请修改脚本或使用对应的安装方法"
        exit 1
    fi
    
    log_success "✅ 系统检查通过: $os_name"
    
    # 检查基本的系统权限和工具
    if ! touch /tmp/network-setup-test 2>/dev/null; then
        log_error "无法创建临时文件，请检查系统权限"
        exit 1
    fi
    rm -f /tmp/network-setup-test
    
    # 检查网络连接（内网环境）
    log_info "检查内网环境..."
    local is_intranet=true
    
    # 检测是否为内网环境（无法访问外网）
    if ! ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1 && ! ping -c 1 -W 3 114.114.114.114 >/dev/null 2>&1; then
        log_warn "检测到内网环境，无法访问外网"
        log_info "脚本将使用内网适配模式运行"
        is_intranet=true
    else
        log_success "网络连接正常，可访问外网"
        is_intranet=false
    fi
    
    # 导出变量供后续函数使用
    export IS_INTRANET=$is_intranet
    
    # 检查 Linux 内核版本（Docker 要求）
    local kernel_version
    kernel_version=$(uname -r | cut -d. -f1-2)
    local kernel_major
    kernel_major=$(echo "$kernel_version" | cut -d. -f1)
    local kernel_minor
    kernel_minor=$(echo "$kernel_version" | cut -d. -f2)
    
    log_info "内核版本: $kernel_version（符合要求）"
    
    log_info "使用 Ubuntu 包管理器: apt-get"
    
    # 显示系统信息
    log_info "系统信息："
    echo "  - 操作系统: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'=' -f2 | tr -d '"')"
    echo "  - 内核版本: $(uname -r)"
    echo "  - 架构: $(uname -m)"
    echo "  - 用户: $(whoami)"
    echo "  - 磁盘空间: $(df -h / | awk 'NR==2 {print $4}') 可用"
    
    # 检查必要的工具
    local basic_tools=("curl" "wget" "jq" "python3")
    local missing_tools=()
    
    for tool in "${basic_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_tools+=("$tool")
        fi
    done
    
    # 安装缺失的基础工具
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        if [[ "$IS_INTRANET" == "true" ]]; then
            log_warn "内网环境检测到缺失工具: ${missing_tools[*]}"
            log_error "内网环境无法自动安装依赖包，请手动安装："
            for tool in "${missing_tools[@]}"; do
                echo "  - $tool: sudo apt-get install -y $tool"
            done
            echo
            log_info "或者配置内网软件源后重新运行脚本"
            exit 1
        else
            log_warn "需要安装以下工具: ${missing_tools[*]}"
            log_info "更新包管理器缓存..."
            if ! apt-get update >/dev/null 2>&1; then
                log_error "更新包管理器缓存失败"
                exit 1
            fi
            
            for tool in "${missing_tools[@]}"; do
                log_info "安装 $tool..."
                if ! apt-get install -y "$tool" 2>/dev/null; then
                    log_error "安装 $tool 失败"
                    log_info "请手动安装: sudo apt-get install -y $tool"
                    exit 1
                fi
                log_success "$tool 安装成功"
            done
        fi
    fi
    
    # 单独处理 pip 安装
    if ! command -v pip3 >/dev/null 2>&1 && ! python3 -m pip --version >/dev/null 2>&1; then
        if [[ "$IS_INTRANET" == "true" ]]; then
            log_warn "内网环境缺少 pip，请手动安装:"
            echo "  sudo apt-get install python3-pip"
            exit 1
        else
            log_info "安装 Python pip..."
            if ! apt-get install -y python3-pip 2>/dev/null; then
                log_warn "通过包管理器安装 pip 失败，尝试其他方法..."
                if curl -fsSL https://bootstrap.pypa.io/get-pip.py | python3; then
                    log_success "pip 安装成功（使用 get-pip.py）"
                else
                    log_error "pip 安装失败"
                    exit 1
                fi
            else
                log_success "pip 安装成功"
            fi
        fi
    fi
    
    # 检查并安装 PyYAML
    if ! python3 -c "import yaml" >/dev/null 2>&1; then
        if [[ "$IS_INTRANET" == "true" ]]; then
            log_warn "内网环境缺少 PyYAML，请手动安装:"
            echo "  方法1: sudo apt-get install python3-yaml"
            echo "  方法2: 下载离线包安装"
            echo "  或者跳过 YAML 验证（脚本将继续运行但不验证配置文件）"
            read -p "是否跳过 YAML 验证继续运行？(y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
            log_warn "已跳过 PyYAML 安装，配置文件验证功能将被禁用"
            export SKIP_YAML_VALIDATION=true
        else
            log_info "安装 PyYAML..."
            if ! python3 -m pip install PyYAML >/dev/null 2>&1; then
                log_error "PyYAML 安装失败"
                log_info "请手动安装: python3 -m pip install PyYAML"
                exit 1
            fi
            log_success "PyYAML 安装成功"
        fi
    fi
    
    log_success "环境检查通过"
}

# 安装 mihomo 二进制文件
install_mihomo_binary() {
    log_step "安装 mihomo 二进制文件..."
    
    local mihomo_dir="/usr/local/bin"
    local mihomo_binary="$mihomo_dir/mihomo"
    local temp_dir="/tmp/mihomo-install"
    
    # 检查是否已安装
    if [[ -f "$mihomo_binary" ]] && "$mihomo_binary" -v >/dev/null 2>&1; then
        local current_version
        current_version=$("$mihomo_binary" -v 2>/dev/null | head -1 || echo "unknown")
        log_success "✅ mihomo 已安装: $current_version"
        return 0
    fi
    
    # 检测系统架构
    local arch
    case "$(uname -m)" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        armv7l)  arch="armv7" ;;
        *)
            log_error "不支持的系统架构: $(uname -m)"
            exit 1
            ;;
    esac
    
    log_info "系统架构: $arch"
    
    # 检查本地静态文件
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local static_dir="$script_dir/static"
    local static_binary="$static_dir/mihomo-linux-$arch"
    
    log_info "检查本地静态文件..."
    log_info "静态文件目录: $static_dir"
    log_info "目标文件: mihomo-linux-$arch"
    
    # 列出 static 目录中的 mihomo 相关文件
    if [[ -d "$static_dir" ]]; then
        local mihomo_files
        mihomo_files=$(ls -la "$static_dir"/mihomo* 2>/dev/null || true)
        if [[ -n "$mihomo_files" ]]; then
            log_info "发现的 mihomo 文件:"
            echo "$mihomo_files" | while read -r line; do
                echo "  $line"
            done
        else
            log_info "static 目录中没有找到 mihomo 文件"
        fi
    else
        log_warn "静态文件目录不存在: $static_dir"
    fi
    
    # 创建临时目录
    rm -rf "$temp_dir"
    mkdir -p "$temp_dir"
    cd "$temp_dir"
    
    # 优先使用本地静态文件
    if [[ -f "$static_binary" ]]; then
        log_success "✅ 找到本地静态二进制文件: $static_binary"
        
        # 检查文件大小
        local file_size
        file_size=$(stat -c%s "$static_binary" 2>/dev/null || stat -f%z "$static_binary" 2>/dev/null || echo "0")
        log_info "文件大小: $(( file_size / 1024 / 1024 )) MB"
        
        # 检查文件权限
        if [[ -x "$static_binary" ]]; then
            log_info "文件已具有执行权限"
        else
            log_info "文件需要添加执行权限"
        fi
        
        log_info "使用本地静态二进制文件..."
        cp "$static_binary" mihomo
        chmod +x mihomo
        
        # 验证复制的文件
        if [[ -f "mihomo" ]]; then
            log_success "✅ 本地静态文件复制成功"
        else
            log_error "本地静态文件复制失败"
            exit 1
        fi
    else
        log_warn "❌ 未找到本地静态二进制文件: $static_binary"
        
        # 提供详细的解决方案
        echo
        log_info "解决方案："
        echo "  方案1 - 使用预下载脚本（推荐）:"
        echo "    ./download-mihomo-binaries.sh"
        echo
        echo "  方案2 - 手动下载到 static 目录:"
        echo "    mkdir -p $static_dir"
        echo "    # 然后下载对应架构的文件到:"
        echo "    # $static_binary"
        echo
        echo "  方案3 - 在线下载（需要网络连接）"
        echo
        
        # 从 GitHub 下载
        if [[ "$IS_INTRANET" == "true" ]]; then
            log_error "内网环境无法在线下载，请使用方案1或方案2"
            exit 1
        fi
        
        log_info "获取 mihomo 最新版本..."
        local latest_version
        if latest_version=$(curl -s --connect-timeout 10 --max-time 20 "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest" | grep '"tag_name"' | cut -d'"' -f4); then
            log_info "最新版本: $latest_version"
        else
            log_warn "无法获取最新版本，使用 latest 下载链接"
            latest_version="latest"
        fi
        
        local download_url
        if [[ "$latest_version" == "latest" ]]; then
            # 使用 latest 重定向链接（GitHub 会自动重定向到最新版本）
            download_url="https://github.com/MetaCubeX/mihomo/releases/latest/download/mihomo-linux-$arch.gz"
        else
            # 使用具体版本号
            download_url="https://github.com/MetaCubeX/mihomo/releases/download/$latest_version/mihomo-linux-$arch-$latest_version.gz"
        fi
        
        log_info "从 GitHub 下载 mihomo..."
        log_info "下载地址: $download_url"
        
        local downloaded_filename
        if [[ "$latest_version" == "latest" ]]; then
            downloaded_filename="mihomo-linux-$arch.gz"
        else
            downloaded_filename="mihomo-linux-$arch-$latest_version.gz"
        fi
        
        if ! curl -fsSL --connect-timeout 10 --max-time 60 "$download_url" -o "$downloaded_filename"; then
            log_error "mihomo 二进制文件下载失败"
            log_info "您可以："
            echo "  1. 检查网络连接"
            echo "  2. 使用预下载脚本: ./download-mihomo-binaries.sh"  
            echo "  3. 手动下载到 static 目录后重新运行"
            exit 1
        fi
        
        log_info "解压二进制文件..."
        if [[ -f "$downloaded_filename" ]]; then
            gunzip "$downloaded_filename"
            # 处理解压后的文件名
            local extracted_name
            if [[ "$latest_version" == "latest" ]]; then
                extracted_name="mihomo-linux-$arch"
            else
                extracted_name="mihomo-linux-$arch-$latest_version"
            fi
            
            if [[ -f "$extracted_name" ]]; then
                mv "$extracted_name" mihomo
            elif [[ -f "mihomo-linux-$arch" ]]; then
                mv "mihomo-linux-$arch" mihomo
            else
                log_error "解压后的文件未找到"
                exit 1
            fi
        else
            log_error "下载的文件不存在: $downloaded_filename"
            exit 1
        fi
        
        chmod +x mihomo
        
        # 显示下载文件信息
        if [[ -f "mihomo" ]]; then
            local file_size=$(stat -c%s "mihomo" 2>/dev/null || stat -f%z "mihomo" 2>/dev/null || echo "0")
            local file_size_mb=$((file_size / 1024 / 1024))
            log_success "✅ 在线下载完成 (${file_size_mb}MB)"
        fi
    fi
    
    # 验证二进制文件
    log_info "验证 mihomo 二进制文件..."
    if ! ./mihomo -v >/dev/null 2>&1; then
        log_error "mihomo 二进制文件验证失败"
        exit 1
    fi
    
    log_success "✅ mihomo 二进制文件验证通过"
    
    # 安装到系统目录
    log_info "安装 mihomo 到 $mihomo_binary..."
    cp mihomo "$mihomo_binary"
    chmod +x "$mihomo_binary"
    
    # 验证安装
    if "$mihomo_binary" -v >/dev/null 2>&1; then
        local version
        version=$("$mihomo_binary" -v | head -1)
        log_success "✅ mihomo 安装成功"
        log_info "版本信息: $version"
        log_info "安装位置: $mihomo_binary"
    else
        log_error "mihomo 安装验证失败"
        exit 1
    fi
    
    # 清理临时文件
    log_debug "清理临时目录: $temp_dir"
    cd /
    rm -rf "$temp_dir"
    log_debug "临时文件清理完成"
    
    log_success "mihomo 二进制文件安装完成"
}

# 创建配置目录
setup_directories() {
    log_step "创建配置目录..."
    
    local mihomo_dir="/opt/mihomo"
    local config_dir="$mihomo_dir/config"
    local data_dir="$mihomo_dir/data"
    
    mkdir -p "$config_dir"
    mkdir -p "$data_dir"
    
    # 设置权限
    chmod 755 "$mihomo_dir"
    chmod 755 "$config_dir" 
    chmod 755 "$data_dir"
    
    log_success "配置目录创建完成: $mihomo_dir"
}

# 下载单个文件的函数
download_file_with_fallback() {
    local filename="$1"
    local output_path="$2"
    local urls=("${@:3}")
    
    log_info "下载 $filename..."
    
    # 尝试多个下载源
    for url in "${urls[@]}"; do
        log_info "  尝试从: $url"
        
        # 尝试使用 wget
        if command -v wget >/dev/null 2>&1; then
            if wget -q --timeout=20 --tries=2 "$url" -O "$output_path.tmp"; then
                # 验证文件完整性（检查文件大小）
                local file_size
                file_size=$(stat -c%s "$output_path.tmp" 2>/dev/null || stat -f%z "$output_path.tmp" 2>/dev/null || echo "0")
                if [[ "$file_size" -gt 1000 ]]; then
                    mv "$output_path.tmp" "$output_path"
                    log_success "✅ $filename 下载完成（使用 wget）"
                    return 0
                else
                    log_warn "  下载文件过小，可能下载不完整"
                    rm -f "$output_path.tmp"
                fi
            fi
        fi
        
        # 尝试使用 curl
        if command -v curl >/dev/null 2>&1; then
            if curl -fsSL --connect-timeout 10 --max-time 60 "$url" -o "$output_path.tmp"; then
                # 验证文件完整性
                local file_size
                file_size=$(stat -c%s "$output_path.tmp" 2>/dev/null || stat -f%z "$output_path.tmp" 2>/dev/null || echo "0")
                if [[ "$file_size" -gt 1000 ]]; then
                    mv "$output_path.tmp" "$output_path"
                    log_success "✅ $filename 下载完成（使用 curl）"
                    return 0
                else
                    log_warn "  下载文件过小，可能下载不完整"
                    rm -f "$output_path.tmp"
                fi
            fi
        fi
        
        log_warn "  从该源下载失败，尝试下一个源..."
    done
    
    # 清理临时文件
    rm -f "$output_path.tmp"
    return 1
}

# 创建基础规则文件（当地理数据文件不可用时）
create_basic_rules() {
    local data_dir="$1"
    
    log_warn "创建基础规则配置文件..."
    
    # 创建基础的 GeoSite.dat 替代配置
    cat > "$data_dir/basic-rules.yaml" << 'EOF'
# 基础规则配置（当 GeoSite.dat 不可用时）
# 这些规则提供基本的分流功能

# 国内常用域名
domestic_domains:
  - baidu.com
  - qq.com
  - taobao.com
  - tmall.com
  - jd.com
  - weibo.com
  - sina.com.cn
  - 163.com
  - sohu.com
  - youku.com
  - iqiyi.com
  - bilibili.com
  - zhihu.com
  - douban.com

# 国外常用域名
foreign_domains:
  - google.com
  - youtube.com
  - facebook.com
  - twitter.com
  - instagram.com
  - github.com
  - stackoverflow.com
  - reddit.com
  - netflix.com
  - amazon.com
EOF
    
    log_info "基础规则文件已创建: $data_dir/basic-rules.yaml"
}

# 为内网环境创建基础配置
create_basic_config_intranet() {
    local config_file="/opt/mihomo/config/config.yaml"
    
    log_info "为内网环境创建基础配置..."
    
    cat > "$config_file" << 'EOF'
# Mihomo (Clash.Meta) 基础配置 - 内网环境
# 此配置适用于无外网订阅链接的内网环境

# 基础设置
port: 7890
socks-port: 7891
redir-port: 7892
mixed-port: 7893
allow-lan: true
bind-address: '*'
mode: rule
log-level: info
ipv6: false
external-controller: 0.0.0.0:9090
external-ui: dashboard

# DNS 配置
dns:
  enable: true
  ipv6: false
  listen: 0.0.0.0:53
  default-nameserver:
    - 114.114.114.114
    - 8.8.8.8
  nameserver:
    - https://doh.pub/dns-query
    - https://dns.alidns.com/dns-query
  fallback:
    - https://1.1.1.1/dns-query
    - https://dns.google/dns-query

# 代理节点（需要手动配置）
proxies:
  # 示例节点配置 - 请根据实际情况修改
  - name: "本地代理"
    type: http
    server: 127.0.0.1
    port: 8080
    # username: user
    # password: pass
  
  # 添加更多代理节点...

# 代理组
proxy-groups:
  - name: "🚀 节点选择"
    type: select
    proxies:
      - "本地代理"
      - DIRECT
  
  - name: "🌍 国外网站"
    type: select
    proxies:
      - "🚀 节点选择"
      - DIRECT
  
  - name: "🐟 漏网之鱼"
    type: select
    proxies:
      - "🚀 节点选择"
      - DIRECT

# 分流规则
rules:
  # 本地网络直连
  - IP-CIDR,127.0.0.0/8,DIRECT
  - IP-CIDR,172.16.0.0/12,DIRECT
  - IP-CIDR,192.168.0.0/16,DIRECT
  - IP-CIDR,10.0.0.0/8,DIRECT
  - IP-CIDR,169.254.0.0/16,DIRECT
  - IP-CIDR,224.0.0.0/4,DIRECT
  - IP-CIDR,240.0.0.0/4,DIRECT
  
  # 常见国外网站
  - DOMAIN-SUFFIX,google.com,🌍 国外网站
  - DOMAIN-SUFFIX,youtube.com,🌍 国外网站
  - DOMAIN-SUFFIX,facebook.com,🌍 国外网站
  - DOMAIN-SUFFIX,twitter.com,🌍 国外网站
  - DOMAIN-SUFFIX,github.com,🌍 国外网站
  - DOMAIN-SUFFIX,stackoverflow.com,🌍 国外网站
  - DOMAIN-SUFFIX,wikipedia.org,🌍 国外网站
  
  # 国内网站直连
  - DOMAIN-SUFFIX,baidu.com,DIRECT
  - DOMAIN-SUFFIX,qq.com,DIRECT
  - DOMAIN-SUFFIX,taobao.com,DIRECT
  - DOMAIN-SUFFIX,jd.com,DIRECT
  - DOMAIN-SUFFIX,weibo.com,DIRECT
  - DOMAIN-SUFFIX,bilibili.com,DIRECT
  - DOMAIN-SUFFIX,zhihu.com,DIRECT
  
  # 中国大陆 IP 直连
  - IP-CIDR,1.0.1.0/24,DIRECT
  - IP-CIDR,1.0.2.0/23,DIRECT
  - IP-CIDR,1.0.8.0/21,DIRECT
  - IP-CIDR,1.0.32.0/19,DIRECT
  - IP-CIDR,1.1.0.0/24,DIRECT
  
  # 其他流量
  - MATCH,🐟 漏网之鱼
EOF
    
    log_success "基础内网配置已创建: $config_file"
    log_warn "⚠️  请根据实际网络环境修改代理节点配置"
    echo "   编辑文件: $config_file"
    echo "   在 proxies 部分添加您的代理服务器信息"
}

# 下载必要的数据文件
download_geodata() {
    log_step "处理地理位置数据文件..."
    
    local data_dir="/opt/mihomo/data"
    local download_success=true
    
    # 获取脚本所在目录（从 scripts/init-server/ 到项目根目录）
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local static_dir="$script_dir/static"
    
    # 检查本地静态文件（支持大小写变体）
    local has_static_files=false
    local static_geosite=""
    local static_geoip=""
    
    # 检查 GeoSite 文件（优先大写，然后小写）
    if [[ -f "$static_dir/GeoSite.dat" ]]; then
        static_geosite="$static_dir/GeoSite.dat"
    elif [[ -f "$static_dir/geosite.dat" ]]; then
        static_geosite="$static_dir/geosite.dat"
    fi
    
    # 检查 GeoIP 文件（优先大写，然后小写）
    if [[ -f "$static_dir/GeoIP.metadb" ]]; then
        static_geoip="$static_dir/GeoIP.metadb"
    elif [[ -f "$static_dir/geoip.metadb" ]]; then
        static_geoip="$static_dir/geoip.metadb"
    fi
    
    if [[ -n "$static_geosite" ]] && [[ -n "$static_geoip" ]]; then
        has_static_files=true
        log_success "✅ 发现本地静态地理数据文件"
        log_info "静态文件位置: $static_dir"
        log_info "  GeoSite: $(basename "$static_geosite")"
        log_info "  GeoIP: $(basename "$static_geoip")"
    fi
    
    # 检查目标目录已有文件
    local has_existing_files=false
    if [[ -f "$data_dir/GeoSite.dat" ]] && [[ -f "$data_dir/GeoIP.metadb" ]]; then
        has_existing_files=true
        log_info "✅ 目标目录已存在地理数据文件"
    fi
    
    # 优先使用本地静态文件
    if [[ "$has_static_files" == "true" ]]; then
        log_info "使用本地静态文件..."
        
        # 复制 GeoSite.dat
        if cp "$static_geosite" "$data_dir/GeoSite.dat" 2>/dev/null; then
            log_success "✅ GeoSite.dat 复制成功"
        else
            log_error "❌ GeoSite.dat 复制失败"
            download_success=false
        fi
        
        # 复制 GeoIP.metadb  
        if cp "$static_geoip" "$data_dir/GeoIP.metadb" 2>/dev/null; then
            log_success "✅ GeoIP.metadb 复制成功"
        else
            log_error "❌ GeoIP.metadb 复制失败"
            download_success=false
        fi
        
        if [[ "$download_success" == "true" ]]; then
            log_success "✅ 本地静态地理数据文件部署完成"
            return 0
        fi
    fi
    
    # 如果已有文件且静态文件不可用，询问是否使用现有文件
    if [[ "$has_existing_files" == "true" ]]; then
        log_info "目标目录已存在地理数据文件"
        read -p "是否使用现有文件？(Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            log_success "✅ 使用现有地理数据文件"
            return 0
        fi
    fi
    
    # 内网环境处理（当没有静态文件时）
    if [[ "$IS_INTRANET" == "true" ]]; then
        log_warn "内网环境且无本地静态文件"
        log_info "内网环境选项："
        echo "  1. 创建基础规则配置（推荐）"  
        echo "  2. 手动上传文件到 $data_dir/"
        echo "  3. 跳过地理数据文件（功能受限）"
        
        while true; do
            read -p "请选择处理方式 (1/2/3): " -n 1 -r choice
            echo
            case $choice in
                1)
                    create_basic_rules "$data_dir"
                    log_info "✅ 已创建基础规则，Clash 将使用基本分流功能"
                    break
                    ;;
                2)
                    echo
                    log_info "手动上传指南："
                    echo "  方案1 - 使用本地静态文件（推荐）："
                    echo "    1. 在有网络的机器上下载文件到项目 static/ 目录"
                    echo "    2. 重新运行脚本，将自动使用静态文件"
                    echo
                    echo "  方案2 - 直接上传到目标目录："
                    echo "    1. 下载文件："
                    echo "       GeoSite.dat: https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat"
                    echo "       GeoIP.metadb: https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb"
                    echo "    2. 上传到服务器目录: $data_dir/"
                    echo "    3. 设置权限: chmod 644 $data_dir/*.dat $data_dir/*.metadb"
                    echo "    4. 重新运行脚本"
                    read -p "按 Enter 键继续安装..." 
                    break
                    ;;
                3)
                    log_warn "⚠️  跳过地理数据文件，部分规则功能将不可用"
                    break
                    ;;
                *)
                    echo "请输入 1、2 或 3"
                    ;;
            esac
        done
    else
        # 外网环境，正常下载
        # 定义多个下载源
        local geosite_urls=(
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat"
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat"
            "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geosite.dat"
            "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"
        )
        
        local geoip_urls=(
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb"
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb" 
            "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geoip.metadb"
            "https://github.com/MetaCubeX/meta-rules-dat/releases/latest/download/geoip-lite.metadb"
        )
        
        # 下载 GeoSite.dat
        if [[ ! -f "$data_dir/GeoSite.dat" ]]; then
            if ! download_file_with_fallback "GeoSite.dat" "$data_dir/GeoSite.dat" "${geosite_urls[@]}"; then
                log_error "❌ GeoSite.dat 从所有源下载失败"
                download_success=false
            fi
        else
            log_info "✅ GeoSite.dat 已存在，跳过下载"
        fi
        
        # 下载 GeoIP.metadb
        if [[ ! -f "$data_dir/GeoIP.metadb" ]]; then
            if ! download_file_with_fallback "GeoIP.metadb" "$data_dir/GeoIP.metadb" "${geoip_urls[@]}"; then
                log_error "❌ GeoIP.metadb 从所有源下载失败"
                download_success=false
            fi
        else
            log_info "✅ GeoIP.metadb 已存在，跳过下载"
        fi
        
        # 如果下载失败，提供备用方案
    if [[ "$download_success" == "false" ]]; then
        log_warn "⚠️  部分地理数据文件下载失败"
        echo
        log_info "备用解决方案："
        echo "  1. 创建基础规则配置（推荐）"
        echo "  2. 跳过地理数据文件（功能受限）"
        echo "  3. 手动下载文件"
        echo
        
        while true; do
            read -p "请选择处理方式 (1/2/3): " -n 1 -r choice
            echo
            case $choice in
                1)
                    create_basic_rules "$data_dir"
                    log_info "✅ 已创建基础规则，Clash 将使用基本分流功能"
                    break
                    ;;
                2)
                    log_warn "⚠️  跳过地理数据文件，部分规则功能将不可用"
                    log_info "💡 可以后续手动下载或使用 mihomo-update-geodata 命令"
                    break
                    ;;
                3)
                    echo
                    log_info "手动下载指南："
                    echo "  1. 下载 GeoSite.dat:"
                    echo "     wget -O $data_dir/GeoSite.dat 'https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat'"
                    echo
                    echo "  2. 下载 GeoIP.metadb:"
                    echo "     wget -O $data_dir/GeoIP.metadb 'https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb'"
                    echo
                    echo "  3. 下载后重启服务:"
                    echo "     mihomo-control restart"
                    echo
                    read -p "按 Enter 键继续安装..." 
                    break
                    ;;
                *)
                    echo "请输入 1、2 或 3"
                    ;;
            esac
        done
    fi
    fi  # 结束外网环境的 else 分支
    
    # 设置文件权限
    chmod 644 "$data_dir"/*.dat "$data_dir"/*.metadb "$data_dir"/*.yaml 2>/dev/null || true
    
    log_success "地理数据文件处理完成"
}

# 创建基础配置文件
create_base_config() {
    log_step "创建基础配置文件..."
    
    local config_file="/opt/mihomo/config/config.yaml"
    
    cat > "$config_file" << 'EOF'
# Mihomo (Clash.Meta) 配置文件
# 混合端口配置
mixed-port: 7890
allow-lan: true
mode: rule
log-level: info
external-controller: 127.0.0.1:9090
external-ui: ui
secret: ""

# DNS 配置
dns:
  enable: true
  listen: 0.0.0.0:53
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - 223.5.5.5
    - 114.114.114.114
  fallback:
    - 8.8.8.8
    - 1.1.1.1

# 代理组配置（将在订阅更新时覆盖）
proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - "DIRECT"
  
  - name: "AUTO"
    type: url-test
    proxies:
      - "DIRECT"
    url: 'http://www.gstatic.com/generate_204'
    interval: 300

# 规则配置
rules:
  # 局域网直连
  - IP-CIDR,192.168.0.0/16,DIRECT
  - IP-CIDR,10.0.0.0/8,DIRECT
  - IP-CIDR,172.16.0.0/12,DIRECT
  - IP-CIDR,127.0.0.0/8,DIRECT
  
  # 国内网站直连
  - GEOSITE,cn,DIRECT
  - GEOIP,cn,DIRECT
  
  # 其他走代理
  - MATCH,PROXY

# 代理配置（将在订阅更新时覆盖）
proxies: []
EOF

    log_success "基础配置文件创建完成"
}

# 验证配置文件
validate_config() {
    local config_file="$1"
    
    if [[ ! -f "$config_file" ]]; then
        log_error "配置文件不存在: $config_file"
        return 1
    fi
    
    # 验证 YAML 格式
    if ! python3 -c "import yaml; yaml.safe_load(open('$config_file'))" 2>/dev/null; then
        log_error "配置文件 YAML 格式无效: $config_file"
        return 1
    fi
    
    # 验证必要的配置项
    local required_fields=("mixed-port" "mode")
    for field in "${required_fields[@]}"; do
        if ! grep -q "^$field:" "$config_file"; then
            log_error "配置文件缺少必要字段: $field"
            return 1
        fi
    done
    
    # 检查端口冲突（7890 和 9090）
    local ports_to_check=("7890" "9090")
    for port in "${ports_to_check[@]}"; do
        if netstat -tln 2>/dev/null | grep -q ":$port " || ss -tln 2>/dev/null | grep -q ":$port "; then
            # 检查是否是 mihomo 自己使用的端口
            if ! docker ps | grep -q mihomo || ! netstat -tlnp 2>/dev/null | grep ":$port " | grep -q docker; then
                log_warn "端口 $port 已被其他进程占用"
                netstat -tlnp 2>/dev/null | grep ":$port " || ss -tlnp 2>/dev/null | grep ":$port " || true
            fi
        fi
    done
    
    log_success "配置文件验证通过: $config_file"
    return 0
}

# 获取订阅链接并更新配置
update_subscription_repeatable() {
    # 检查是否已有有效的配置文件
    local config_file="/opt/mihomo/config/config.yaml"
    if [[ -f "$config_file" ]] && validate_config "$config_file" 2>/dev/null; then
        log_info "检测到已存在的配置文件"
        echo
        read -p "是否要更新 VPN 订阅配置？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_success "✅ 跳过订阅更新，使用现有配置"
            return 0
        fi
    fi

    log_step "配置 VPN 订阅..."
    
    local subscription_url=""
    
    while true; do
        echo
        read -p "请输入 Clash 订阅链接: " subscription_url
        
        if [[ -z "$subscription_url" ]]; then
            log_warn "订阅链接不能为空，请重新输入"
            continue
        fi
        
        if [[ ! "$subscription_url" =~ ^https?:// ]]; then
            log_warn "订阅链接格式不正确，请输入完整的 HTTP/HTTPS 链接"
            continue
        fi
        
        break
    done
    
    if [[ "$IS_INTRANET" == "true" ]]; then
        log_warn "⚠️  内网环境无法直接下载订阅配置"
        echo
        log_info "内网环境解决方案："
        echo "  1. 手动下载配置文件"
        echo "  2. 使用基础配置（本地分流）"
        echo "  3. 跳过订阅配置"
        echo
        
        while true; do
            read -p "请选择处理方式 (1/2/3): " -n 1 -r choice
            echo
            case $choice in
                1)
                    echo
                    log_info "手动配置步骤："
                    echo "  1. 在有网络的设备上访问: $subscription_url"
                    echo "  2. 保存配置文件为 clash_config.yaml"
                    echo "  3. 上传到服务器 /opt/mihomo/config/config.yaml"
                    echo "  4. 设置权限: chmod 644 /opt/mihomo/config/config.yaml"
                    echo "  5. 重新运行脚本或跳过此步骤"
                    read -p "按 Enter 键继续..."
                    return 0
                    ;;
                2)
                    log_info "创建基础本地配置..."
                    create_basic_config_intranet
                    return 0
                    ;;
                3)
                    log_warn "跳过订阅配置，需要稍后手动配置"
                    return 0
                    ;;
                *)
                    echo "请输入 1、2 或 3"
                    ;;
            esac
        done
    else
        log_info "正在下载订阅配置..."
        
        local temp_config="/tmp/clash_subscription.yaml"
        
        # 下载订阅配置
        if ! curl -fsSL --connect-timeout 10 --max-time 30 \
            -H "User-Agent: clash.meta" \
            "$subscription_url" -o "$temp_config"; then
            log_error "订阅配置下载失败，请检查网络连接和订阅链接"
            exit 1
        fi
        
        # 验证下载的配置文件
        if ! validate_config "$temp_config"; then
            log_error "下载的订阅配置验证失败"
            rm -f "$temp_config"
            exit 1
        fi
    fi
    
    # 备份现有配置
    if [[ -f "$config_file" ]]; then
        local backup_file="$config_file.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$config_file" "$backup_file"
        log_info "已备份现有配置到: $backup_file"
    fi
    
    # 更新配置
    cp "$temp_config" "$config_file"
    rm -f "$temp_config"
    
    log_success "订阅配置更新完成"
    
    # 保存订阅链接以便后续更新
    echo "$subscription_url" > "/opt/mihomo/subscription_url.txt"
    chmod 600 "/opt/mihomo/subscription_url.txt"
}

# 配置 systemd 服务
setup_systemd_service() {
    log_step "配置 mihomo systemd 服务..."
    
    # 创建 mihomo 用户（安全考虑）
    if ! id mihomo >/dev/null 2>&1; then
        log_info "创建 mihomo 系统用户..."
        useradd -r -s /bin/false -d /opt/mihomo mihomo
        chown -R mihomo:mihomo /opt/mihomo
    fi
    
    # 创建 systemd 服务文件
    local service_file="/etc/systemd/system/mihomo.service"
    
    cat > "$service_file" << 'EOF'
[Unit]
Description=Mihomo (Clash.Meta) Proxy Service
Documentation=https://wiki.metacubex.one/
After=network.target
Wants=network.target

[Service]
Type=simple
User=mihomo
Group=mihomo
ExecStart=/usr/local/bin/mihomo -d /opt/mihomo/config
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
LimitNOFILE=1048576

# 安全设置
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/mihomo
ProtectHome=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

    # 重新加载 systemd 配置
    systemctl daemon-reload
    
    # 启用服务（开机自启动）
    systemctl enable mihomo.service
    
    log_success "systemd 服务配置完成"
}

# 启动 mihomo 服务
start_mihomo_service() {
    log_step "启动 mihomo 服务..."
    
    # 验证配置文件
    if [[ ! -f "/opt/mihomo/config/config.yaml" ]]; then
        log_error "配置文件不存在: /opt/mihomo/config/config.yaml"
        exit 1
    fi
    
    # 通过 systemd 启动服务
    log_info "启动 mihomo 服务（混合端口 7890）..."
    systemctl start mihomo.service
    
    # 等待服务启动
    sleep 5
    
    # 检查服务状态
    if systemctl is-active --quiet mihomo.service; then
        log_success "✅ mihomo 服务启动成功"
        
        # 检查端口是否监听
        local port_check=0
        for i in {1..10}; do
            if netstat -tuln | grep -q ":7890 "; then
                log_success "✅ 代理端口 7890 已监听"
                port_check=1
                break
            fi
            sleep 1
        done
        
        if [[ $port_check -eq 0 ]]; then
            log_warn "⚠️  代理端口 7890 未监听，请检查配置"
        fi
        
        # 检查 API 端口
        if netstat -tuln | grep -q ":9090 "; then
            log_success "✅ 管理端口 9090 已监听"
        else
            log_warn "⚠️  管理端口 9090 未监听"
        fi
    else
        log_error "❌ mihomo 服务启动失败"
        echo
        log_info "诊断信息："
        echo "服务状态："
        systemctl status mihomo.service --no-pager || true
        echo
        echo "服务日志："
        journalctl -u mihomo.service --no-pager -n 10 || true
        exit 1
    fi
}

# 配置全局系统代理
setup_global_proxy() {
    log_step "配置全局代理环境变量..."
    
    # 创建全局代理配置文件
    local proxy_config="/etc/profile.d/clash-proxy.sh"
    
    log_info "创建全局代理配置文件: $proxy_config"
    
    tee "$proxy_config" > /dev/null << 'EOF'
# Global Clash Proxy Settings
# 自动加载代理环境变量
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export all_proxy="socks5://127.0.0.1:7890"
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
export ALL_PROXY="socks5://127.0.0.1:7890"

# 排除本地和局域网地址
export no_proxy="localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
export NO_PROXY="localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# 便捷的代理开关别名
alias proxy-on='export http_proxy=http://127.0.0.1:7890; export https_proxy=http://127.0.0.1:7890; export all_proxy=socks5://127.0.0.1:7890; export HTTP_PROXY=http://127.0.0.1:7890; export HTTPS_PROXY=http://127.0.0.1:7890; export ALL_PROXY=socks5://127.0.0.1:7890; echo "🟢 Proxy is ON"'
alias proxy-off='unset http_proxy; unset https_proxy; unset all_proxy; unset HTTP_PROXY; unset HTTPS_PROXY; unset ALL_PROXY; echo "🔴 Proxy is OFF"'
alias proxy-status='echo "Proxy Status:"; echo "  HTTP_PROXY: $http_proxy"; echo "  HTTPS_PROXY: $https_proxy"; echo "  ALL_PROXY: $all_proxy"'

# 显示代理加载信息
echo "🌐 Clash proxy environment loaded"
echo "   Use 'proxy-on' to enable proxy"
echo "   Use 'proxy-off' to disable proxy"
echo "   Use 'proxy-status' to check status"
EOF
    
    # 设置适当的权限
    chmod 644 "$proxy_config"
    
    # 应用代理设置到当前 shell
    source "$proxy_config"
    
    log_success "全局代理配置完成"
    log_info "所有用户登录时将自动加载代理环境变量"
    log_info "用户可以使用 proxy-on/proxy-off 命令控制代理状态"
}

# 测试网络连接
test_network_connectivity() {
    log_step "测试网络连接..."
    
    # 等待代理服务完全启动并进行健康检查
    log_info "等待代理服务初始化..."
    local max_wait=30
    local wait_count=0
    
    while [[ $wait_count -lt $max_wait ]]; do
        if netstat -tln 2>/dev/null | grep -q ":7890" || ss -tln 2>/dev/null | grep -q ":7890"; then
            log_success "代理端口 7890 已就绪"
            break
        fi
        sleep 2
        wait_count=$((wait_count + 2))
        echo -n "."
    done
    echo
    
    if [[ $wait_count -ge $max_wait ]]; then
        log_warn "代理端口 7890 启动超时，但继续进行测试..."
    fi
    
    local test_sites=("baidu.com" "github.com" "google.com")
    local proxy_url="http://127.0.0.1:7890"
    local success_count=0
    
    echo
    log_info "开始网络连接测试..."
    echo "----------------------------------------"
    
    for site in "${test_sites[@]}"; do
        echo -n "测试 $site ... "
        
        # 增加重试机制
        local retry_count=0
        local max_retries=2
        local test_success=false
        
        while [[ $retry_count -le $max_retries ]]; do
            if curl -s --connect-timeout 8 --max-time 12 \
                --proxy "$proxy_url" \
                "https://$site" >/dev/null 2>&1; then
                echo -e "${GREEN}✅ 成功${NC}"
                success_count=$((success_count + 1))
                test_success=true
                break
            fi
            retry_count=$((retry_count + 1))
            [[ $retry_count -le $max_retries ]] && sleep 2
        done
        
        if [[ "$test_success" == "false" ]]; then
            echo -e "${RED}❌ 失败${NC}"
        fi
    done
    
    echo "----------------------------------------"
    echo "测试结果: $success_count/${#test_sites[@]} 个站点连接成功"
    
    # 测试代理端口是否监听
    if netstat -tln 2>/dev/null | grep -q ":7890" || ss -tln 2>/dev/null | grep -q ":7890"; then
        log_success "代理端口 7890 正在监听"
    else
        log_warn "代理端口 7890 未检测到监听状态"
    fi
    
    # 显示服务状态
    log_info "服务运行状态:"
    echo "  systemd 服务状态: $(systemctl is-active mihomo.service 2>/dev/null || echo '未知')"
    echo "  容器状态:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep mihomo || echo "    mihomo 容器未运行"
    
    # 如果测试全部失败，给出建议
    if [[ $success_count -eq 0 ]]; then
        echo
        log_warn "网络连接测试全部失败，可能的原因："
        echo "  1. 代理服务尚未完全启动"
        echo "  2. 订阅配置有问题"
        echo "  3. 网络连接问题"
        echo "  建议："
        echo "  - 等待几分钟后重新测试: mihomo-control status"
        echo "  - 检查服务日志: mihomo-control logs"
        echo "  - 更新订阅配置: mihomo-update"
    fi
}

# 创建管理脚本
create_management_scripts() {
    log_step "创建管理脚本..."
    
    # 创建更新订阅脚本
    cat > "/usr/local/bin/mihomo-update" << 'EOF'
#!/bin/bash
# 更新 mihomo 订阅配置

if [[ ! -f /opt/mihomo/subscription_url.txt ]]; then
    echo "❌ 错误: 未找到订阅链接文件"
    exit 1
fi

subscription_url=$(cat /opt/mihomo/subscription_url.txt)
echo "🔄 正在更新订阅配置..."

# 下载新配置
if curl -fsSL --connect-timeout 10 --max-time 30 \
    -H "User-Agent: clash.meta" \
    "$subscription_url" -o "/tmp/new_config.yaml"; then
    
    # 验证配置文件
    if ! python3 -c "import yaml; yaml.safe_load(open('/tmp/new_config.yaml'))" 2>/dev/null; then
        echo "❌ 下载的配置文件格式无效"
        rm -f /tmp/new_config.yaml
        exit 1
    fi
    
    # 备份现有配置
    cp /opt/mihomo/config/config.yaml "/opt/mihomo/config/config.yaml.backup.$(date +%Y%m%d_%H%M%S)"
    
    # 更新配置
    cp /tmp/new_config.yaml /opt/mihomo/config/config.yaml
    rm -f /tmp/new_config.yaml
    
    # 通过 systemd 重启服务
    echo "🔄 重启 mihomo 服务..."
    systemctl restart mihomo.service
    
    # 等待服务启动
    sleep 3
    
    if systemctl is-active --quiet mihomo.service; then
        echo "✅ 订阅配置更新完成"
    else
        echo "❌ 服务重启失败"
        exit 1
    fi
else
    echo "❌ 订阅配置下载失败"
    exit 1
fi
EOF
    
    # 创建启停脚本
    cat > "/usr/local/bin/mihomo-control" << 'EOF'
#!/bin/bash
# mihomo 控制脚本（支持 systemd 服务）

case "$1" in
    start)
        echo "🚀 启动 mihomo 服务..."
        systemctl start mihomo.service
        if systemctl is-active --quiet mihomo.service; then
            echo "✅ mihomo 服务启动成功"
        else
            echo "❌ mihomo 服务启动失败"
            exit 1
        fi
        ;;
    stop)
        echo "🛑 停止 mihomo 服务..."
        systemctl stop mihomo.service
        echo "✅ mihomo 服务已停止"
        ;;
    restart)
        echo "🔄 重启 mihomo 服务..."
        systemctl restart mihomo.service
        if systemctl is-active --quiet mihomo.service; then
            echo "✅ mihomo 服务重启成功"
        else
            echo "❌ mihomo 服务重启失败"
            exit 1
        fi
        ;;
    status)
        echo "📊 mihomo 服务状态:"
        systemctl status mihomo.service --no-pager -l
        echo ""
        echo "🐳 容器状态:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep mihomo || echo "  mihomo 容器未运行"
        ;;
    logs)
        echo "📋 mihomo 服务日志:"
        journalctl -u mihomo.service -f --no-pager
        ;;
    docker-logs)
        echo "🐳 mihomo 容器日志:"
        docker logs -f mihomo
        ;;
    enable)
        echo "🔧 启用 mihomo 开机自启..."
        systemctl enable mihomo.service
        echo "✅ 开机自启已启用"
        ;;
    disable)
        echo "🔧 禁用 mihomo 开机自启..."
        systemctl disable mihomo.service
        echo "✅ 开机自启已禁用"
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|logs|docker-logs|enable|disable}"
        echo ""
        echo "命令说明:"
        echo "  start       - 启动服务"
        echo "  stop        - 停止服务"
        echo "  restart     - 重启服务"
        echo "  status      - 查看服务状态"
        echo "  logs        - 查看服务日志（实时）"
        echo "  docker-logs - 查看容器日志（实时）"
        echo "  enable      - 启用开机自启"
        echo "  disable     - 禁用开机自启"
        exit 1
        ;;
esac
EOF

    # 创建地理数据更新脚本
    cat > "/usr/local/bin/mihomo-update-geodata" << 'EOF'
#!/bin/bash
# 更新 mihomo 地理数据文件

echo "🌍 更新地理数据文件..."

DATA_DIR="/opt/mihomo/data"

# 备份现有文件
if [[ -f "$DATA_DIR/GeoSite.dat" ]]; then
    cp "$DATA_DIR/GeoSite.dat" "$DATA_DIR/GeoSite.dat.backup.$(date +%Y%m%d_%H%M%S)"
fi
if [[ -f "$DATA_DIR/GeoIP.metadb" ]]; then
    cp "$DATA_DIR/GeoIP.metadb" "$DATA_DIR/GeoIP.metadb.backup.$(date +%Y%m%d_%H%M%S)"
fi

# 下载函数
download_file_with_fallback() {
    local filename="$1"
    local output_path="$2"
    local urls=("${@:3}")
    
    echo "📥 下载 $filename..."
    
    for url in "${urls[@]}"; do
        echo "  尝试: $url"
        
        if command -v wget >/dev/null 2>&1; then
            if wget -q --timeout=20 --tries=2 "$url" -O "$output_path.tmp"; then
                local file_size
                file_size=$(stat -c%s "$output_path.tmp" 2>/dev/null || stat -f%z "$output_path.tmp" 2>/dev/null || echo "0")
                if [[ "$file_size" -gt 1000 ]]; then
                    mv "$output_path.tmp" "$output_path"
                    echo "✅ $filename 下载成功"
                    return 0
                fi
            fi
        fi
        
        if command -v curl >/dev/null 2>&1; then
            if curl -fsSL --connect-timeout 10 --max-time 60 "$url" -o "$output_path.tmp"; then
                local file_size
                file_size=$(stat -c%s "$output_path.tmp" 2>/dev/null || stat -f%z "$output_path.tmp" 2>/dev/null || echo "0")
                if [[ "$file_size" -gt 1000 ]]; then
                    mv "$output_path.tmp" "$output_path"
                    echo "✅ $filename 下载成功"
                    return 0
                fi
            fi
        fi
        
        rm -f "$output_path.tmp"
    done
    
    echo "❌ $filename 下载失败"
    return 1
}

# 定义下载源
geosite_urls=(
    "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat"
    "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat"
    "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geosite.dat"
    "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"
)

geoip_urls=(
    "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb"
    "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb"
    "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geoip.metadb"
    "https://github.com/MetaCubeX/meta-rules-dat/releases/latest/download/geoip-lite.metadb"
)

# 下载文件
download_file_with_fallback "GeoSite.dat" "$DATA_DIR/GeoSite.dat" "${geosite_urls[@]}"
download_file_with_fallback "GeoIP.metadb" "$DATA_DIR/GeoIP.metadb" "${geoip_urls[@]}"

# 设置权限
chmod 644 "$DATA_DIR"/*.dat "$DATA_DIR"/*.metadb 2>/dev/null || true

# 重启服务
echo "🔄 重启 mihomo 服务以应用新数据..."
if systemctl restart mihomo.service; then
    echo "✅ 地理数据文件更新完成"
else
    echo "❌ 服务重启失败"
    exit 1
fi
EOF

    # 设置执行权限
    chmod +x /usr/local/bin/mihomo-update
    chmod +x /usr/local/bin/mihomo-control
    chmod +x /usr/local/bin/mihomo-update-geodata
    
    log_success "管理脚本创建完成"
}

# 显示完成信息
show_completion_info() {
    echo
    log_success "=========================================="
    log_success "网络环境初始化完成！"
    log_success "=========================================="
    
    echo
    log_info "已安装的组件："
    echo "  ✅ mihomo (Clash.Meta) 代理客户端"
    echo "  ✅ 地理位置数据文件 (GeoSite.dat, GeoIP.metadb)"
    echo "  ✅ systemd 服务配置 (开机自启)"
    echo "  ✅ 全局代理环境变量"
    echo "  ✅ 管理脚本和别名"
    
    echo
    log_info "服务信息："
    echo "  🌐 混合端口: 7890 (HTTP/SOCKS5)"
    echo "  🎛️  控制面板: http://127.0.0.1:9090"
    echo "  📁 配置目录: /opt/mihomo/"
    echo "  🐳 容器名称: mihomo"
    echo "  🔧 systemd 服务: mihomo.service"
    
    echo
    log_info "管理命令："
    echo "  mihomo-control start|stop|restart|status|logs|enable|disable"
    echo "  mihomo-update         # 更新订阅配置"
    echo "  mihomo-update-geodata # 更新地理数据文件"
    echo "  proxy-on              # 启用代理（所有用户可用）"
    echo "  proxy-off             # 禁用代理（所有用户可用）"
    echo "  proxy-status          # 查看代理状态（所有用户可用）"
    
    echo
    log_info "全局代理配置："
    echo "  📄 配置文件: /etc/profile.d/clash-proxy.sh"
    echo "  🌍 所有用户登录时自动加载代理环境变量"
    echo "  💡 用户可通过 proxy-on/proxy-off 控制代理状态"
    
    echo
    log_info "systemd 服务："
    echo "  🚀 服务已启用开机自启动"
    echo "  🔧 使用 'systemctl status mihomo' 查看服务状态"
    echo "  📋 使用 'journalctl -u mihomo -f' 查看服务日志"
    
    echo
    log_warn "注意事项："
    echo "  1. 服务会在系统启动时自动启动"
    echo "  2. 配置文件位置: /opt/mihomo/config/config.yaml"
    echo "  3. 地理数据目录: /opt/mihomo/data/"
    echo "  4. 日志查看: mihomo-control logs"
    echo "  5. 重新登录以应用全局代理环境变量"
    echo "  6. 使用 proxy-on/proxy-off 命令控制代理状态"
    echo "  7. 地理数据更新: mihomo-update-geodata"
}

# 主函数
main() {
    log_info "=========================================="
    log_info "服务器网络环境初始化脚本"
    log_info "执行时间: $(date)"
    log_info "=========================================="
    
    # 用户确认
    echo
    log_warn "此脚本将执行以下操作："
    echo "  • 安装并配置 mihomo (Clash.Meta) VPN 客户端"
    echo "  • 下载必要的地理位置数据文件"
    echo "  • 配置 systemd 服务（开机自启）"
    echo "  • 配置全局代理环境变量"
    echo "  • 测试网络连接"
    echo "  • 创建管理脚本"
    echo
    log_info "注意：此脚本支持重复执行，已安装的组件将被自动跳过"
    echo
    read -p "确认继续执行？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "用户取消执行"
        exit 0
    fi
    
    # 执行安装步骤（可重复执行）
    check_prerequisites
    install_mihomo_binary_repeatable
    setup_directories_repeatable
    download_geodata_repeatable
    create_base_config_repeatable
    update_subscription_repeatable
    setup_systemd_service_repeatable
    start_mihomo_service_repeatable
    setup_global_proxy_repeatable
    test_network_connectivity
    create_management_scripts_repeatable
    show_completion_info
    
    log_success "网络环境初始化完成！"
    
    # 如果是内网环境，显示额外提示
    if [[ "$IS_INTRANET" == "true" ]]; then
        echo
        log_warn "========= 内网环境特别提醒 ========="
        echo "由于您处于内网环境，请注意以下事项："
        echo
        echo "1. 配置文件检查："
        echo "   - 编辑 /opt/mihomo/config/config.yaml"
        echo "   - 确保代理节点配置正确"
        echo
        echo "2. 地理数据文件："
        if [[ -f "/opt/mihomo/data/GeoSite.dat" ]] && [[ -f "/opt/mihomo/data/GeoIP.metadb" ]]; then
            echo "   ✅ 地理数据文件已就绪"
        else
            echo "   ⚠️  地理数据文件可能缺失，建议手动上传"
            echo "   参考: /opt/mihomo/data/basic-rules.yaml"
        fi
        echo
        echo "3. Docker 镜像："
        if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "mihomo"; then
            echo "   ✅ mihomo Docker 镜像已就绪"
        else
            echo "   ⚠️  请确保 mihomo Docker 镜像可用"
        fi
        echo
        echo "4. 测试与管理："
        echo "   - 使用 mihomo-control status 检查状态"
        echo "   - 使用 diagnose-network.sh 诊断问题"
        echo "   - 访问 http://内网IP:9090 管理面板"
        echo "=================================="
    fi
}

# 执行主函数
main "$@"
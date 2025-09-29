#!/usr/bin/env bash
set -euo pipefail

# =================================================================
# Docker 组件统一安装脚本
# =================================================================
# 功能：基于 components 配置安装 Docker 服务组件
# 支持：nginx, mysql, redis, mongodb, kafka, jenkins
# 用户：www (推荐) 或 root
# =================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_step() { echo -e "${PURPLE}[STEP]${NC} $1"; }

# 全局变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPONENTS_DIR="$PROJECT_ROOT/components"
COMPOSE_DIR="$PROJECT_ROOT/compose"
DATA_DIR="/data"
LOG_DIR="/data/logs"

# 默认配置
DEFAULT_USER="www"
DEFAULT_COMPOSE_PROJECT="infra"

# =================================================================
# 帮助信息
# =================================================================

show_help() {
    cat << EOF
Docker 组件统一安装脚本

用法:
  $0 [选项] [组件名]

组件:
  nginx       Web 服务器
  mysql       MySQL 数据库  
  redis       Redis 缓存
  mongo       MongoDB 数据库
  kafka       Apache Kafka 消息队列
  jenkins     Jenkins CI/CD 平台
  all         安装所有组件

选项:
  --user USER        指定运行用户 (默认: www)
  --project NAME     指定 Docker Compose 项目名 (默认: infra)
  --data-dir DIR     指定数据目录 (默认: /data)
  --env ENV          指定环境 (dev/prod, 默认: prod)
  --dry-run          仅显示要执行的命令，不实际执行
  --interactive, -i  强制进入交互式选择模式
  --help, -h         显示帮助信息

模式说明:
  1. 命令行模式: 直接指定组件名进行安装
  2. 交互式模式: 未指定组件或使用 -i 选项时，进入交互式菜单

示例:
  $0                          # 交互式选择组件
  $0 --interactive            # 强制交互式模式
  $0 nginx                    # 直接安装 nginx
  $0 mysql --user www         # 以 www 用户安装 mysql
  $0 all --env prod           # 安装所有组件（生产环境）
  $0 redis --dry-run          # 预览 redis 安装命令

交互式功能:
  - 多选组件支持
  - 实时选择状态显示
  - 批量安装选中组件
  - 安装结果汇总报告

环境变量:
  INFRA_USER         运行用户 (覆盖 --user)
  INFRA_PROJECT      项目名称 (覆盖 --project)
  INFRA_DATA_DIR     数据目录 (覆盖 --data-dir)
EOF
}

# =================================================================
# 环境检查和准备
# =================================================================

check_prerequisites() {
    log_step "检查前置条件..."
    
    # 检查 Docker
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker 未安装，请先运行 install-docker.sh"
        exit 1
    fi
    
    # 检查 Docker Compose
    if ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Compose 未安装"
        exit 1
    fi
    
    # 检查项目目录结构
    if [[ ! -d "$COMPONENTS_DIR" ]]; then
        log_error "组件配置目录不存在: $COMPONENTS_DIR"
        exit 1
    fi
    
    if [[ ! -d "$COMPOSE_DIR" ]]; then
        log_error "Compose 配置目录不存在: $COMPOSE_DIR"
        exit 1
    fi
    
    # 检查并初始化基础设施
    check_infrastructure
    
    log_success "前置条件检查通过"
}

check_infrastructure() {
    log_step "检查基础设施状态..."
    
    local infra_script="$SCRIPT_DIR/init-infrastructure.sh"
    
    # 检查基础设施脚本是否存在
    if [[ ! -f "$infra_script" ]]; then
        log_error "基础设施脚本不存在: $infra_script"
        exit 1
    fi
    
    # 检查网络和卷是否已创建
    local networks_exist=false
    local volumes_exist=false
    
    if docker network inspect infra-frontend infra-backend >/dev/null 2>&1; then
        networks_exist=true
    fi
    
    if docker volume inspect infra_mysql_data infra_redis_data >/dev/null 2>&1; then
        volumes_exist=true
    fi
    
    # 如果基础设施不完整，尝试创建
    if [[ "$networks_exist" != true || "$volumes_exist" != true ]]; then
        log_warn "基础设施不完整，正在创建网络和数据卷..."
        
        if ! "$infra_script" create; then
            log_error "基础设施创建失败，请手动运行: $infra_script create"
            exit 1
        fi
        
        log_success "基础设施创建完成"
    else
        log_success "基础设施已就绪"
    fi
}

check_user() {
    local user="$1"
    
    if [[ "$user" == "root" ]]; then
        log_warn "使用 root 用户运行（不推荐用于生产环境）"
        return 0
    fi
    
    # 检查用户是否存在
    if ! id "$user" >/dev/null 2>&1; then
        log_error "用户 $user 不存在"
        return 1
    fi
    
    # 检查用户是否在 docker 组中
    if ! groups "$user" 2>/dev/null | grep -q docker; then
        log_error "用户 $user 不在 docker 组中"
        log_info "请运行: sudo usermod -aG docker $user"
        return 1
    fi
    
    log_success "用户 $user 权限检查通过"
}

prepare_directories() {
    local user="$1"
    
    log_step "准备目录结构..."
    
    # 创建数据目录
    local dirs=(
        "$DATA_DIR"
        "$LOG_DIR"
        "$DATA_DIR/nginx"
        "$DATA_DIR/mysql"  
        "$DATA_DIR/redis"
        "$DATA_DIR/mongodb"
        "$DATA_DIR/kafka"
        "$DATA_DIR/ssl"
        "$DATA_DIR/apps"
        "$LOG_DIR/nginx"
        "$LOG_DIR/mysql"
        "$LOG_DIR/redis"
        "$LOG_DIR/mongodb"
        "$LOG_DIR/kafka"
        "$LOG_DIR/ssl"
        "$LOG_DIR/certbot"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log_info "创建目录: $dir"
            mkdir -p "$dir"
        fi
        
        # 设置目录权限
        if [[ "$user" != "root" ]]; then
            sudo chown "$user:$user" "$dir"
        fi
        sudo chmod 755 "$dir"
    done
    
    log_success "目录结构准备完成"
}

# =================================================================
# 组件验证和配置
# =================================================================

validate_component() {
    local component="$1"
    
    # 支持的组件列表
    local valid_components=("nginx" "mysql" "redis" "mongo" "kafka" "jenkins" "all")
    
    if [[ "$component" == "all" ]]; then
        return 0
    fi
    
    # 检查组件是否支持
    local found=false
    for valid in "${valid_components[@]}"; do
        if [[ "$component" == "$valid" ]]; then
            found=true
            break
        fi
    done
    
    if [[ "$found" == false ]]; then
        log_error "不支持的组件: $component"
        log_info "支持的组件: ${valid_components[*]}"
        return 1
    fi
    
    # 检查组件配置文件是否存在
    if [[ "$component" != "all" ]]; then
        local component_dir="$COMPONENTS_DIR/$component"
        if [[ ! -d "$component_dir" ]]; then
            log_error "组件配置目录不存在: $component_dir"
            return 1
        fi
        
        local override_file="$component_dir/override.yml"
        if [[ ! -f "$override_file" ]]; then
            log_error "组件配置文件不存在: $override_file"
            return 1
        fi
    fi
    
    return 0
}

# =================================================================
# 环境配置生成
# =================================================================

# =================================================================
# 环境配置验证（不再自动生成，要求用户手动配置）
# =================================================================

validate_env_file() {
    local env_file="$1"
    local component="$2"
    
    log_info "验证环境配置文件: $env_file"
    
    # 检查文件是否存在 - 如果不存在则直接退出
    if [[ ! -f "$env_file" ]]; then
        show_env_file_help "$env_file"
        log_error "安装中止：请先按照上述说明创建环境配置文件"
        exit 1
    fi
    
    # 根据组件检查必需的环境变量
    local missing_vars=()
    
    case "$component" in
        mysql)
            check_env_var "$env_file" "MYSQL_ROOT_PASSWORD" missing_vars
            check_env_var "$env_file" "MYSQL_DATABASE" missing_vars
            check_env_var "$env_file" "MYSQL_USER" missing_vars  
            check_env_var "$env_file" "MYSQL_PASSWORD" missing_vars
            ;;
        redis)
            check_env_var "$env_file" "REDIS_PASSWORD" missing_vars
            ;;
        mongo)
            check_env_var "$env_file" "MONGO_ROOT_USERNAME" missing_vars
            check_env_var "$env_file" "MONGO_ROOT_PASSWORD" missing_vars
            check_env_var "$env_file" "MONGO_DATABASE" missing_vars
            ;;
        jenkins)
            check_env_var "$env_file" "JENKINS_ADMIN_USER" missing_vars
            check_env_var "$env_file" "JENKINS_ADMIN_PASSWORD" missing_vars
            ;;
    esac
    
    # 如果有缺失的变量，报告错误
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "环境配置文件缺少必需的变量:"
        for var in "${missing_vars[@]}"; do
            log_error "  - $var"
        done
        show_env_file_help "$env_file"
        return 1
    fi
    
    log_success "环境配置验证通过"
    return 0
}

check_env_var() {
    local env_file="$1"
    local var_name="$2"
    local -n missing_array="$3"
    
    if ! grep -q "^${var_name}=" "$env_file"; then
        missing_array+=("$var_name")
    fi
}

show_env_file_help() {
    local env_file="$1"
    local env_dir="$(dirname "$env_file")"
    
    echo
    echo "========================================"
    log_error "❌ 环境配置文件缺失"
    echo "========================================"
    log_error "找不到必需的环境配置文件: $env_file"
    echo
    log_warn "⚠️  此文件包含数据库密码等敏感信息，已被 .gitignore 排除在版本控制之外"
    log_warn "⚠️  您需要手动创建或上传此文件才能继续安装"
    echo
    echo "========================================" 
    log_info "📋 解决方案 (任选其一):"
    echo "========================================" 
    echo
    log_info "方案1️⃣ : 从本地上传配置文件 (推荐)"
    echo "  # 在本地执行以下命令:"
    echo "  scp /local/path/to/.env root@\$(hostname -I | awk '{print \$1}'):$env_file"
    echo
    echo "  # 或者上传开发环境配置并修改:"
    echo "  scp compose/env/dev/.env root@\$(hostname -I | awk '{print \$1}'):$env_file"
    echo "  # 然后登录服务器修改数据库名称等配置"
    echo
    log_info "方案2️⃣ : 在服务器上直接创建"
    echo "  # 创建配置目录:"
    echo "  mkdir -p $env_dir"
    echo
    echo "  # 创建配置文件:"
    echo "  cat > $env_file << 'EOF'"
    echo "# MySQL 配置"
    echo "MYSQL_ROOT_PASSWORD=your_secure_password_here"
    echo "MYSQL_DATABASE=your_database_name"
    echo "MYSQL_USER=your_username" 
    echo "MYSQL_PASSWORD=your_user_password_here"
    echo "MYSQL_PORT=3306"
    echo ""
    echo "# Redis 配置"
    echo "REDIS_PASSWORD=your_redis_password_here"
    echo "REDIS_PORT=6379"
    echo ""
    echo "# MongoDB 配置"
    echo "MONGO_ROOT_USERNAME=your_mongo_admin"
    echo "MONGO_ROOT_PASSWORD=your_mongo_password_here"
    echo "MONGO_DATABASE=your_mongo_database"
    echo "MONGO_PORT=27017"
    echo ""
    echo "# Jenkins 配置"
    echo "JENKINS_ADMIN_USER=admin"
    echo "JENKINS_ADMIN_PASSWORD=your_jenkins_password_here"
    echo "EOF"
    echo
    echo "  # 设置安全权限:"
    echo "  chmod 600 $env_file"
    echo "  chown \$(whoami):\$(whoami) $env_file"
    echo
    log_info "方案3️⃣ : 复制现有配置模板"
    echo "  # 如果存在其他环境的配置:"
    echo "  cp compose/env/dev/.env $env_file  # 复制开发环境配置"
    echo "  nano $env_file  # 编辑并修改相应参数"
    echo
    echo "========================================"
    log_warn "🔐 安全提醒:"
    echo "========================================"
    log_warn "• 请使用强密码，不要使用示例中的默认值"
    log_warn "• 配置文件包含敏感信息，请妥善保管"
    log_warn "• 生产环境与开发环境请使用不同的密码"
    log_warn "• 配置完成后，重新运行安装命令即可"
    echo
    echo "========================================"
    log_info "📞 需要帮助?"
    echo "========================================"
    log_info "• 查看配置模板: ls compose/env/*/README.md"
    log_info "• 检查现有配置: find compose/env -name '*.env' -type f"
    log_info "• 重新运行安装: make install-mysql (配置文件创建后)"
    echo "========================================"
}

# =================================================================
# 组件安装函数
# =================================================================

# Jenkins 专门安装函数
install_jenkins_component() {
    local env_type="$1"
    local dry_run="$2"
    
    log_info "使用 Jenkins 专门安装脚本..."
    
    local jenkins_script="$SCRIPT_DIR/install-jenkins.sh"
    
    if [[ ! -f "$jenkins_script" ]]; then
        log_error "Jenkins 安装脚本不存在: $jenkins_script"
        return 1
    fi
    
    # 构建参数
    local args=("--env" "$env_type")
    
    if [[ "$dry_run" == "true" ]]; then
        args+=("--dry-run")
    fi
    
    # 执行 Jenkins 安装脚本
    if "$jenkins_script" "${args[@]}"; then
        log_success "Jenkins 安装完成"
        return 0
    else
        log_error "Jenkins 安装失败"
        return 1
    fi
}

# =================================================================
# 组件安装
# =================================================================

install_component() {
    local component="$1"
    local user="$2"
    local env_type="$3"
    local dry_run="$4"
    
    log_step "安装组件: $component"
    
    # 验证组件
    if ! validate_component "$component"; then
        return 1
    fi
    
    # Jenkins 使用专门的安装脚本
    if [[ "$component" == "jenkins" ]]; then
        install_jenkins_component "$env_type" "$dry_run"
        return $?
    fi
    
    # 检查并验证环境配置文件
    local env_file="$COMPOSE_DIR/env/${env_type}/.env"
    if ! validate_env_file "$env_file" "$component"; then
        log_error "环境配置验证失败，请修正配置后重试"
        return 1
    fi
    
    # 准备 Docker Compose 文件
    local compose_base="$COMPOSE_DIR/base/docker-compose.yml"
    local compose_override
    local env_file="$COMPOSE_DIR/env/${env_type}/.env"
    local use_standalone=false
    
    # 对于某些组件使用专门的独立 compose 文件
    case "$component" in
        nginx|mysql|redis|mongo|kafka|jenkins)
            local standalone_compose="$COMPOSE_DIR/infra/docker-compose.${component}.yml"
            if [[ -f "$standalone_compose" ]]; then
                use_standalone=true
                compose_override="$standalone_compose"
            else
                compose_override="$COMPONENTS_DIR/$component/override.yml"
            fi
            ;;
        *)
            compose_override="$COMPONENTS_DIR/$component/override.yml"
            ;;
    esac
    
    # 构建 Docker Compose 命令
    local compose_cmd=(
        "docker" "compose"
    )
    
    if [[ "$use_standalone" == true ]]; then
        # 使用独立的 compose 文件
        compose_cmd+=("-f" "$compose_override")
    else
        # 使用 base + override 模式
        compose_cmd+=("-f" "$compose_base" "-f" "$compose_override")
    fi
    
    compose_cmd+=(
        "--env-file" "$env_file"
        "-p" "$DEFAULT_COMPOSE_PROJECT"
    )
    
    if [[ "$dry_run" == true ]]; then
        log_info "预览模式 - 将要执行的命令:"
        echo "  ${compose_cmd[*]} up -d $component"
        return 0
    fi
    
    # 切换到指定用户执行（如果不是 root）
    if [[ "$user" != "root" && "$(id -u)" == "0" ]]; then
        log_info "切换到用户 $user 执行安装..."
        
        # 使用 sudo -u 切换用户
        sudo -u "$user" "${compose_cmd[@]}" up -d "$component"
    else
        # 直接执行
        "${compose_cmd[@]}" up -d "$component"
    fi
    
    # 等待服务启动（根据服务类型设置不同等待时间）
    log_info "等待服务启动..."
    case "$component" in
        nginx)
            log_info "Nginx 启动中，等待 10 秒..."
            sleep 10
            # 初始化应用配置目录
            log_info "初始化 Nginx 应用配置目录..."
            if [[ -f "$SCRIPT_DIR/init-apps-config.sh" ]]; then
                bash "$SCRIPT_DIR/init-apps-config.sh"
            else
                log_warn "未找到应用配置初始化脚本"
            fi
            ;;
        mysql)
            log_info "MySQL 需要较长初始化时间，等待 30 秒..."
            sleep 30
            ;;
        mongo)
            log_info "MongoDB 需要初始化时间，等待 20 秒..."
            sleep 20
            ;;
        jenkins)
            log_info "Jenkins 需要较长启动时间，等待 60 秒..."
            sleep 60
            ;;
        *)
            sleep 10
            ;;
    esac
    
    # 检查服务状态
    if check_component_health "$component"; then
        log_success "组件 $component 安装成功"
    else
        log_error "组件 $component 安装失败"
        return 1
    fi
}

install_all_components() {
    local user="$1"
    local env_type="$2" 
    local dry_run="$3"
    
    log_step "安装所有组件..."
    
    local components=("nginx" "mysql" "redis" "mongo" "kafka" "jenkins")
    local failed_components=()
    
    for component in "${components[@]}"; do
        log_info "正在安装: $component"
        
        if install_component "$component" "$user" "$env_type" "$dry_run"; then
            log_success "✅ $component 安装成功"
        else
            log_error "❌ $component 安装失败"
            failed_components+=("$component")
        fi
        
        echo "----------------------------------------"
    done
    
    # 安装结果总结
    if [[ ${#failed_components[@]} -eq 0 ]]; then
        log_success "🎉 所有组件安装完成！"
    else
        log_warn "部分组件安装失败:"
        for failed in "${failed_components[@]}"; do
            log_error "  - $failed"
        done
    fi
}

check_component_health() {
    local component="$1"
    
    log_info "检查 $component 服务健康状态..."
    
    # 检查服务状态（支持多种容器名称格式）
    local container_patterns=("$component" "${DEFAULT_COMPOSE_PROJECT}-${component}-1" "${component}-1")
    
    for pattern in "${container_patterns[@]}"; do
        if docker ps --filter "name=^${pattern}$" --filter "status=running" --format "{{.Names}}" | grep -q "^${pattern}$"; then
            log_success "$component 容器运行正常 (容器名: $pattern)"
            return 0
        fi
    done
    
    # 如果没有找到运行的容器，显示详细信息
    log_warn "$component 容器可能未运行，检查详细状态..."
    docker ps -a --filter "name=$component" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    # 最后尝试简单的名称匹配
    if docker ps --filter "status=running" --format "{{.Names}}" | grep -q "$component"; then
        log_success "$component 容器实际在运行中"
        return 0
    else
        log_error "$component 容器未运行"
        return 1
    fi
}

# =================================================================
# 交互式组件选择
# =================================================================

show_interactive_menu() {
    local user="$1"
    local env_type="$2"
    local dry_run="$3"
    
    echo "========================================"
    echo "🐳 Docker 组件交互式安装"
    echo "========================================"
    echo "当前配置:"
    echo "  用户: $user"
    echo "  环境: $env_type"
    echo "  预览模式: $dry_run"
    echo "========================================"
    echo
    
    local components=("nginx" "mysql" "redis" "mongo" "kafka" "jenkins")
    local selected_components=()
    
    while true; do
        echo "📋 可选组件列表:"
        echo
        
        # 显示组件选项
        for i in "${!components[@]}"; do
            local num=$((i + 1))
            local component="${components[i]}"
            local status="未选择"
            
            # 检查是否已选择
            for selected in "${selected_components[@]}"; do
                if [[ "$selected" == "$component" ]]; then
                    status="✅ 已选择"
                    break
                fi
            done
            
            case "$component" in
                nginx) echo "  $num. Nginx       - Web 服务器          [$status]" ;;
                mysql) echo "  $num. MySQL       - 关系型数据库        [$status]" ;;
                redis) echo "  $num. Redis       - 内存缓存数据库      [$status]" ;;
                mongo) echo "  $num. MongoDB     - NoSQL 文档数据库    [$status]" ;;
                kafka) echo "  $num. Kafka       - 分布式消息队列      [$status]" ;;
                jenkins) echo "  $num. Jenkins     - CI/CD 持续集成平台  [$status]" ;;
            esac
        done
        
        echo
        echo "操作选项:"
        echo "  a. 全选所有组件"
        echo "  r. 推荐组合 (nginx + mysql + redis)"
        echo "  c. 清空选择"
        echo "  i. 显示组件详细信息"
        echo "  s. 开始安装已选择的组件"
        echo "  q. 退出"
        echo
        
        if [[ ${#selected_components[@]} -gt 0 ]]; then
            echo "🎯 已选择的组件: ${selected_components[*]}"
            echo
        fi
        
        read -p "请选择组件编号或操作 (1-5/a/c/s/q): " -r choice
        
        case "$choice" in
            [1-5])
                local index=$((choice - 1))
                local component="${components[index]}"
                
                # 检查是否已选择
                local already_selected=false
                local new_selected=()
                
                for selected in "${selected_components[@]}"; do
                    if [[ "$selected" == "$component" ]]; then
                        already_selected=true
                        log_info "取消选择: $component"
                    else
                        new_selected+=("$selected")
                    fi
                done
                
                if [[ "$already_selected" == false ]]; then
                    selected_components+=("$component")
                    log_info "选择了: $component"
                else
                    selected_components=("${new_selected[@]}")
                fi
                ;;
            a|A)
                selected_components=("${components[@]}")
                log_info "已选择所有组件"
                ;;
            r|R)
                selected_components=("nginx" "mysql" "redis")
                log_info "已选择推荐组合: nginx + mysql + redis"
                ;;
            c|C)
                selected_components=()
                log_info "已清空所有选择"
                ;;
            i|I)
                show_component_details
                ;;
            s|S)
                if [[ ${#selected_components[@]} -eq 0 ]]; then
                    log_warn "请先选择要安装的组件"
                    continue
                fi
                
                echo
                log_info "准备安装以下组件: ${selected_components[*]}"
                echo
                read -p "确认开始安装？(y/N): " -n 1 -r
                echo
                
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    install_selected_components "${selected_components[@]}" "$user" "$env_type" "$dry_run"
                    return 0
                else
                    log_info "取消安装，返回选择菜单"
                fi
                ;;
            q|Q)
                log_info "退出安装程序"
                exit 0
                ;;
            *)
                log_warn "无效选择，请重新输入"
                ;;
        esac
        
        echo
    done
}

show_component_details() {
    echo
    echo "========================================"
    echo "📋 组件详细信息"
    echo "========================================"
    echo
    echo "🌐 Nginx (Web 服务器)"
    echo "  • 作用: 反向代理、负载均衡、静态文件服务"
    echo "  • 端口: 80 (HTTP), 443 (HTTPS)"
    echo "  • 资源: 轻量级，内存占用约 128MB"
    echo "  • 依赖: 无"
    echo
    echo "🗄️  MySQL (关系型数据库)"
    echo "  • 作用: 主要数据存储，支持事务和 SQL"
    echo "  • 端口: 3306"
    echo "  • 资源: 中等，内存占用约 1.2GB"
    echo "  • 依赖: 无"
    echo
    echo "⚡ Redis (内存缓存)"
    echo "  • 作用: 缓存、会话存储、消息队列"
    echo "  • 端口: 6379"
    echo "  • 资源: 轻量级，内存占用约 256MB"
    echo "  • 依赖: 无"
    echo
    echo "📄 MongoDB (NoSQL 数据库)"
    echo "  • 作用: 文档存储，适用于非关系型数据"
    echo "  • 端口: 27017"
    echo "  • 资源: 中等，内存占用约 512MB"
    echo "  • 依赖: 无"
    echo
    echo "📨 Kafka (消息队列)"
    echo "  • 作用: 分布式消息流处理平台"
    echo "  • 端口: 9092 (Kafka), 2181 (Zookeeper)"
    echo "  • 资源: 较重，内存占用约 1GB"
    echo "  • 依赖: Zookeeper (自动安装)"
    echo
    echo "� Jenkins (CI/CD 平台)"
    echo "  • 作用: 持续集成/持续部署，代码构建和发布"
    echo "  • 端口: 8080 (Web), 50000 (Agent)"
    echo "  • 资源: 中等，内存占用约 512MB"
    echo "  • 依赖: 无 (可选择依赖 Docker 进行构建)"
    echo "  • 特性: CasC 配置，预装插件，Docker 集成"
    echo
    echo "�💡 推荐安装顺序:"
    echo "  1. Nginx → 2. MySQL → 3. Redis → 4. MongoDB → 5. Kafka → 6. Jenkins"
    echo
    echo "🎯 常用组合:"
    echo "  • Web 应用: nginx + mysql + redis"
    echo "  • API 服务: nginx + mysql + redis + mongo"
    echo "  • 微服务: nginx + mysql + redis + kafka"
    echo "  • 全栈开发: nginx + mysql + redis + mongo + kafka + jenkins"
    echo "  • CI/CD 环境: jenkins + mysql + redis (用于构建和测试)"
    echo
    read -p "按任意键返回组件选择菜单..." -n 1 -r
    echo
}

install_selected_components() {
    local components=("$@")
    local user="${components[-3]}"
    local env_type="${components[-2]}"
    local dry_run="${components[-1]}"
    
    # 移除最后三个参数（用户、环境类型、预览模式）
    unset 'components[-1]' 'components[-1]' 'components[-1]'
    
    log_step "开始安装选中的组件..."
    
    local failed_components=()
    local success_count=0
    
    for component in "${components[@]}"; do
        echo "========================================"
        log_info "正在安装: $component (${success_count}/${#components[@]})"
        echo "========================================"
        
        if install_component "$component" "$user" "$env_type" "$dry_run"; then
            log_success "✅ $component 安装成功"
            ((success_count++))
        else
            log_error "❌ $component 安装失败"
            failed_components+=("$component")
        fi
        
        echo
    done
    
    # 安装结果总结
    echo "========================================"
    echo "📊 安装结果汇总"
    echo "========================================"
    echo "总计组件: ${#components[@]}"
    echo "安装成功: $success_count"
    echo "安装失败: ${#failed_components[@]}"
    
    if [[ ${#failed_components[@]} -eq 0 ]]; then
        log_success "🎉 所有组件安装完成！"
    else
        echo
        log_warn "以下组件安装失败:"
        for failed in "${failed_components[@]}"; do
            log_error "  ❌ $failed"
        done
        echo
        log_info "可以稍后单独重试失败的组件："
        for failed in "${failed_components[@]}"; do
            echo "  bash install-$failed.sh --user $user"
        done
    fi
}

# =================================================================
# 主程序
# =================================================================

main() {
    # 默认参数
    local component=""
    local user="${INFRA_USER:-$DEFAULT_USER}"
    local project="${INFRA_PROJECT:-$DEFAULT_COMPOSE_PROJECT}"
    local data_dir="${INFRA_DATA_DIR:-$DATA_DIR}"
    local env_type="prod"
    local dry_run=false
    local interactive=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --user)
                user="$2"
                shift 2
                ;;
            --project)
                project="$2"
                shift 2
                ;;
            --data-dir)
                data_dir="$2"
                shift 2
                ;;
            --env)
                env_type="$2"
                shift 2
                ;;
            --dry-run)
                dry_run=true
                shift
                ;;
            --interactive|-i)
                interactive=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            -*)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
            *)
                if [[ -z "$component" ]]; then
                    component="$1"
                else
                    log_error "只能指定一个组件"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # 更新全局变量
    DEFAULT_COMPOSE_PROJECT="$project"
    DATA_DIR="$data_dir"
    LOG_DIR="$data_dir/logs"
    
    # 执行前置检查
    check_prerequisites
    check_user "$user"
    prepare_directories "$user"
    
    # 交互式模式或命令行模式
    if [[ "$interactive" == true ]] || [[ -z "$component" ]]; then
        # 交互式选择组件
        if [[ -z "$component" ]]; then
            log_info "未指定组件，进入交互式选择模式"
        fi
        show_interactive_menu "$user" "$env_type" "$dry_run"
    else
        # 命令行直接指定组件
        echo "========================================"
        echo "🐳 Docker 组件安装"
        echo "========================================"
        echo "组件: $component"
        echo "用户: $user"
        echo "项目: $project"
        echo "数据目录: $data_dir"
        echo "环境: $env_type"
        echo "预览模式: $dry_run"
        echo "========================================"
        echo
        
        if [[ "$component" == "all" ]]; then
            install_all_components "$user" "$env_type" "$dry_run"
        else
            install_component "$component" "$user" "$env_type" "$dry_run"
        fi
    fi
    
    if [[ "$dry_run" == false ]]; then
        log_success "🎉 安装完成！"
        log_info "管理命令:"
        log_info "  查看状态: docker compose -p $project ps"
        log_info "  查看日志: docker compose -p $project logs [服务名]"
        log_info "  停止服务: docker compose -p $project stop [服务名]"
        log_info "  启动服务: docker compose -p $project start [服务名]"
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
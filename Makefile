# Infrastructure Management Makefile
# 基础设施项目管理工具 v2.1 - 按 "0→1 部署" 编排
# ==============================================================================

# ==============================================================================
# 全局变量
# ==============================================================================
PROJECT_NAME := infra
DEFAULT_ENV := dev
ENV ?= $(DEFAULT_ENV)

# 环境配置文件路径
# prod 环境使用各节点 env，其他环境使用 .env
ifeq ($(ENV),prod)
    ENV_FILE_A := compose/env/prod/serverA.env
    ENV_FILE_B := compose/env/prod/serverB.env
    ENV_FILE_C := compose/env/prod/serverC.env
    ENV_FILE_D := compose/env/prod/serverD.env
    ENV_FILE := $(ENV_FILE_A)
else
    ENV_FILE := compose/env/$(ENV)/.env
    ENV_FILE_A := $(ENV_FILE)
    ENV_FILE_B := $(ENV_FILE)
    ENV_FILE_C := $(ENV_FILE)
    ENV_FILE_D := $(ENV_FILE)
endif

# 加载环境变量（如果文件存在）
ifneq (,$(wildcard $(ENV_FILE)))
    include $(ENV_FILE)
    export
endif

# 脚本路径（新结构）
SCRIPTS_DIR := scripts
SERVER_SCRIPTS := $(SCRIPTS_DIR)/00-server
NETWORK_SCRIPTS := $(SCRIPTS_DIR)/01-network
COMPONENTS_SCRIPTS := $(SCRIPTS_DIR)/02-components
NGINX_SCRIPTS := $(SCRIPTS_DIR)/03-nginx
SSL_SCRIPTS := $(SCRIPTS_DIR)/04-ssl
UTILS_SCRIPTS := $(SCRIPTS_DIR)/utils

# 常用脚本
INFRA_SCRIPT := $(COMPONENTS_SCRIPTS)/init-infrastructure.sh
INSTALL_SCRIPT := $(COMPONENTS_SCRIPTS)/install.sh
COMPOSE_MANAGER := $(COMPONENTS_SCRIPTS)/compose-manager.sh
COMPOSE_MANAGER_ENV := ENV=$(ENV) ENVIRONMENT=$(ENV) INFRA_ENV=$(ENV) INFRA_ENV_TYPE=$(ENV)

# 组件配置路径
COMPONENTS_DIR := components

# 默认参数
LOG_LINES := 100

# 颜色定义
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
CYAN := \033[36m
MAGENTA := \033[35m
BOLD := \033[1m
RESET := \033[0m

# ==============================================================================
# 辅助函数
# ==============================================================================
define require_param
	@if [ -z "$($(1))" ]; then \
		echo "$(RED)$(BOLD)❌ 错误: 请提供 $(1) 参数$(RESET)"; \
		echo "$(BLUE)💡 示例: $(2)$(RESET)"; \
		exit 1; \
	fi
endef

define success_msg
	@echo "$(GREEN)✅ $(1)$(RESET)"
endef

define warning_msg
	@echo "$(YELLOW)⚠️  $(1)$(RESET)"
endef

define error_msg
	@echo "$(RED)$(BOLD)❌ $(1)$(RESET)"
endef

define info_msg
	@echo "$(BLUE)ℹ️  $(1)$(RESET)"
endef

define shell_success_msg
	echo "$(GREEN)✅ $(1)$(RESET)"
endef

define shell_warning_msg
	echo "$(YELLOW)⚠️  $(1)$(RESET)"
endef

define shell_error_msg
	echo "$(RED)$(BOLD)❌ $(1)$(RESET)"
endef

define shell_info_msg
	echo "$(BLUE)ℹ️  $(1)$(RESET)"
endef

define ensure_infra_network_visible
	@if docker network inspect infra-network >/dev/null 2>&1; then \
		echo "$(GREEN)✅ infra-network 已在本机可见$(RESET)"; \
	else \
		swarm_state=$$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive"); \
		control_available=$$(docker info --format '{{.Swarm.ControlAvailable}}' 2>/dev/null || echo "false"); \
		if [ "$$swarm_state" != "active" ]; then \
			echo "$(RED)$(BOLD)❌ 未找到 infra-network，且当前节点未加入 active Swarm$(RESET)"; \
			echo "$(BLUE)💡 先按 docs/network/swarm-setup.md 加入集群，再启动本机服务$(RESET)"; \
			exit 1; \
		fi; \
		if [ "$$control_available" = "true" ]; then \
			echo "$(RED)$(BOLD)❌ 当前 manager 未找到 infra-network$(RESET)"; \
			echo "$(BLUE)💡 请先在首个 manager 上执行 make init-serverA，或执行 sudo ./scripts/01-network/swarm-manager.sh create-network$(RESET)"; \
			exit 1; \
		fi; \
		echo "$(RED)$(BOLD)❌ 当前 worker 尚未看到 infra-network$(RESET)"; \
		echo "$(YELLOW)这是 Docker Swarm overlay 的按需下发现象：worker 只有在有任务/容器接入网络后，才会在本机 docker network ls 中看到它。$(RESET)"; \
		echo "$(BLUE)💡 请在任一 manager 上执行 make swarm-network-probe，完成后回到当前节点重试。$(RESET)"; \
		exit 1; \
	fi
endef

define section_title
	@echo ""
	@echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"
	@echo "$(CYAN)$(BOLD)  $(1)$(RESET)"
	@echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"
endef

# ==============================================================================
# 默认目标和帮助
# ==============================================================================
.DEFAULT_GOAL := help

.PHONY: help
help: ## 显示帮助信息
	@echo ""
	@echo "$(GREEN)$(BOLD)🐳 基础设施项目管理工具$(RESET) v2.1"
	@echo ""
	@echo "$(BLUE)$(BOLD)按 \"0→1 部署\" 顺序编排:$(RESET)"
	@echo ""
	@echo "$(MAGENTA)0. 服务器初始化$(RESET)"
	@echo "   $(CYAN)server-init$(RESET)          交互式 Linux 初始化"
	@echo "   $(CYAN)server-init-users$(RESET)    创建/维护用户账户 (root/yangshujie/deploy/www)"
	@echo "   $(CYAN)server-install-docker$(RESET) 安装 Docker 和 Compose"
	@echo ""
	@echo "$(MAGENTA)1. VPN/网络配置$(RESET)"
	@echo "   $(CYAN)vpn-setup$(RESET)            安装配置 VPN (Mihomo)"
	@echo "   $(CYAN)vpn-status$(RESET)           查看 VPN 状态"
	@echo "   $(CYAN)swarm-init$(RESET)           初始化 Docker Swarm"
	@echo ""
	@echo "$(MAGENTA)2. 基础设施初始化$(RESET)"
	@echo "   $(CYAN)init$(RESET)                 初始化网络和数据卷"
	@echo "   $(CYAN)install$(RESET)              交互式安装组件"
	@echo "   $(CYAN)install-all-silent$(RESET)   静默安装所有组件"
	@echo ""
	@echo "$(MAGENTA)3. 组件管理$(RESET)"
	@echo "   $(CYAN)<组件>-start/stop/logs$(RESET)  启动/停止/日志"
	@echo "   组件: nginx, mongo, redis, nsq, mysql(dev), prometheus, grafana"
	@echo ""
	@echo "$(MAGENTA)4. SSL证书管理$(RESET)"
	@echo "   $(CYAN)ssl-wildcard$(RESET)         申请通配符证书 (Let's Encrypt)"
	@echo "   $(CYAN)ssl-list$(RESET)             列出所有证书"
	@echo "   $(CYAN)ssl-dev$(RESET)              生成开发环境自签名证书"
	@echo "   $(CYAN)ssl-dev-list$(RESET)         列出开发证书"
	@echo "   $(CYAN)grpc-ca$(RESET)              生成 gRPC mTLS CA 证书"
	@echo "   $(CYAN)grpc-server$(RESET)          生成 gRPC 双向证书 (serverAuth+clientAuth)"
	@echo ""
	@echo "$(MAGENTA)5. Nginx应用管理$(RESET)"
	@echo "   $(CYAN)app-deploy$(RESET)           部署应用配置"
	@echo "   $(CYAN)app-list$(RESET)             列出应用配置"
	@echo ""
	@echo "$(MAGENTA)6. 运维监控$(RESET)"
	@echo "   $(CYAN)status$(RESET)               查看所有服务状态"
	@echo "   $(CYAN)test-all$(RESET)             测试所有服务"
	@echo "   $(CYAN)troubleshoot$(RESET)         故障诊断"
	@echo ""
	@echo "$(MAGENTA)7. 服务器部署$(RESET)"
	@echo "   $(CYAN)serverA-up/down$(RESET)      ServerA 服务栈管理"
	@echo "   $(CYAN)serverB-up/down$(RESET)      ServerB 服务栈管理"
	@echo "   $(CYAN)serverC-up/down$(RESET)      ServerC 服务栈管理"
	@echo "   $(CYAN)serverD-up/down$(RESET)      ServerD 服务栈管理"
	@echo "   $(CYAN)server-info$(RESET)          显示当前服务器架构"
	@echo ""
	@echo "$(YELLOW)💡 使用 'make help-all' 查看完整命令列表$(RESET)"
	@echo ""

.PHONY: help-all
help-all: ## 显示所有命令
	$(call section_title,完整命令列表)
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)0. 服务器初始化$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^server-.*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)1. VPN/网络管理$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^(vpn-|swarm-|net-|port-).*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)2. 基础设施初始化$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^(init|install|up|down|restart|status|ps):.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)3. 组件管理$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^(nginx-|mongo-|redis-|nsq-|mysql-|prometheus-|grafana-).*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)4. SSL 证书管理$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(YELLOW)4.1 Let's Encrypt 证书（生产环境）$(RESET)"
	@grep -hE '^ssl-(wildcard|obtain|import|renew|list|remove|setup-aliyun):.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)4.2 开发环境证书（自签名）$(RESET)"
	@grep -hE '^ssl-dev.*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)4.3 gRPC mTLS 证书（服务间通信）$(RESET)"
	@grep -hE '^grpc-.*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)5. Nginx 应用管理$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^app-.*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)6. 运维监控$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^(test-|backup-|troubleshoot).*:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(MAGENTA)7. 服务器部署管理$(RESET)"
	@echo "$(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@grep -hE '^serverA-|^serverB-|^serverC-|^serverD-|^server-info:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ==============================================================================
# 0. 服务器初始化
# ==============================================================================
.PHONY: server-init server-init-users server-install-docker server-setup-deploy-ssh server-tune

server-init: ## 交互式 Linux 初始化 (用户/Docker/调优/deploy SSH/VPN)
	$(call info_msg,启动交互式 Linux 初始化...)
	@sudo bash $(SERVER_SCRIPTS)/initialize.sh

server-init-users: ## 初始化服务器用户账户 (root/yangshujie/deploy/www)
	$(call info_msg,初始化服务器用户账户...)
	@sudo bash $(SERVER_SCRIPTS)/init-users.sh

server-install-docker: ## 安装 Docker Engine 和 Compose
	$(call info_msg,安装 Docker...)
	@sudo bash $(SERVER_SCRIPTS)/install-docker.sh

server-setup-deploy-ssh: ## 配置 deploy 受限 SSH (CI_PUBLIC_KEY=xxx)
	$(call require_param,CI_PUBLIC_KEY,make server-setup-deploy-ssh CI_PUBLIC_KEY="ssh-ed25519 AAA...")
	@sudo bash $(SERVER_SCRIPTS)/setup-deploy-ssh.sh "$(CI_PUBLIC_KEY)"

server-tune: ## 优化宿主机系统参数 (MongoDB等需要)
	$(call warning_msg,优化宿主机系统参数...)
	@sudo bash $(SERVER_SCRIPTS)/tune-host.sh

# ==============================================================================
# 1. VPN/网络配置
# ==============================================================================
.PHONY: vpn-setup vpn-status vpn-test vpn-enable vpn-disable vpn-switch vpn-proxies vpn-docker-test vpn-uninstall vpn-diagnose
.PHONY: tailscale-install tailscale-up tailscale-status tailscale-ip tailscale-check tailscale-swarm-env
.PHONY: swarm-init swarm-join-manager swarm-join-worker swarm-leave swarm-status swarm-network-probe net-list net-create net-delete net-inspect port-check

vpn-setup: ## 安装配置 VPN (Mihomo)
	@sudo bash $(NETWORK_SCRIPTS)/vpn-setup.sh

vpn-status: ## 查看 VPN 状态
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh status

vpn-test: ## 测试 VPN 连接
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh test

vpn-enable: ## 启用 VPN 模式
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh enable

vpn-disable: ## 禁用 VPN (直连)
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh disable

vpn-proxies: ## 显示所有代理组状态
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh proxies

vpn-switch: ## 切换代理选择 (交互式)
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh switch

vpn-docker-test: ## 测试 Docker 容器 VPN 连接
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh docker-test

vpn-uninstall: ## 卸载 VPN
	@sudo bash $(NETWORK_SCRIPTS)/vpn-uninstall.sh

vpn-diagnose: ## 网络诊断
	@sudo bash $(NETWORK_SCRIPTS)/diagnose.sh

tailscale-install: ## 安装 Tailscale
	@sudo bash $(NETWORK_SCRIPTS)/tailscale-manager.sh install

tailscale-up: ## 启动/登录 Tailscale (TAILSCALE_HOSTNAME=serverA TAILSCALE_AUTH_KEY=可选)
	@sudo TAILSCALE_HOSTNAME="$(TAILSCALE_HOSTNAME)" TAILSCALE_AUTH_KEY="$(TAILSCALE_AUTH_KEY)" TAILSCALE_EXTRA_ARGS="$(TAILSCALE_EXTRA_ARGS)" bash $(NETWORK_SCRIPTS)/tailscale-manager.sh up

tailscale-status: ## 查看 Tailscale 状态
	@bash $(NETWORK_SCRIPTS)/tailscale-manager.sh status

tailscale-ip: ## 输出本机 Tailscale IPv4
	@bash $(NETWORK_SCRIPTS)/tailscale-manager.sh ip

tailscale-check: ## 检查 Tailscale 与 Mihomo/Swarm underlay 冲突
	@sudo bash $(NETWORK_SCRIPTS)/tailscale-manager.sh check

tailscale-swarm-env: ## 输出当前节点 Swarm advertise/data-path 环境变量
	@bash $(NETWORK_SCRIPTS)/tailscale-manager.sh swarm-env

swarm-init: ## 初始化首个 Docker Swarm manager
	$(call require_param,SWARM_ADVERTISE_ADDR,make swarm-init SWARM_ADVERTISE_ADDR=100.x.x.11 SWARM_DATA_PATH_ADDR=100.x.x.11)
	@docker swarm init --advertise-addr $(SWARM_ADVERTISE_ADDR) $(if $(SWARM_DATA_PATH_ADDR),--data-path-addr $(SWARM_DATA_PATH_ADDR))
	$(call success_msg,Swarm 集群已初始化 (advertise-addr=$(SWARM_ADVERTISE_ADDR), data-path=$(if $(SWARM_DATA_PATH_ADDR),$(SWARM_DATA_PATH_ADDR),$(SWARM_ADVERTISE_ADDR))))

swarm-join-manager: ## 加入现有 Swarm 成为 manager
	$(call require_param,SWARM_MANAGER_IP,make swarm-join-manager SWARM_MANAGER_IP=100.x.x.11 SWARM_TOKEN=SWMTKN-xxx SWARM_ADVERTISE_ADDR=100.x.x.12)
	$(call require_param,SWARM_TOKEN,make swarm-join-manager SWARM_MANAGER_IP=100.x.x.11 SWARM_TOKEN=SWMTKN-xxx SWARM_ADVERTISE_ADDR=100.x.x.12)
	$(call require_param,SWARM_ADVERTISE_ADDR,make swarm-join-manager SWARM_MANAGER_IP=100.x.x.11 SWARM_TOKEN=SWMTKN-xxx SWARM_ADVERTISE_ADDR=100.x.x.12)
	@docker swarm join --token $(SWARM_TOKEN) --advertise-addr $(SWARM_ADVERTISE_ADDR) $(if $(SWARM_DATA_PATH_ADDR),--data-path-addr $(SWARM_DATA_PATH_ADDR)) $(SWARM_MANAGER_IP):2377
	$(call success_msg,已加入 Swarm manager (advertise-addr=$(SWARM_ADVERTISE_ADDR)))

swarm-join-worker: ## 加入现有 Swarm 成为 worker
	$(call require_param,SWARM_MANAGER_IP,make swarm-join-worker SWARM_MANAGER_IP=100.x.x.11 SWARM_TOKEN=SWMTKN-xxx SWARM_ADVERTISE_ADDR=100.x.x.13)
	$(call require_param,SWARM_TOKEN,make swarm-join-worker SWARM_MANAGER_IP=100.x.x.11 SWARM_TOKEN=SWMTKN-xxx SWARM_ADVERTISE_ADDR=100.x.x.13)
	$(call require_param,SWARM_ADVERTISE_ADDR,make swarm-join-worker SWARM_MANAGER_IP=100.x.x.11 SWARM_TOKEN=SWMTKN-xxx SWARM_ADVERTISE_ADDR=100.x.x.13)
	@docker swarm join --token $(SWARM_TOKEN) --advertise-addr $(SWARM_ADVERTISE_ADDR) $(if $(SWARM_DATA_PATH_ADDR),--data-path-addr $(SWARM_DATA_PATH_ADDR)) $(SWARM_MANAGER_IP):2377
	$(call success_msg,已加入 Swarm worker (advertise-addr=$(SWARM_ADVERTISE_ADDR)))

swarm-leave: ## 离开 Docker Swarm
	@docker swarm leave --force
	$(call success_msg,已离开 Swarm)

swarm-status: ## 查看 Swarm 状态
	@docker node ls 2>/dev/null || echo "$(YELLOW)未加入 Swarm 集群$(RESET)"

swarm-network-probe: ## 在 manager 上触发 infra-network 下发到所有节点
	@if ! docker node ls >/dev/null 2>&1; then \
		echo "$(RED)$(BOLD)❌ 当前节点不是 Swarm manager，请在 serverA/serverB/serverD 上执行$(RESET)"; \
		exit 1; \
	fi
	@if ! docker network inspect infra-network >/dev/null 2>&1; then \
		echo "$(RED)$(BOLD)❌ manager 上未找到 infra-network，请先执行 make init-serverA 或创建网络$(RESET)"; \
		exit 1; \
	fi
	@echo "$(BLUE)ℹ️  创建 net-probe 全局服务，触发 infra-network 下发...$(RESET)"
	@docker service rm net-probe >/dev/null 2>&1 || true
	@docker service create --mode global --name net-probe --network infra-network alpine:3.20 sleep 1d >/dev/null
	@sleep 8
	@docker service ps net-probe --format "table {{.Name}}\t{{.Node}}\t{{.CurrentState}}\t{{.Error}}"
	@docker service rm net-probe >/dev/null
	$(call success_msg,infra-network 下发探针已完成；请在目标节点重试 docker network ls 或 make serverC-up)

net-list: ## 列出所有网络
	@docker network ls --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"

net-create: ## 创建网络 (NAME=名称 DRIVER=bridge/overlay)
	$(call require_param,NAME,make net-create NAME=my-network DRIVER=bridge)
	@docker network create --driver=$(or $(DRIVER),bridge) $(NAME)
	$(call success_msg,网络创建成功: $(NAME))

net-delete: ## 删除网络 (NAME=名称)
	$(call require_param,NAME,make net-delete NAME=my-network)
	@docker network rm $(NAME)

net-inspect: ## 查看网络详情 (NAME=名称)
	$(call require_param,NAME,make net-inspect NAME=infra-network)
	@docker network inspect $(NAME)

port-check: ## 检查端口占用 (PORT=端口号)
	$(call require_param,PORT,make port-check PORT=80)
	@lsof -i :$(PORT) || echo "$(GREEN)端口 $(PORT) 未被占用$(RESET)"

# ==============================================================================
# 2. 基础设施初始化
# ==============================================================================
.PHONY: init init-serverA init-serverB init-serverC init-serverD install install-all-silent up down restart status ps

init: ## 初始化基础设施 (网络+卷)
	$(call info_msg,初始化基础设施网络和卷...)
	@$(INFRA_SCRIPT) create
	$(call success_msg,基础设施初始化完成)

init-serverA: ## 仅在 ServerA 上初始化网络和卷 (manager, nginx 节点)
	$(call info_msg,初始化 ServerA 网络和卷...)
	@INIT_TARGET=serverA $(INFRA_SCRIPT) create
	$(call success_msg,ServerA 初始化完成)

init-serverB: ## 在 ServerB 上初始化节点基线，跳过网络创建 (manager, collection+IAM 节点)
	$(call info_msg,初始化 ServerB 节点基线，跳过网络创建...)
	@INIT_TARGET=serverB SKIP_NETWORK=true $(INFRA_SCRIPT) create
	$(call success_msg,ServerB 初始化完成)

init-serverC: ## 在 ServerC 上初始化卷，跳过网络创建 (worker, Mongo 节点)
	$(call info_msg,初始化 ServerC 卷，跳过网络创建...)
	@INIT_TARGET=serverC SKIP_NETWORK=true $(INFRA_SCRIPT) create
	$(call success_msg,ServerC 初始化完成)

init-serverD: ## 在 ServerD 上初始化卷，跳过网络创建 (manager, NSQ + Monitoring 节点)
	$(call info_msg,初始化 ServerD 卷，跳过网络创建...)
	@INIT_TARGET=serverD SKIP_NETWORK=true $(INFRA_SCRIPT) create
	$(call success_msg,ServerD 初始化完成)

install: init ## 交互式安装组件
	$(call section_title,基础设施组件安装)
	@echo ""
	@echo "$(BLUE)可用组件:$(RESET)"
	@echo "  $(GREEN)1)$(RESET) Nginx   - Web 服务器 (80, 443)"
	@echo "  $(GREEN)2)$(RESET) MySQL   - 关系型数据库 (仅开发)"
	@echo "  $(GREEN)3)$(RESET) Redis   - 缓存 (6379)"
	@echo "  $(GREEN)4)$(RESET) MongoDB - 文档数据库 (27017)"
	@echo "  $(GREEN)5)$(RESET) NSQ     - 消息队列 (4150-4171)"
	@echo "  $(GREEN)6)$(RESET) All     - 安装全部"
	@echo ""
	@read -p "选择组件 (空格分隔): " choices; \
	$(INSTALL_SCRIPT) $$choices

install-all-silent: init ## 静默安装全部组件
	@$(INSTALL_SCRIPT) all

up: ## 启动所有服务
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up all

down: ## 停止所有服务
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra down all

restart: down up ## 重启所有服务

status: ## 查看服务状态
	$(call section_title,服务状态)
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

ps: status ## 查看容器 (别名)

# ==============================================================================
# 3. 组件管理 - Nginx
# ==============================================================================
.PHONY: nginx-start nginx-stop nginx-restart nginx-logs nginx-reload nginx-test

nginx-start: ## 启动 Nginx
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up nginx
	$(call success_msg,Nginx 已启动)

nginx-stop: ## 停止 Nginx
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra down nginx

nginx-restart: nginx-stop nginx-start ## 重启 Nginx

nginx-logs: ## 查看 Nginx 日志
	@docker logs -f --tail=$(LOG_LINES) nginx

nginx-reload: ## 重载 Nginx 配置
	@docker exec nginx nginx -s reload
	$(call success_msg,配置已重载)

nginx-test: ## 测试 Nginx 配置
	@docker exec nginx nginx -t

# ==============================================================================
# 3. 组件管理 - MongoDB
# ==============================================================================
.PHONY: mongo-start mongo-stop mongo-restart mongo-logs mongo-shell mongo-status
.PHONY: mongo-backup mongo-monitor mongo-tune mongo-init-users mongo-stats
.PHONY: mongo-rs-init mongo-rs-status mongo-keyfile

mongo-start: ## 启动 MongoDB
	@bash $(COMPONENTS_SCRIPTS)/prepare-mongo-keyfile.sh
	@cd $(COMPONENTS_DIR)/mongo && docker compose --env-file ../../$(ENV_FILE_C) up -d
	@bash $(COMPONENTS_SCRIPTS)/init-mongo-replica-set.sh
	$(call success_msg,MongoDB 已启动)

mongo-stop: ## 停止 MongoDB
	@cd $(COMPONENTS_DIR)/mongo && docker compose --env-file ../../$(ENV_FILE_C) down

mongo-restart: mongo-stop mongo-start ## 重启 MongoDB

mongo-logs: ## 查看 MongoDB 日志
	@docker logs -f --tail=$(LOG_LINES) mongo

mongo-shell: ## 进入 MongoDB Shell
	@set -a; . $(ENV_FILE_C); set +a; docker exec -it mongo mongosh -u "$$MONGO_INITDB_ROOT_USERNAME" -p "$$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin

mongo-status: ## 查看 MongoDB 状态
	@docker ps --filter "name=mongo" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@$(MAKE) --no-print-directory mongo-rs-status || true

mongo-rs-init: ## 初始化/修复 MongoDB 单节点副本集
	@bash $(COMPONENTS_SCRIPTS)/init-mongo-replica-set.sh

mongo-rs-status: ## 查看 MongoDB 副本集状态
	@set -a; . $(ENV_FILE_C); set +a; docker exec mongo mongosh -u "$$MONGO_INITDB_ROOT_USERNAME" -p "$$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet --eval "try { const hello = db.hello(); printjson({ setName: hello.setName || null, isWritablePrimary: !!hello.isWritablePrimary, secondary: !!hello.secondary, hosts: hello.hosts || [] }) } catch (e) { print(e.message); quit(1) }"

mongo-keyfile: ## 准备/校正 MongoDB 副本集 keyFile
	@bash $(COMPONENTS_SCRIPTS)/prepare-mongo-keyfile.sh

mongo-backup: ## 备份 MongoDB
	@bash $(COMPONENTS_SCRIPTS)/backup-mongo.sh

mongo-monitor: ## 监控 MongoDB 性能
	@bash $(COMPONENTS_SCRIPTS)/monitor-mongo.sh

mongo-tune: ## 系统调优 (宿主机内核参数)
	$(call warning_msg,此命令需要 root 权限)
	@sudo bash $(SERVER_SCRIPTS)/tune-host.sh

mongo-init-users: ## 创建 MongoDB 业务用户
	@bash $(COMPONENTS_SCRIPTS)/init-mongo-users.sh

mongo-stats: ## 查看 MongoDB 统计信息
	@set -a; . $(ENV_FILE_C); set +a; docker exec mongo mongosh -u "$$MONGO_INITDB_ROOT_USERNAME" -p "$$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet --eval "db.serverStatus()" | head -50

# ==============================================================================
# 3. 组件管理 - Redis
# ==============================================================================
.PHONY: redis-start redis-stop redis-restart redis-logs redis-cli redis-info redis-status
.PHONY: redis-cache-logs redis-cache-cli redis-cache-info redis-cache-shell
.PHONY: redis-clean redis-rebuild redis-acl-regenerate redis-acl-list redis-test

redis-start: ## 启动 Redis Cache
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up storage
	$(call success_msg,Redis 已启动 (6379))

redis-stop: ## 停止 Redis
	@docker stop redis-cache 2>/dev/null || true

redis-restart: redis-stop redis-start ## 重启 Redis

redis-logs: ## 查看 Redis 日志
	@docker logs -f --tail=$(LOG_LINES) redis-cache

redis-cli: ## 进入 Redis CLI
	@docker exec -it redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}"

redis-info: ## 查看 Redis 详细信息
	@echo "$(CYAN)=== Redis Cache Info ===$(RESET)"
	@docker exec redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}" --no-auth-warning INFO server | grep -E "redis_version|redis_mode|uptime_in_seconds" 2>/dev/null || echo "未运行"
	@docker exec redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}" --no-auth-warning INFO memory | grep -E "used_memory_human|maxmemory_human" 2>/dev/null || true

redis-status: ## 查看 Redis 状态
	@docker ps --filter "name=redis-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

redis-cache-logs: ## 查看 Redis Cache 日志
	@docker logs -f --tail=$(LOG_LINES) redis-cache

redis-cache-cli: ## 进入 Redis Cache CLI
	@docker exec -it redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}"

redis-cache-info: ## 查看 Redis Cache 详细信息
	@docker exec redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}" --no-auth-warning INFO

redis-cache-shell: ## 进入 Redis Cache 容器 Shell
	@docker exec -it redis-cache sh

redis-clean: ## 清理 Redis 数据 (危险!)
	@echo "$(RED)警告: 即将删除所有 Redis 数据！$(RESET)"
	@read -p "确认 (yes/no): " confirm && [ "$$confirm" = "yes" ] || exit 1
	@cd $(COMPONENTS_DIR)/redis && ENV=$(ENV) bash rebuild.sh --clean-only

redis-rebuild: ## 完全重建 Redis (清理+部署)
	@echo "$(RED)警告: 即将删除所有 Redis 数据并重建！$(RESET)"
	@read -p "确认 (yes/no): " confirm && [ "$$confirm" = "yes" ] || exit 1
	@cd $(COMPONENTS_DIR)/redis && ENV=$(ENV) bash rebuild.sh

redis-acl-regenerate: ## 重新生成 Redis ACL 配置
	@cd $(COMPONENTS_DIR)/redis && ENV=$(ENV) bash generate-acl.sh
	$(call warning_msg,需要重启 Redis 使配置生效: make redis-restart)

redis-acl-list: ## 查看 Redis ACL 用户列表
	@docker exec redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}" ACL LIST 2>/dev/null || echo "$(RED)无法连接$(RESET)"

redis-test: ## 测试 Redis 功能
	@cd $(COMPONENTS_DIR)/redis && ENV=$(ENV) bash test-redis.sh

# ==============================================================================
# 3. 组件管理 - NSQ
# ==============================================================================
.PHONY: nsq-start nsq-stop nsq-restart nsq-logs nsq-status nsq-admin
.PHONY: nsq-shell nsq-lookupd-logs nsq-admin-logs nsq-topics nsq-stats

nsq-start: ## 启动 NSQ
	@cd $(COMPONENTS_DIR)/nsq && docker compose --env-file ../../$(ENV_FILE_D) up -d
	$(call success_msg,NSQ 已启动)

nsq-stop: ## 停止 NSQ
	@docker stop nsqd nsqlookupd nsqadmin 2>/dev/null || true

nsq-restart: nsq-stop nsq-start ## 重启 NSQ

nsq-logs: ## 查看 NSQd 日志
	@docker logs -f --tail=$(LOG_LINES) nsqd

nsq-lookupd-logs: ## 查看 NSQLookupd 日志
	@docker logs -f --tail=$(LOG_LINES) nsqlookupd

nsq-admin-logs: ## 查看 NSQAdmin 日志
	@docker logs -f --tail=$(LOG_LINES) nsqadmin

nsq-status: ## 查看 NSQ 状态
	@docker ps --filter "name=nsq" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

nsq-shell: ## 进入 NSQd 容器 Shell
	@docker exec -it nsqd sh

nsq-topics: ## 查看 NSQ Topics
	@echo "$(CYAN)=== NSQ Topics ===$(RESET)"
	@curl -s http://localhost:4151/stats?format=json 2>/dev/null | grep -o '"topic_name":"[^"]*"' | cut -d'"' -f4 || echo "$(YELLOW)无法获取$(RESET)"

nsq-stats: ## 查看 NSQ 统计信息
	@curl -s http://localhost:4151/stats 2>/dev/null | head -30 || echo "$(RED)无法连接到 NSQd$(RESET)"

nsq-admin: ## NSQ Admin 访问说明
	@echo "$(YELLOW)NSQAdmin 仅本机访问:$(RESET)"
	@echo "  1. SSH 隧道: $(CYAN)ssh -L 4171:127.0.0.1:4171 user@serverD$(RESET)"
	@echo "  2. 浏览器: $(CYAN)http://localhost:4171$(RESET)"

# ==============================================================================
# 3. 组件管理 - MySQL (仅开发)
# ==============================================================================
.PHONY: mysql-start mysql-stop mysql-logs mysql-shell

mysql-start: ## 启动 MySQL (仅开发环境)
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up storage
	$(call success_msg,MySQL 已启动)

mysql-stop: ## 停止 MySQL
	@docker stop mysql 2>/dev/null || true

mysql-logs: ## 查看 MySQL 日志
	@docker logs -f --tail=$(LOG_LINES) mysql

mysql-shell: ## 进入 MySQL Shell
	@docker exec -it mysql bash

# ==============================================================================
# 3. 组件管理 - Prometheus
# ==============================================================================
.PHONY: prometheus-start prometheus-stop prometheus-restart prometheus-logs prometheus-status prometheus-targets

prometheus-start: ## 在 ServerD 启动 Prometheus
	$(call section_title,启动 Prometheus (serverD))
	$(call ensure_infra_network_visible)
	@$(MAKE) init-serverD
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env up -d prometheus
	$(call success_msg,Prometheus 已启动)

prometheus-stop: ## 停止 Prometheus
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env stop prometheus 2>/dev/null || docker stop prometheus 2>/dev/null || true

prometheus-restart: prometheus-stop prometheus-start ## 重启 Prometheus

prometheus-logs: ## 查看 Prometheus 日志
	@docker logs -f --tail=$(LOG_LINES) prometheus

prometheus-status: ## 查看 Prometheus 状态
	@docker ps --filter "name=prometheus" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

prometheus-targets: ## 查看 Prometheus 抓取目标状态
	@docker exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool

# ==============================================================================
# 3. 组件管理 - Grafana
# ==============================================================================
.PHONY: grafana-start grafana-stop grafana-restart grafana-logs grafana-status grafana-nginx-deploy

grafana-start: ## 在 ServerD 启动 Grafana
	$(call section_title,启动 Grafana (serverD))
	$(call ensure_infra_network_visible)
	@$(MAKE) init-serverD
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env up -d prometheus grafana
	$(call success_msg,Grafana 已启动)

grafana-stop: ## 停止 Grafana
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env stop grafana 2>/dev/null || docker stop grafana 2>/dev/null || true

grafana-restart: grafana-stop grafana-start ## 重启 Grafana

grafana-logs: ## 查看 Grafana 日志
	@docker logs -f --tail=$(LOG_LINES) grafana

grafana-status: ## 查看 Grafana 状态
	@docker ps --filter "name=grafana" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

grafana-nginx-deploy: ## 部署 Grafana Nginx 配置到 /data/apps/nginx-configs
	@bash $(NGINX_SCRIPTS)/nginx-app-manager.sh deploy grafana components/grafana/nginx/grafana.conf

# ==============================================================================
# 4. SSL证书管理
# ==============================================================================
.PHONY: ssl-wildcard ssl-obtain ssl-import ssl-renew ssl-list ssl-remove ssl-setup-aliyun
.PHONY: ssl-dev ssl-dev-force ssl-dev-list ssl-dev-verify ssl-dev-remove
.PHONY: grpc-ca grpc-server grpc-generate-all grpc-verify grpc-info grpc-clean

ssl-wildcard: ## 申请通配符证书 (DOMAIN=域名 EMAIL=邮箱)
	$(call require_param,DOMAIN,make ssl-wildcard DOMAIN=example.com EMAIL=admin@example.com)
	$(call require_param,EMAIL,make ssl-wildcard DOMAIN=example.com EMAIL=admin@example.com)
	@$(SSL_SCRIPTS)/ssl-manager.sh wildcard $(DOMAIN) $(EMAIL)

ssl-obtain: ## 申请单域名证书 (DOMAIN=域名 EMAIL=邮箱)
	$(call require_param,DOMAIN,make ssl-obtain DOMAIN=example.com EMAIL=admin@example.com)
	$(call require_param,EMAIL,make ssl-obtain DOMAIN=example.com EMAIL=admin@example.com)
	@$(SSL_SCRIPTS)/ssl-manager.sh obtain $(DOMAIN) $(EMAIL)

ssl-import: ## 导入证书 (DOMAIN=域名 CERT=证书路径 KEY=私钥路径)
	$(call require_param,DOMAIN,make ssl-import DOMAIN=example.com CERT=/path/cert.pem KEY=/path/key.pem)
	@$(SSL_SCRIPTS)/ssl-manager.sh import $(DOMAIN) $(CERT) $(KEY)

ssl-renew: ## 续期所有证书
	@$(SSL_SCRIPTS)/ssl-manager.sh renew

ssl-list: ## 列出所有证书
	@$(SSL_SCRIPTS)/ssl-manager.sh list

ssl-remove: ## 删除证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-remove DOMAIN=example.com)
	@$(SSL_SCRIPTS)/ssl-manager.sh remove $(DOMAIN)

ssl-setup-aliyun: ## 配置阿里云 DNS API
	@$(SSL_SCRIPTS)/ssl-manager.sh setup-aliyun

# 开发环境 SSL 证书管理（自签名）
ssl-dev: ## 生成开发环境自签名证书 (DOMAIN=域名，默认 localhost)
	@$(SSL_SCRIPTS)/dev-ssl.sh generate $(or $(DOMAIN),localhost)
	$(call success_msg,开发证书生成完成: $(or $(DOMAIN),localhost))

ssl-dev-force: ## 强制重新生成开发证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-dev-force DOMAIN=iam-apiserver)
	@$(SSL_SCRIPTS)/dev-ssl.sh force $(DOMAIN)
	$(call success_msg,开发证书已重新生成: $(DOMAIN))

ssl-dev-list: ## 列出所有开发环境证书
	@$(SSL_SCRIPTS)/dev-ssl.sh list

ssl-dev-verify: ## 验证开发证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-dev-verify DOMAIN=iam-apiserver)
	@$(SSL_SCRIPTS)/dev-ssl.sh verify $(DOMAIN)

ssl-dev-remove: ## 删除开发证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-dev-remove DOMAIN=iam-apiserver)
	@$(SSL_SCRIPTS)/dev-ssl.sh remove $(DOMAIN)
	$(call warning_msg,开发证书已删除: $(DOMAIN))

# gRPC mTLS 证书管理
grpc-ca: ## 生成 gRPC Root CA 和 Intermediate CA
	@$(SSL_SCRIPTS)/grpc-mtls.sh generate-ca
	$(call success_msg,gRPC CA 证书生成完成)

grpc-server: ## 生成 gRPC 双向证书 (NAME=服务名 OU=组织单元 ALT_DNS=额外DNS TYPE=dual|server|client)
	$(call require_param,NAME,make grpc-server NAME=iam-apiserver OU=IAM ALT_DNS=iam-apiserver.example.com)
	@$(SSL_SCRIPTS)/grpc-mtls.sh generate-server $(NAME) $(or $(OU),IAM) $(ALT_DNS) $(or $(TYPE),dual)
	$(call success_msg,证书生成完成: $(NAME) (类型: $(or $(TYPE),dual)))

grpc-dual: ## 生成 gRPC 双向证书 (简化命令，等同于 TYPE=dual)
	$(call require_param,NAME,make grpc-dual NAME=qs-collection-server OU=QS ALT_DNS=collect.example.com)
	@$(SSL_SCRIPTS)/grpc-mtls.sh generate-server $(NAME) $(or $(OU),IAM) $(ALT_DNS) dual
	$(call success_msg,双向证书生成完成: $(NAME))

grpc-generate-all: ## 生成所有 gRPC 证书（CA + 默认双向证书）
	@$(SSL_SCRIPTS)/grpc-mtls.sh generate
	$(call success_msg,所有 gRPC 证书生成完成)

grpc-verify: ## 验证 gRPC 证书有效性
	@$(SSL_SCRIPTS)/grpc-mtls.sh verify

grpc-info: ## 查看 gRPC 证书信息
	@$(SSL_SCRIPTS)/grpc-mtls.sh info

grpc-clean: ## 清理 gRPC 证书 (TYPE=server|client|ca NAME=服务名)
	@$(SSL_SCRIPTS)/grpc-mtls.sh clean $(TYPE) $(NAME)
	$(call warning_msg,gRPC 证书已清理)

# ==============================================================================
# 5. Nginx应用管理
# ==============================================================================
.PHONY: app-deploy app-remove app-list app-enable app-disable

app-deploy: ## 部署应用配置 (APP=名称 DOMAIN=域名 PORT=端口)
	$(call require_param,APP,make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000)
	$(call require_param,DOMAIN,make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000)
	$(call require_param,PORT,make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000)
	@$(NGINX_SCRIPTS)/nginx-app-manager.sh deploy $(APP) $(DOMAIN) $(PORT) $(or $(SSL),no)
	$(call success_msg,应用配置部署成功: $(APP))

app-remove: ## 删除应用配置 (APP=名称)
	$(call require_param,APP,make app-remove APP=myapp)
	@$(NGINX_SCRIPTS)/nginx-app-manager.sh remove $(APP)

app-list: ## 列出应用配置
	@$(NGINX_SCRIPTS)/nginx-app-manager.sh list

app-enable: ## 启用应用 (APP=名称)
	$(call require_param,APP,make app-enable APP=myapp)
	@$(NGINX_SCRIPTS)/nginx-app-manager.sh enable $(APP)
	@$(MAKE) nginx-reload

app-disable: ## 禁用应用 (APP=名称)
	$(call require_param,APP,make app-disable APP=myapp)
	@$(NGINX_SCRIPTS)/nginx-app-manager.sh disable $(APP)
	@$(MAKE) nginx-reload

# ==============================================================================
# 6. 运维监控
# ==============================================================================
.PHONY: test-all test-nginx test-redis test-mongo test-nsq stats logs troubleshoot disk-usage

test-all: ## 测试所有服务
	$(call section_title,服务连接测试)
	@$(MAKE) test-nginx || true
	@$(MAKE) test-mongo || true
	@$(MAKE) test-nsq || true

test-nginx: ## 测试 Nginx
	@printf "$(BLUE)Nginx:$(RESET)   "
	@curl -s -o /dev/null -w "%{http_code}" http://localhost 2>/dev/null | grep -q 200 && echo "$(GREEN)✅$(RESET)" || echo "$(RED)❌$(RESET)"

test-redis: ## 测试本地 Redis 组件（可选）
	@printf "$(BLUE)Redis:$(RESET)   "
	@docker exec redis-cache redis-cli --user admin -a "$${REDIS_ADMIN_PASSWORD}" --no-auth-warning ping 2>/dev/null | grep -q PONG && echo "$(GREEN)✅$(RESET)" || echo "$(RED)❌$(RESET)"

test-mongo: ## 测试 MongoDB
	@printf "$(BLUE)MongoDB:$(RESET) "
	@set -a; . $(ENV_FILE_C); set +a; docker exec mongo mongosh -u "$$MONGO_INITDB_ROOT_USERNAME" -p "$$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet --eval "const hello = db.hello(); print(hello.ok === 1 && hello.setName === 'rs0' && hello.isWritablePrimary ? 'OK' : 'FAIL')" 2>/dev/null | grep -q "OK" && echo "$(GREEN)✅$(RESET)" || echo "$(RED)❌$(RESET)"

test-nsq: ## 测试 NSQ
	@printf "$(BLUE)NSQ:$(RESET)     "
	@curl -s http://localhost:4171/ping 2>/dev/null | grep -q OK && echo "$(GREEN)✅$(RESET)" || echo "$(RED)❌$(RESET)"

stats: ## 资源使用统计
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

logs: ## 查看服务日志 (SERVICE=服务名)
	@if [ -n "$(SERVICE)" ]; then \
		docker logs -f --tail=$(LOG_LINES) $(SERVICE); \
	else \
		docker ps --format '{{.Names}}' | xargs -I {} sh -c 'echo "=== {} ===" && docker logs --tail=20 {}'; \
	fi

troubleshoot: ## 故障诊断
	$(call section_title,系统诊断)
	@echo "$(BLUE)1. Docker 状态$(RESET)"
	@docker version --format '{{.Server.Version}}' || echo "$(RED)Docker 未运行$(RESET)"
	@echo ""
	@echo "$(BLUE)2. 容器健康$(RESET)"
	@docker ps --format "{{.Names}}: {{.Status}}" | grep -E "unhealthy|Restarting" || echo "$(GREEN)所有容器健康$(RESET)"
	@echo ""
	@echo "$(BLUE)3. 磁盘空间$(RESET)"
	@df -h / | tail -1
	@echo ""
	@echo "$(BLUE)4. 错误日志$(RESET)"
	@docker ps --format '{{.Names}}' | head -3 | xargs -I {} sh -c 'docker logs --tail=20 {} 2>&1 | grep -i error | head -2' || true

disk-usage: ## Docker 磁盘使用
	@docker system df -v

# ==============================================================================
# 7. 服务器部署
# ==============================================================================
.PHONY: serverA-up serverA-down serverA-logs serverA-status serverA-destroy serverA-rebuild
.PHONY: serverB-up serverB-down serverB-logs serverB-status serverB-destroy serverB-rebuild
.PHONY: serverC-up serverC-down serverC-logs serverC-status serverC-destroy serverC-rebuild
.PHONY: serverD-up serverD-down serverD-logs serverD-status serverD-destroy serverD-rebuild
.PHONY: serverD-monitoring-up serverD-monitoring-down serverD-monitoring-logs serverD-monitoring-status serverD-monitoring-restart
.PHONY: server-info validate-cloud-env

serverA-up: ## 启动 ServerA 服务栈 (Nginx)
	$(call section_title,启动 ServerA (2C2G))
	@$(MAKE) init-serverA
	@cd deploy/serverA && docker compose --env-file ../../compose/env/prod/serverA.env up -d
	$(call success_msg,ServerA 服务已启动)

serverA-down: ## 停止 ServerA 服务栈
	@cd deploy/serverA && docker compose --env-file ../../compose/env/prod/serverA.env down

serverA-logs: ## 查看 ServerA 日志
	@cd deploy/serverA && docker compose --env-file ../../compose/env/prod/serverA.env logs -f --tail=$(LOG_LINES)

serverA-status: ## 查看 ServerA 状态
	@docker ps --filter "label=infra.host=serverA" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

serverA-destroy: ## 销毁 ServerA 所有容器、卷和数据 (危险!)
	@echo "$(RED)$(BOLD)⚠️  警告: 此操作将销毁 ServerA 的所有数据！$(RESET)"
	@echo "$(RED)   - 停止并删除容器: nginx$(RESET)"
	@echo "$(RED)   - 删除旧版 Docker 卷(如存在): infra_nginx_logs$(RESET)"
	@echo "$(RED)   - 删除日志目录: /data/logs/nginx/*$(RESET)"
	@echo ""
	@read -p "确认销毁所有数据? 输入 'DESTROY' 继续: " confirm && [ "$$confirm" = "DESTROY" ] || (echo "已取消"; exit 1)
	$(call section_title,销毁 ServerA 数据)
	@docker rm -f nginx 2>/dev/null || true
	@docker volume rm infra_nginx_logs 2>/dev/null || true
	@rm -rf /data/logs/nginx/* 2>/dev/null || true
	$(call success_msg,ServerA 数据已销毁)

serverA-rebuild: serverA-destroy serverA-up ## 完全重建 ServerA (销毁后重建)

serverB-up: ## 初始化 ServerB 节点基线 (collection + IAM 由业务仓库部署)
	$(call section_title,启动 ServerB (2C2G))
	$(call ensure_infra_network_visible)
	@$(MAKE) init-serverB
	$(call warning_msg,ServerB 当前没有 infra 仓库直接维护的本地组件；qs-collection-server 与 IAM 请由业务仓库部署)

serverB-down: ## 停止 ServerB infra 服务栈
	$(call warning_msg,ServerB 当前没有 infra 仓库直接维护的本地组件)

serverB-logs: ## 查看 ServerB 日志
	$(call warning_msg,ServerB 当前没有 infra 仓库直接维护的本地组件日志)

serverB-status: ## 查看 ServerB 状态
	@docker ps --filter "label=infra.host=serverB" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

serverB-destroy: ## 销毁 ServerB 所有容器、卷和数据 (危险!)
	$(call warning_msg,ServerB 当前没有 infra 仓库直接维护的本地组件；不会删除业务仓库部署的 collection/IAM)

serverB-rebuild: serverB-destroy serverB-up ## 完全重建 ServerB (销毁后重建)

serverC-up: ## 启动 ServerC 服务栈 (MongoDB)
	$(call section_title,启动 ServerC (4C4G))
	$(call ensure_infra_network_visible)
	@$(MAKE) init-serverC
	@cd deploy/serverC && docker compose --env-file ../../compose/env/prod/serverC.env up -d
	$(call success_msg,ServerC 服务已启动)

serverC-down: ## 停止 ServerC 服务栈
	@cd deploy/serverC && docker compose --env-file ../../compose/env/prod/serverC.env down

serverC-logs: ## 查看 ServerC 日志
	@cd deploy/serverC && docker compose --env-file ../../compose/env/prod/serverC.env logs -f --tail=$(LOG_LINES)

serverC-status: ## 查看 ServerC 状态
	@docker ps --filter "label=infra.host=serverC" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

serverC-destroy: ## 销毁 ServerC 所有容器、卷和数据 (危险!)
	@echo "$(RED)$(BOLD)⚠️  警告: 此操作将销毁 ServerC 的所有数据！$(RESET)"
	@echo "$(RED)   - 停止并删除容器: mongo$(RESET)"
	@echo "$(RED)   - 删除旧版 Docker 卷(如存在): infra_mongo_data$(RESET)"
	@echo "$(RED)   - 删除数据目录: /data/infra/mongo/*$(RESET)"
	@echo ""
	@read -p "确认销毁所有数据? 输入 'DESTROY' 继续: " confirm && [ "$$confirm" = "DESTROY" ] || (echo "已取消"; exit 1)
	$(call section_title,销毁 ServerC 数据)
	@docker rm -f mongo 2>/dev/null || true
	@docker volume rm infra_mongo_data 2>/dev/null || true
	@rm -rf /data/infra/mongo/* 2>/dev/null || true
	$(call success_msg,ServerC 数据已销毁)

serverC-rebuild: serverC-destroy serverC-up ## 完全重建 ServerC (销毁后重建)

serverD-up: ## 启动 ServerD 服务栈 (NSQ + Prometheus + Grafana)
	$(call section_title,启动 ServerD (2C4G))
	$(call ensure_infra_network_visible)
	@$(MAKE) init-serverD
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env up -d
	$(call success_msg,ServerD 服务已启动)

serverD-monitoring-up: ## 在 ServerD 一键启动 Prometheus + Grafana
	$(call section_title,启动 ServerD Monitoring)
	$(call ensure_infra_network_visible)
	@$(MAKE) init-serverD
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env up -d prometheus grafana
	$(call success_msg,ServerD Prometheus + Grafana 已启动)

serverD-monitoring-down: ## 停止 ServerD Prometheus + Grafana
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env stop grafana prometheus

serverD-monitoring-logs: ## 查看 ServerD Prometheus + Grafana 日志
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env logs -f --tail=$(LOG_LINES) prometheus grafana

serverD-monitoring-status: ## 查看 ServerD Prometheus + Grafana 状态
	@docker ps --filter "label=infra.host=serverD" --filter "label=infra.category=observability" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

serverD-monitoring-restart: serverD-monitoring-down serverD-monitoring-up ## 重启 ServerD Prometheus + Grafana

serverD-down: ## 停止 ServerD 服务栈
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env down

serverD-logs: ## 查看 ServerD 日志
	@cd deploy/serverD && docker compose --env-file ../../compose/env/prod/serverD.env logs -f --tail=$(LOG_LINES)

serverD-status: ## 查看 ServerD 状态
	@docker ps --filter "label=infra.host=serverD" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

serverD-destroy: ## 销毁 ServerD 所有容器、卷和数据 (危险!)
	@echo "$(RED)$(BOLD)⚠️  警告: 此操作将销毁 ServerD 的 NSQ / Prometheus / Grafana 数据！$(RESET)"
	@echo "$(RED)   - 停止并删除容器: nsqlookupd, nsqd, nsqadmin, prometheus, grafana$(RESET)"
	@echo "$(RED)   - 删除旧版 Docker 卷(如存在): infra_nsq_data, infra_prometheus_data, infra_grafana_data$(RESET)"
	@echo "$(RED)   - 删除数据目录: /data/infra/nsq/*, /data/infra/prometheus/*, /data/infra/grafana/*, /data/logs/nsq/*$(RESET)"
	@echo ""
	@read -p "确认销毁所有数据? 输入 'DESTROY' 继续: " confirm && [ "$$confirm" = "DESTROY" ] || (echo "已取消"; exit 1)
	$(call section_title,销毁 ServerD 数据)
	@docker rm -f nsqlookupd nsqd nsqadmin prometheus grafana 2>/dev/null || true
	@docker volume rm infra_nsq_data infra_prometheus_data infra_grafana_data 2>/dev/null || true
	@rm -rf /data/infra/nsq/* /data/infra/prometheus/* /data/infra/grafana/* /data/logs/nsq/* 2>/dev/null || true
	$(call success_msg,ServerD 数据已销毁)

serverD-rebuild: serverD-destroy serverD-up ## 完全重建 ServerD (销毁后重建)

server-info: ## 显示当前服务器架构
	$(call section_title,当前基础设施架构)
	@echo ""
	@echo "$(CYAN)┌─────────────────────────────────────────────────────────┐$(RESET)"
	@echo "$(CYAN)│            ServerA (2C2G) - 网关 + qs-apiserver         │$(RESET)"
	@echo "$(CYAN)├─────────────────────────────────────────────────────────┤$(RESET)"
	@echo "$(CYAN)│  $(GREEN)Nginx$(RESET) (infra 管理) + $(GREEN)qs-apiserver$(RESET) (业务仓库部署)          $(CYAN)│$(RESET)"
	@echo "$(CYAN)│  $(YELLOW)80/443$(RESET)                                             $(CYAN)│$(RESET)"
	@echo "$(CYAN)└─────────────────────────────────────────────────────────┘$(RESET)"
	@echo ""
	@echo "$(CYAN)┌─────────────────────────────────────────────────────────┐$(RESET)"
	@echo "$(CYAN)│          ServerB (2C2G) - collection + IAM             │$(RESET)"
	@echo "$(CYAN)├─────────────────────────────────────────────────────────┤$(RESET)"
	@echo "$(CYAN)│  $(GREEN)qs-collection-server$(RESET) / $(GREEN)IAM$(RESET) 由业务仓库部署          $(CYAN)│$(RESET)"
	@echo "$(CYAN)│  依赖: qs-apiserver / nsq / mongo / 云 MySQL / 云 Redis │$(RESET)"
	@echo "$(CYAN)└─────────────────────────────────────────────────────────┘$(RESET)"
	@echo ""
	@echo "$(CYAN)┌─────────────────────────────────────────────────────────┐$(RESET)"
	@echo "$(CYAN)│          ServerC (4C4G) - MongoDB (跨云 worker)        │$(RESET)"
	@echo "$(CYAN)├─────────────────────────────────────────────────────────┤$(RESET)"
	@echo "$(CYAN)│  $(GREEN)MongoDB$(RESET) (infra 管理)                               $(CYAN)│$(RESET)"
	@echo "$(CYAN)│  $(YELLOW)127.0.0.1:27017$(RESET) + overlay: $(YELLOW)mongo:27017$(RESET)          $(CYAN)│$(RESET)"
	@echo "$(CYAN)└─────────────────────────────────────────────────────────┘$(RESET)"
	@echo ""
	@echo "$(CYAN)┌─────────────────────────────────────────────────────────┐$(RESET)"
	@echo "$(CYAN)│ ServerD (2C4G) - worker + operating + NSQ + monitoring │$(RESET)"
	@echo "$(CYAN)├─────────────────────────────────────────────────────────┤$(RESET)"
	@echo "$(CYAN)│  $(GREEN)nsqlookupd$(RESET) $(GREEN)nsqd$(RESET) $(GREEN)nsqadmin$(RESET) $(GREEN)prometheus$(RESET) $(GREEN)grafana$(RESET) (infra 管理) │$(RESET)"
	@echo "$(CYAN)│  $(YELLOW)4160/4161$(RESET) $(YELLOW)4150/4151$(RESET) $(YELLOW)4171$(RESET)                           $(CYAN)│$(RESET)"
	@echo "$(CYAN)│  + $(GREEN)qs-worker$(RESET) / $(GREEN)operating$(RESET) / $(GREEN)miniblog$(RESET) / $(GREEN)qlume$(RESET) 由业务仓库部署 │$(RESET)"
	@echo "$(CYAN)└─────────────────────────────────────────────────────────┘$(RESET)"
	@echo ""
	@echo "$(MAGENTA)云托管:$(RESET) MySQL (云服务商 A RDS) + Redis (云服务商 A)"
	@echo ""

validate-cloud-env: ## 校验云服务配置
	$(call section_title,校验云服务配置)
	@echo ""
	@echo "$(BLUE)检查 serverA.env:$(RESET)"
	@grep -q "^MYSQL_HOST=your-rds" compose/env/prod/serverA.env 2>/dev/null && echo "  $(RED)❌ MYSQL_HOST 未配置$(RESET)" || echo "  $(GREEN)✅ MYSQL_HOST 已配置$(RESET)"
	@grep -q "^REDIS_HOST=your-redis" compose/env/prod/serverA.env 2>/dev/null && echo "  $(RED)❌ REDIS_HOST 未配置$(RESET)" || echo "  $(GREEN)✅ REDIS_HOST 已配置$(RESET)"
	@echo "$(BLUE)检查 serverD.env:$(RESET)"
	@grep -q "^NSQD_BROADCAST_ADDRESS=.*NODE_D_IP" compose/env/prod/serverD.env 2>/dev/null && echo "  $(GREEN)✅ NSQD 广播地址指向 serverD$(RESET)" || echo "  $(YELLOW)⚠️  请确认 NSQD_BROADCAST_ADDRESS 指向 serverD 可达地址$(RESET)"
	@echo "$(BLUE)检查 serverC.env:$(RESET)"
	@grep -q "^MONGO_INITDB_ROOT_PASSWORD=change_me" compose/env/prod/serverC.env 2>/dev/null && echo "  $(RED)❌ MongoDB 密码仍为占位值$(RESET)" || echo "  $(GREEN)✅ MongoDB 密码已配置$(RESET)"
	@echo ""

# ==============================================================================
# 维护清理
# ==============================================================================
.PHONY: clean clean-all clean-volumes clean-networks clean-images prune backup shell

clean: ## 清理停止的容器和悬空镜像
	@docker container prune -f
	@docker image prune -f
	$(call success_msg,清理完成)

clean-all: ## 清理全部未使用资源 (危险!)
	$(call error_msg,警告: 这将清理所有未使用的容器、网络、镜像!)
	@read -p "确认? (yes): " confirm; \
	[ "$$confirm" = "yes" ] && docker system prune -a -f

clean-volumes: ## 清理未使用的数据卷 (危险!)
	$(call error_msg,警告: 这将删除所有未使用的数据卷!)
	@read -p "确认? (yes): " confirm; \
	[ "$$confirm" = "yes" ] && docker volume prune -f

clean-networks: ## 清理未使用的网络
	@docker network prune -f
	$(call success_msg,网络清理完成)

clean-images: ## 清理悬空镜像
	@docker image prune -f
	$(call success_msg,镜像清理完成)

prune: clean ## 清理 (别名)

backup: ## 备份数据卷 (TARGET=/path)
	$(call require_param,TARGET,make backup TARGET=/backup)
	@mkdir -p $(TARGET)
	@for volume in $$(docker volume ls -q | grep infra); do \
		echo "$(CYAN)备份: $$volume$(RESET)"; \
		docker run --rm -v $$volume:/src -v $(TARGET):/dst alpine tar czf /dst/$$volume-$$(date +%Y%m%d).tar.gz -C /src .; \
	done
	$(call success_msg,备份完成)

shell: ## 进入容器 Shell (NAME=容器名)
	$(call require_param,NAME,make shell NAME=nginx)
	@docker exec -it $(NAME) sh || docker exec -it $(NAME) bash

# ==============================================================================
# 环境管理
# ==============================================================================
.PHONY: env-init env-edit env-show env-copy dev prod

env-init: ## 初始化环境配置
	@if [ ! -f "$(ENV_FILE)" ]; then \
		mkdir -p compose/env/$(ENV); \
		touch "$(ENV_FILE)"; \
		echo "$(GREEN)✅ 已创建: $(ENV_FILE)$(RESET)"; \
	else \
		echo "$(YELLOW)⚠️  已存在: $(ENV_FILE)$(RESET)"; \
	fi

env-edit: ## 编辑环境配置
	@$${EDITOR:-vi} $(ENV_FILE)

env-show: ## 显示环境配置
	@echo "$(CYAN)环境: $(ENV)$(RESET)"
	@echo "$(CYAN)文件: $(ENV_FILE)$(RESET)"
	@cat $(ENV_FILE) 2>/dev/null | grep -E '^[^#]' | head -15 || true

env-copy: ## 复制环境配置 (FROM=源 TO=目标)
	$(call require_param,FROM,make env-copy FROM=dev TO=prod)
	$(call require_param,TO,make env-copy FROM=dev TO=prod)
	@mkdir -p compose/env/$(TO)
	@cp compose/env/$(FROM)/.env compose/env/$(TO)/.env
	$(call success_msg,已复制配置: $(FROM) -> $(TO))

dev: ## 切换到开发环境
	@$(MAKE) ENV=dev status

prod: ## 切换到生产环境
	@$(MAKE) ENV=prod status

# ==============================================================================
# 快速参考
# ==============================================================================
.PHONY: help-mongo help-redis help-nsq help-vpn help-ssl service-ports

help-redis: ## Redis 快速参考
	$(call section_title,Redis 管理命令)
	@echo ""
	@echo "$(BLUE)基础操作:$(RESET)"
	@echo "  $(CYAN)make redis-start$(RESET)      启动 Redis Cache"
	@echo "  $(CYAN)make redis-stop$(RESET)       停止"
	@echo "  $(CYAN)make redis-restart$(RESET)    重启"
	@echo "  $(CYAN)make redis-cli$(RESET)        进入 CLI"
	@echo ""
	@echo "$(BLUE)监控运维:$(RESET)"
	@echo "  $(CYAN)make redis-info$(RESET)       查看详细信息"
	@echo "  $(CYAN)make redis-status$(RESET)     查看状态"
	@echo "  $(CYAN)make redis-test$(RESET)       测试功能"
	@echo ""
	@echo "$(BLUE)高级操作:$(RESET)"
	@echo "  $(CYAN)make redis-acl-list$(RESET)   查看 ACL 用户"
	@echo "  $(CYAN)make redis-acl-regenerate$(RESET) 重新生成 ACL"
	@echo "  $(CYAN)make redis-rebuild$(RESET)    完全重建 (危险)"
	@echo ""
	@echo "$(BLUE)配置说明:$(RESET)"
	@echo "  容器: redis-cache, 端口: 6379"
	@echo "  资源: 192M/0.12C"
	@echo "  注: Redis-Store 已迁移到阿里云"
	@echo ""

help-mongo: ## MongoDB 快速参考
	$(call section_title,MongoDB 管理命令)
	@echo ""
	@echo "$(BLUE)基础操作:$(RESET)"
	@echo "  $(CYAN)make mongo-start$(RESET)      启动"
	@echo "  $(CYAN)make mongo-stop$(RESET)       停止"
	@echo "  $(CYAN)make mongo-shell$(RESET)      连接 Shell"
	@echo "  $(CYAN)make mongo-keyfile$(RESET)    准备副本集 keyFile"
	@echo "  $(CYAN)make mongo-rs-init$(RESET)    初始化/修复单节点副本集"
	@echo "  $(CYAN)make mongo-rs-status$(RESET)  查看副本集状态"
	@echo ""
	@echo "$(BLUE)监控运维:$(RESET)"
	@echo "  $(CYAN)make mongo-monitor$(RESET)    实时监控"
	@echo "  $(CYAN)make mongo-backup$(RESET)     备份数据"
	@echo "  $(CYAN)make mongo-stats$(RESET)      统计信息"
	@echo ""
	@echo "$(BLUE)初始化:$(RESET)"
	@echo "  $(CYAN)make mongo-tune$(RESET)       系统调优 (首次)"
	@echo "  $(CYAN)make mongo-init-users$(RESET) 创建业务用户"
	@echo ""
	@echo "$(BLUE)配置说明:$(RESET)"
	@echo "  容器: mongo, 端口: 27017, 模式: 单节点副本集(rs0)"
	@echo "  宿主机: serverC (4C4G)"
	@echo "  资源: 3072M/3.00C"
	@echo ""

help-nsq: ## NSQ 快速参考
	$(call section_title,NSQ 管理命令)
	@echo ""
	@echo "$(BLUE)基础操作:$(RESET)"
	@echo "  $(CYAN)make nsq-start$(RESET)        启动全部组件"
	@echo "  $(CYAN)make nsq-stop$(RESET)         停止"
	@echo "  $(CYAN)make nsq-status$(RESET)       查看状态"
	@echo ""
	@echo "$(BLUE)日志查看:$(RESET)"
	@echo "  $(CYAN)make nsq-logs$(RESET)         NSQd 日志"
	@echo "  $(CYAN)make nsq-lookupd-logs$(RESET) Lookupd 日志"
	@echo "  $(CYAN)make nsq-admin-logs$(RESET)   Admin 日志"
	@echo ""
	@echo "$(BLUE)监控:$(RESET)"
	@echo "  $(CYAN)make nsq-topics$(RESET)       查看 Topics"
	@echo "  $(CYAN)make nsq-stats$(RESET)        统计信息"
	@echo "  $(CYAN)make nsq-admin$(RESET)        Admin 访问说明"
	@echo ""
	@echo "$(BLUE)配置说明:$(RESET)"
	@echo "  nsqlookupd: 4160/4161, nsqd: 4150/4151, admin: 4171"
	@echo "  部署在 ServerD (2C4G)"
	@echo ""

help-vpn: ## VPN 快速参考
	$(call section_title,VPN 管理命令 - Mihomo)
	@echo ""
	@echo "$(BLUE)安装卸载:$(RESET)"
	@echo "  $(CYAN)make vpn-setup$(RESET)        安装配置 VPN"
	@echo "  $(CYAN)make vpn-uninstall$(RESET)    卸载 VPN"
	@echo ""
	@echo "$(BLUE)日常操作:$(RESET)"
	@echo "  $(CYAN)make vpn-status$(RESET)       查看状态"
	@echo "  $(CYAN)make vpn-enable$(RESET)       启用 VPN"
	@echo "  $(CYAN)make vpn-disable$(RESET)      禁用 (直连)"
	@echo ""
	@echo "$(BLUE)代理管理:$(RESET)"
	@echo "  $(CYAN)make vpn-proxies$(RESET)      显示代理组"
	@echo "  $(CYAN)make vpn-switch$(RESET)       切换代理 (交互)"
	@echo ""
	@echo "$(BLUE)测试诊断:$(RESET)"
	@echo "  $(CYAN)make vpn-test$(RESET)         测试连接"
	@echo "  $(CYAN)make vpn-docker-test$(RESET)  测试容器 VPN"
	@echo "  $(CYAN)make vpn-diagnose$(RESET)     网络诊断"
	@echo ""

help-ssl: ## SSL 证书快速参考
	$(call section_title,SSL 证书管理命令)
	@echo ""
	@echo "$(BLUE)申请证书:$(RESET)"
	@echo "  $(CYAN)make ssl-wildcard DOMAIN=xxx EMAIL=xxx$(RESET)"
	@echo "    申请通配符证书 (*.domain.com)"
	@echo ""
	@echo "  $(CYAN)make ssl-obtain DOMAIN=xxx EMAIL=xxx$(RESET)"
	@echo "    申请单域名证书"
	@echo ""
	@echo "$(BLUE)管理证书:$(RESET)"
	@echo "  $(CYAN)make ssl-list$(RESET)         列出所有证书"
	@echo "  $(CYAN)make ssl-renew$(RESET)        续期所有证书"
	@echo "  $(CYAN)make ssl-remove DOMAIN=xxx$(RESET)"
	@echo "    删除证书"
	@echo ""
	@echo "$(BLUE)导入证书:$(RESET)"
	@echo "  $(CYAN)make ssl-import DOMAIN=xxx CERT=xxx KEY=xxx$(RESET)"
	@echo ""
	@echo "$(BLUE)阿里云配置:$(RESET)"
	@echo "  $(CYAN)make ssl-setup-aliyun$(RESET) 配置 DNS API"
	@echo ""

service-ports: ## 显示所有服务端口
	$(call section_title,服务端口映射)
	@echo "$(CYAN)Nginx:$(RESET)       80, 443                [serverA]"
	@echo "$(CYAN)MongoDB:$(RESET)     127.0.0.1:27017        [serverC 宿主机]"
	@echo "$(CYAN)MongoDB:$(RESET)     mongo:27017            [infra-network]"
	@echo "$(CYAN)NSQ:$(RESET)         4150, 4151, 4160, 4161 [serverD]"
	@echo "$(CYAN)NSQAdmin:$(RESET)    127.0.0.1:4171         [serverD]"
	@echo "$(CYAN)Prometheus:$(RESET)  prometheus:9090        [serverD / infra-network]"
	@echo "$(CYAN)Grafana:$(RESET)     grafana:3000           [serverD / infra-network]"
	@echo "$(CYAN)MySQL:$(RESET)       云托管地址             [云服务商 A]"
	@echo "$(CYAN)Redis:$(RESET)       云托管地址             [云服务商 A]"
	@echo ""

# ==============================================================================

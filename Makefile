# Infrastructure Management Makefile
# 简化的基础设施项目管理工具 - 重构优化版本
# 与现有脚本系统协调工作

# ==============================================================================
# 全局变量
# ==============================================================================
PROJECT_NAME := infra
DEFAULT_ENV := dev
ENV ?= $(DEFAULT_ENV)
ENV_FILE := compose/env/$(ENV)/.env

# 加载环境变量（如果文件存在）
ifneq (,$(wildcard $(ENV_FILE)))
    include $(ENV_FILE)
    export
endif

# 脚本路径
SCRIPTS_DIR := scripts
COMPONENTS_SCRIPTS := $(SCRIPTS_DIR)/components
SERVER_SCRIPTS := $(SCRIPTS_DIR)/server
NETWORK_SCRIPTS := $(SCRIPTS_DIR)/network
TOOLS_SCRIPTS := $(SCRIPTS_DIR)/tools

# 常用脚本
INFRA_SCRIPT := $(COMPONENTS_SCRIPTS)/init-infrastructure.sh
INSTALL_SCRIPT := $(COMPONENTS_SCRIPTS)/install.sh
COMPOSE_MANAGER := $(COMPONENTS_SCRIPTS)/compose-manager.sh
COMPOSE_MANAGER_ENV := ENV=$(ENV) ENVIRONMENT=$(ENV) INFRA_ENV=$(ENV) INFRA_ENV_TYPE=$(ENV)

# 组件配置路径
COMPONENTS_DIR := components
NETWORKS_DIR := $(COMPONENTS_DIR)/networks

# 默认参数
KAFKA_DEFAULT_PARTITIONS := 3
KAFKA_DEFAULT_REPLICAS := 1
KAFKA_BOOTSTRAP_SERVER := localhost:9092
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
# 检查必需参数
define require_param
	@if [ -z "$($(1))" ]; then \
		echo "$(RED)$(BOLD)❌ 错误: 请提供 $(1) 参数$(RESET)"; \
		echo "$(BLUE)💡 示例: $(2)$(RESET)"; \
		exit 1; \
	fi
endef

# 打印成功消息
define success_msg
	@echo "$(GREEN)✅ $(1)$(RESET)"
endef

# 打印警告消息  
define warning_msg
	@echo "$(YELLOW)⚠️  $(1)$(RESET)"
endef

# 打印错误消息
define error_msg
	@echo "$(RED)$(BOLD)❌ $(1)$(RESET)"
endef

# 打印信息消息
define info_msg
	@echo "$(BLUE)ℹ️  $(1)$(RESET)"
endef

# Shell 内部使用的辅助函数（无@前缀）
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

# 打印标题
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

.PHONY: help help-simple help-all
help: ## 显示帮助信息
	@echo ""
	@echo "$(GREEN)$(BOLD)🐳 基础设施项目管理工具$(RESET) v2.0"
	@echo ""
	@echo "$(BLUE)项目结构:$(RESET)"
	@echo "  components/             - 组件配置（自包含）"
	@echo "  env/                    - 环境变量配置"
	@echo "  scripts/                - 管理脚本"
	@echo ""
	@echo "$(BLUE)$(BOLD)核心命令:$(RESET)"
	@echo "  $(CYAN)install$(RESET)              交互式选择并安装组件"
	@echo "  $(CYAN)install-all-silent$(RESET)   静默安装所有组件 (自动化用)"
	@echo "  $(CYAN)quick-start$(RESET)          快速启动开发环境 (Nginx + MySQL + Redis 双实例)"
	@echo "  $(CYAN)full-install$(RESET)         完整安装 (使用交互式选择)"
	@echo "  $(CYAN)status$(RESET)               查看所有服务状态"
	@echo "  $(CYAN)test-all$(RESET)             测试所有服务连接"
	@echo "  $(CYAN)troubleshoot$(RESET)         运行故障诊断"
	@echo ""
	@echo "$(BLUE)模块命令:$(RESET)"
	@echo "  0. 服务器初始化: $(CYAN)server-init-users, server-install-docker$(RESET)"
	@echo "  1. 快速开始: $(CYAN)init, install (交互式), install-all-silent, up, down$(RESET)"
	@echo "  2. 环境管理: $(CYAN)env-init, env-edit, dev, prod$(RESET)"
	@echo "  3. 服务管理: $(CYAN)<service>-start/stop/logs/shell$(RESET)"
	@echo "     服务: mysql, redis (cache+store双实例), mongo, nsq"
	@echo "  4. 网络管理: $(CYAN)net-create/delete/list, swarm-*, vpn-*$(RESET)"
	@echo "  5. SSL 证书: $(CYAN)ssl-wildcard/obtain/renew/list/setup-aliyun$(RESET)"
	@echo "  6. Nginx:    $(CYAN)app-deploy/remove/list, nginx-*$(RESET)"
	@echo "  7. 监控诊断: $(CYAN)stats, logs, disk-usage$(RESET)"
	@echo "  8. 测试验证: $(CYAN)test-<service>$(RESET)"
	@echo "  9. 维护清理: $(CYAN)backup, clean, prune$(RESET)"
	@echo ""
	@echo "$(YELLOW)💡 使用 'make help-all' 查看所有命令详情$(RESET)"
	@echo ""

help-simple: help ## 显示简化帮助 (别名)

help-all: ## 显示所有命令详情
	$(call section_title,完整命令列表)
	@awk 'BEGIN { \
		FS = ":.*?## "; \
		module_order[1] = "0. 服务器初始化"; \
		module_order[2] = "1. 快速开始"; \
		module_order[3] = "2. 环境管理"; \
		module_order[4] = "3. 服务管理 - MySQL"; \
		module_order[5] = "3. 服务管理 - Redis"; \
		module_order[6] = "3. 服务管理 - MongoDB"; \
		module_order[7] = "3. 服务管理 - Kafka"; \
		module_order[8] = "3. 服务管理 - NSQ"; \
		module_order[9] = "4. 网络管理"; \
		module_order[10] = "5. SSL 证书"; \
		module_order[11] = "6. Nginx"; \
		module_order[12] = "7. 监控诊断"; \
		module_order[13] = "8. 测试验证"; \
		module_order[14] = "9. 维护清理"; \
		module_order[15] = "10. 帮助文档"; \
		modules["0. 服务器初始化"] = "^server-"; \
		modules["1. 快速开始"] = "^(check-env|check-scripts|init$$|init-infra|reset|clean-infra|install$$|install-all-silent|install-nginx|install-mysql|install-redis|install-mongo|install-kafka|install-nsq|up$$|down$$|restart$$|status$$|ps$$|health|quick-start|full-install|dev-setup|prod-setup)"; \
		modules["2. 环境管理"] = "^(dev$$|prod$$|env-init|env-copy|env-edit|env-show|config-show|config-validate)"; \
		modules["3. 服务管理 - MySQL"] = "^mysql-"; \
		modules["3. 服务管理 - Redis"] = "^redis-"; \
		modules["3. 服务管理 - MongoDB"] = "^mongo-"; \
		modules["3. 服务管理 - Kafka"] = "^kafka-"; \
		modules["3. 服务管理 - NSQ"] = "^nsq-"; \
		modules["4. 网络管理"] = "^(network-|net-|swarm-|vpn-|port-check)"; \
		modules["5. SSL 证书"] = "^ssl-"; \
		modules["6. Nginx"] = "^(nginx-|app-deploy|app-remove|app-list|app-enable|app-disable)"; \
		modules["7. 监控诊断"] = "^(stats$$|top$$|disk-usage|logs$$|troubleshoot|service-ports|diagnose)"; \
		modules["8. 测试验证"] = "^test-"; \
		modules["9. 维护清理"] = "^(backup|clean$$|clean-all|clean-volumes|clean-networks|clean-images|prune|shell$$)"; \
		modules["10. 帮助文档"] = "^(help$$|help-simple|help-all)"; \
	} \
	/^[a-zA-Z_-]+:.*?## / { \
		cmd = $$1; \
		desc = $$2; \
		for (module in modules) { \
			if (cmd ~ modules[module]) { \
				if (!(module in items)) { \
					items[module] = ""; \
				} \
				items[module] = items[module] sprintf("  $(CYAN)%-28s$(RESET) %s\n", cmd, desc); \
				break; \
			} \
		} \
	} \
	END { \
		for (i = 1; i <= 15; i++) { \
			module = module_order[i]; \
			if (module in items) { \
				print ""; \
				print "$(MAGENTA)$(BOLD)" module "$(RESET)"; \
				print "$(CYAN)────────────────────────────────────────$(RESET)"; \
				printf "%s", items[module]; \
			} \
		} \
	}' $(MAKEFILE_LIST)
	@echo ""

# ==============================================================================
# 1. 快速开始
# ==============================================================================
.PHONY: check-env check-scripts
check-env: ## 检查环境配置
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "$(RED)$(BOLD)❌ 环境文件不存在: $(ENV_FILE)$(RESET)"; \
		echo "$(YELLOW)⚠️  请运行: make env-init$(RESET)"; \
		exit 1; \
	fi
	$(call success_msg,环境配置正常: $(ENV))

check-scripts: ## 检查必要脚本
	@for script in "$(INFRA_SCRIPT)" "$(INSTALL_SCRIPT)" "$(COMPOSE_MANAGER)"; do \
		if [ ! -f "$$script" ]; then \
			echo "$(RED)$(BOLD)❌ 脚本不存在: $$script$(RESET)"; \
			exit 1; \
		fi; \
	done
	$(call success_msg,脚本检查通过)

# ==============================================================================
# 服务器初始化
# ==============================================================================
.PHONY: server-init-users server-install-docker server-setup-deploy-ssh server-reset-users
server-init-users: ## 初始化服务器用户账户 (yangshujie/deploy/www)
	@echo "$(BLUE)ℹ️  初始化服务器用户账户...$(RESET)"
	@sudo bash $(SERVER_SCRIPTS)/init-users.sh

server-reset-users: ## 重置所有服务器用户 (删除 yangshujie/deploy/www)
	@echo "$(RED)⚠️  重置服务器用户账户...$(RESET)"
	@sudo bash $(SERVER_SCRIPTS)/reset-users.sh

server-install-docker: ## 安装 Docker Engine 和 Docker Compose
	@echo "$(BLUE)ℹ️  安装 Docker...$(RESET)"
	@sudo bash $(SERVER_SCRIPTS)/install-docker.sh

server-setup-deploy-ssh: ## 配置 deploy 的受限 SSH (需要提供 CI_PUBLIC_KEY)
	$(call require_param,CI_PUBLIC_KEY,make server-setup-deploy-ssh CI_PUBLIC_KEY="ssh-ed25519 AAA...")
	@echo "$(BLUE)ℹ️  配置 deploy 受限 SSH...$(RESET)"
	@sudo bash $(SERVER_SCRIPTS)/setup-deploy-ssh.sh "$(CI_PUBLIC_KEY)"

# ==============================================================================
# 基础设施初始化
# ==============================================================================
.PHONY: init init-infra reset clean-infra
init: check-scripts init-infra ## 完整初始化 (网络+卷)
	$(call success_msg,基础设施初始化完成)

init-infra: ## 初始化基础设施网络和卷
	$(call shell_info_msg,初始化基础设施网络和卷...)
	@$(INFRA_SCRIPT) create

reset: ## 重置基础设施 (删除后重新创建)
	$(call shell_warning_msg,重置基础设施...)
	@$(INFRA_SCRIPT) reset

clean-infra: ## 清理基础设施 (谨慎操作)
	$(call shell_error_msg,警告: 这将删除所有基础设施网络和卷!)
	@read -p "确认删除? (输入 'yes' 确认): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(INFRA_SCRIPT) remove; \
	else \
		echo "$(YELLOW)⚠️  操作已取消$(RESET)"; \
	fi

.PHONY: install install-nginx install-mysql install-redis install-mongo install-kafka install-nsq
install: init ## 安装所有基础设施服务
	@echo ""
	@echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"
	@echo "$(CYAN)$(BOLD)  🐳 基础设施组件安装 - 交互式选择$(RESET)"
	@echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"
	@echo ""
	@echo "$(BLUE)当前环境:$(RESET) $(YELLOW)$(ENV)$(RESET)"
	@echo ""
	@echo "$(BLUE)可用组件:$(RESET)"
	@echo "  $(GREEN)1)$(RESET) Nginx       - Web 服务器 (80, 443)"
	@echo "  $(GREEN)2)$(RESET) MySQL       - 关系型数据库 (3306)"
	@echo "  $(GREEN)3)$(RESET) Redis       - 缓存和存储 (6379, 6380 双实例)"
	@echo "  $(GREEN)4)$(RESET) MongoDB     - 文档数据库 (27017)"
	@echo "  $(GREEN)5)$(RESET) Kafka       - 消息队列 (9092)"
	@echo "  $(GREEN)6)$(RESET) NSQ         - 分布式消息平台 (4150-4171)"
	@echo "  $(GREEN)7)$(RESET) All         - 安装所有组件"
	@echo ""
	@if [ "$(ENV)" = "prod" ]; then \
		echo "$(YELLOW)💡 提示: 生产环境推荐组件: Nginx + MySQL + Redis + MongoDB$(RESET)"; \
		echo "$(YELLOW)   (Kafka 和 NSQ 可按需选择)$(RESET)"; \
	fi
	@echo ""
	@read -p "$(CYAN)请选择要安装的组件 (多选用空格分隔，如: 1 3 4): $(RESET)" choices; \
	if [ -z "$$choices" ]; then \
		echo "$(RED)❌ 未选择任何组件，安装已取消$(RESET)"; \
		exit 1; \
	fi; \
	echo ""; \
	selected_components=""; \
	for choice in $$choices; do \
		case $$choice in \
			1) selected_components="$$selected_components nginx";; \
			2) selected_components="$$selected_components mysql";; \
			3) selected_components="$$selected_components redis";; \
			4) selected_components="$$selected_components mongo";; \
			5) selected_components="$$selected_components kafka";; \
			6) selected_components="$$selected_components nsq";; \
			7) selected_components="all"; break;; \
			*) echo "$(RED)⚠️  无效选项: $$choice (已忽略)$(RESET)";; \
		esac; \
	done; \
	if [ -z "$$selected_components" ]; then \
		echo "$(RED)❌ 没有有效的组件选择，安装已取消$(RESET)"; \
		exit 1; \
	fi; \
	echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"; \
	if [ "$$selected_components" = "all" ]; then \
		echo "$(GREEN)✓$(RESET) 将安装: $(YELLOW)所有组件$(RESET)"; \
	else \
		echo "$(GREEN)✓$(RESET) 将安装: $(YELLOW)$$selected_components$(RESET)"; \
	fi; \
	echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"; \
	echo ""; \
	read -p "$(YELLOW)确认继续安装? [Y/n]: $(RESET)" confirm; \
	if [ "$$confirm" = "n" ] || [ "$$confirm" = "N" ]; then \
		echo "$(YELLOW)⚠️  安装已取消$(RESET)"; \
		exit 0; \
	fi; \
	echo ""; \
	echo "$(BLUE)ℹ️  开始安装...$(RESET)"; \
	echo ""; \
	if [ "$$selected_components" = "all" ]; then \
		$(INSTALL_SCRIPT) all; \
	else \
		failed_components=""; \
		for component in $$selected_components; do \
			echo "$(CYAN)───────────────────────────────────────────────────────────$(RESET)"; \
			echo "$(BLUE)📦 正在安装: $$component$(RESET)"; \
			echo "$(CYAN)───────────────────────────────────────────────────────────$(RESET)"; \
			if ! $(INSTALL_SCRIPT) $$component; then \
				echo "$(RED)❌ $$component 安装失败$(RESET)"; \
				failed_components="$$failed_components $$component"; \
			else \
				echo "$(GREEN)✅ $$component 安装成功$(RESET)"; \
			fi; \
			echo ""; \
		done; \
		echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"; \
		echo "$(CYAN)$(BOLD)  📊 安装汇总$(RESET)"; \
		echo "$(CYAN)$(BOLD)═══════════════════════════════════════════════════════════$(RESET)"; \
		if [ -z "$$failed_components" ]; then \
			echo "$(GREEN)✅ 所有组件安装成功！$(RESET)"; \
		else \
			echo "$(YELLOW)⚠️  部分组件安装失败:$$failed_components$(RESET)"; \
			echo "$(BLUE)💡 提示: 可以单独重试失败的组件，例如: make install-redis$(RESET)"; \
		fi; \
		echo ""; \
	fi

install-nginx: init ## 安装 Nginx
	@$(INSTALL_SCRIPT) nginx

install-mysql: init ## 安装 MySQL
	@$(INSTALL_SCRIPT) mysql

install-redis: init ## 安装 Redis (双实例: cache + store)
	@$(INSTALL_SCRIPT) redis

install-mongo: init ## 安装 MongoDB
	@$(INSTALL_SCRIPT) mongo

install-kafka: init ## 安装 Kafka
	@$(INSTALL_SCRIPT) kafka

install-nsq: init ## 安装 NSQ
	@$(INSTALL_SCRIPT) nsq

.PHONY: up down restart
up: ## 启动所有基础设施服务
	$(call shell_info_msg,启动基础设施服务...)
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up all

down: ## 停止所有服务
	$(call shell_info_msg,停止基础设施服务...)
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra down all

restart: down up ## 重启所有服务

.PHONY: status ps health
status: ## 查看基础设施和服务状态
	$(call section_title,基础设施状态)
	@$(INFRA_SCRIPT) status
	@echo ""
	$(call section_title,服务状态)
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) status

ps: ## 查看运行的容器
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

health: ## 健康检查
	$(call shell_info_msg,服务健康检查...)
	@$(INFRA_SCRIPT) test

.PHONY: quick-start full-install dev-setup prod-setup install-all-silent
quick-start: init install-nginx install-mysql install-redis ## 快速启动开发环境
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up nginx
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up storage
	$(call success_msg,🚀 开发环境已就绪!)
	@echo ""
	$(call shell_info_msg,已启动服务:)
	@echo "  $(GREEN)•$(RESET) Nginx       (80, 443)"
	@echo "  $(GREEN)•$(RESET) MySQL       (3306)"
	@echo "  $(GREEN)•$(RESET) Redis Cache (6379) - 缓存实例"
	@echo "  $(GREEN)•$(RESET) Redis Store (6380) - 存储实例"

full-install: init install ## 完整安装所有服务 (使用交互式选择)

install-all-silent: init ## 静默安装所有组件 (非交互，用于自动化)
	@echo "$(BLUE)ℹ️  静默模式: 安装所有组件...$(RESET)"
	@$(INSTALL_SCRIPT) all

dev-setup: ## 配置开发环境
	@$(MAKE) ENV=dev env-init
	@$(MAKE) ENV=dev quick-start

prod-setup: ## 配置生产环境
	@$(MAKE) ENV=prod env-init
	$(call shell_warning_msg,请编辑生产环境配置后再执行: make ENV=prod install)

# ==============================================================================
# 2. 环境管理
# ==============================================================================
.PHONY: dev prod env-init env-copy env-edit env-show
dev: ## 切换到开发环境
	@$(MAKE) ENV=dev status

prod: ## 切换到生产环境
	@$(MAKE) ENV=prod status

env-init: ## 初始化环境配置文件
	@if [ ! -f "$(ENV_FILE)" ]; then \
		mkdir -p env/$(ENV); \
		if [ -f "env/.env.example" ]; then \
			cp env/.env.example "$(ENV_FILE)"; \
		else \
			touch "$(ENV_FILE)"; \
		fi; \
		echo "$(GREEN)✅ 已创建环境配置: $(ENV_FILE)$(RESET)"; \
		echo "$(YELLOW)⚠️  请编辑配置文件后再继续$(RESET)"; \
	else \
		echo "$(YELLOW)⚠️  环境配置已存在: $(ENV_FILE)$(RESET)"; \
	fi

env-copy: ## 复制环境配置 (FROM=源 TO=目标)
	$(call require_param,FROM,make env-copy FROM=dev TO=prod)
	$(call require_param,TO,make env-copy FROM=dev TO=prod)
	@mkdir -p env/$(TO)
	@cp env/$(FROM)/.env env/$(TO)/.env
	$(call success_msg,已复制配置: $(FROM) -> $(TO))

env-edit: ## 编辑当前环境配置
	@$${EDITOR:-vi} $(ENV_FILE)

env-show: check-env ## 显示当前环境配置
	$(call section_title,当前环境配置 ($(ENV)))
	@echo "环境文件: $(CYAN)$(ENV_FILE)$(RESET)"
	@if [ -f "$(ENV_FILE)" ]; then \
		echo ""; \
		grep -E '^[^#].*=' "$(ENV_FILE)" | head -15 || true; \
		echo "$(YELLOW)...$(RESET)"; \
	fi

.PHONY: config-show config-validate
config-show: env-show ## 显示配置 (别名)

config-validate: check-env ## 验证配置文件
	$(call info_msg,验证配置文件...)
	@if docker compose --env-file $(ENV_FILE) config >/dev/null 2>&1; then \
		echo "$(GREEN)✅ Docker Compose 配置有效$(RESET)"; \
	else \
		echo "$(RED)$(BOLD)❌ Docker Compose 配置无效$(RESET)"; \
		exit 1; \
	fi

# ==============================================================================
# 3. 服务管理
# ==============================================================================

# --- MySQL -------------------------------------------------------------------
.PHONY: mysql-start mysql-stop mysql-restart mysql-logs mysql-shell mysql-status mysql-backup
mysql-start: init-infra ## 启动 MySQL
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up storage
	$(call success_msg,MySQL 已启动)

mysql-stop: ## 停止 MySQL
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra down storage
	$(call success_msg,MySQL 已停止)

mysql-restart: mysql-stop mysql-start ## 重启 MySQL

mysql-logs: ## 查看 MySQL 日志
	@docker logs -f --tail=$(LOG_LINES) mysql 2>/dev/null || \
		$(call shell_error_msg,MySQL 容器不存在或未运行)

mysql-shell: ## 进入 MySQL 容器 Shell
	@docker exec -it mysql bash || \
		$(call shell_error_msg,无法连接到 MySQL 容器)

mysql-status: ## 查看 MySQL 状态
	@docker ps --filter "name=mysql" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

mysql-backup: ## 备份 MySQL (DB=数据库名)
	$(call require_param,DB,make mysql-backup DB=myapp)
	@if [ -z "$${MYSQL_ROOT_PASSWORD}" ]; then \
		$(call shell_error_msg,缺少 MYSQL_ROOT_PASSWORD 环境变量); \
		exit 1; \
	fi
	@docker exec mysql mysqldump -u root -p"$${MYSQL_ROOT_PASSWORD}" \
		--databases $(DB) \
		--single-transaction \
		--quick \
		--lock-tables=false \
		> backup-$(DB)-$(shell date +%Y%m%d-%H%M%S).sql
	$(call success_msg,MySQL 备份完成: backup-$(DB)-*.sql)

# --- Redis (双实例) -----------------------------------------------------------
.PHONY: redis-start redis-stop redis-restart redis-logs redis-shell redis-cli redis-status redis-info
.PHONY: redis-cache-logs redis-cache-cli redis-cache-info redis-cache-shell
.PHONY: redis-store-logs redis-store-cli redis-store-info redis-store-shell
.PHONY: redis-clean redis-rebuild redis-acl-regenerate redis-acl-list redis-test

redis-start: init-infra ## 启动 Redis (双实例: cache + store)
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up storage
	$(call success_msg,Redis 双实例已启动 (cache: 6379, store: 6380))

redis-stop: ## 停止 Redis (双实例)
	@docker stop redis-cache redis-store 2>/dev/null || true
	$(call success_msg,Redis 双实例已停止)

redis-restart: redis-stop redis-start ## 重启 Redis (双实例)

redis-logs: ## 查看所有 Redis 日志
	@echo "$(CYAN)=== Redis Cache 日志 ===$(RESET)"
	@docker logs --tail=$(LOG_LINES) redis-cache 2>/dev/null || echo "redis-cache 未运行"
	@echo ""
	@echo "$(CYAN)=== Redis Store 日志 ===$(RESET)"
	@docker logs --tail=$(LOG_LINES) redis-store 2>/dev/null || echo "redis-store 未运行"

redis-status: ## 查看 Redis 状态
	@docker ps --filter "name=redis-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

redis-info: ## 查看 Redis 信息 (双实例)
	@echo "$(CYAN)=== Redis Cache Info (6379) ===$(RESET)"
	@docker exec redis-cache redis-cli -a "$${REDIS_CACHE_PASSWORD}" --no-auth-warning INFO server | grep -E "redis_version|redis_mode|os|uptime_in_seconds" 2>/dev/null || echo "redis-cache 未运行"
	@docker exec redis-cache redis-cli -a "$${REDIS_CACHE_PASSWORD}" --no-auth-warning INFO memory | grep -E "used_memory_human|maxmemory_human" 2>/dev/null || true
	@docker exec redis-cache redis-cli -a "$${REDIS_CACHE_PASSWORD}" --no-auth-warning INFO stats | grep -E "evicted_keys|keyspace_hits|keyspace_misses" 2>/dev/null || true
	@echo ""
	@echo "$(CYAN)=== Redis Store Info (6380) ===$(RESET)"
	@docker exec redis-store redis-cli -p 6380 -a "$${REDIS_STORE_PASSWORD}" --no-auth-warning INFO server | grep -E "redis_version|redis_mode|os|uptime_in_seconds" 2>/dev/null || echo "redis-store 未运行"
	@docker exec redis-store redis-cli -p 6380 -a "$${REDIS_STORE_PASSWORD}" --no-auth-warning INFO memory | grep -E "used_memory_human|maxmemory_human" 2>/dev/null || true
	@docker exec redis-store redis-cli -p 6380 -a "$${REDIS_STORE_PASSWORD}" --no-auth-warning INFO persistence | grep -E "aof_enabled|aof_current_size" 2>/dev/null || true

# Cache 实例操作
redis-cache-logs: ## 查看 Redis Cache 日志
	@docker logs -f --tail=$(LOG_LINES) redis-cache 2>/dev/null || \
		$(call shell_error_msg,Redis Cache 容器不存在或未运行)

redis-cache-cli: ## 进入 Redis Cache CLI
	@docker exec -it redis-cache redis-cli -a "$${REDIS_CACHE_PASSWORD}" || \
		$(call shell_error_msg,无法连接到 Redis Cache)

redis-cache-info: ## 查看 Redis Cache 详细信息
	@docker exec redis-cache redis-cli -a "$${REDIS_CACHE_PASSWORD}" --no-auth-warning INFO

redis-cache-shell: ## 进入 Redis Cache 容器 Shell
	@docker exec -it redis-cache sh || \
		$(call shell_error_msg,无法连接到 Redis Cache 容器)

# Store 实例操作
redis-store-logs: ## 查看 Redis Store 日志
	@docker logs -f --tail=$(LOG_LINES) redis-store 2>/dev/null || \
		$(call shell_error_msg,Redis Store 容器不存在或未运行)

redis-store-cli: ## 进入 Redis Store CLI
	@docker exec -it redis-store redis-cli -p 6380 -a "$${REDIS_STORE_PASSWORD}" || \
		$(call shell_error_msg,无法连接到 Redis Store)

redis-store-info: ## 查看 Redis Store 详细信息
	@docker exec redis-store redis-cli -p 6380 -a "$${REDIS_STORE_PASSWORD}" --no-auth-warning INFO

redis-store-shell: ## 进入 Redis Store 容器 Shell
	@docker exec -it redis-store sh || \
		$(call shell_error_msg,无法连接到 Redis Store 容器)

# 兼容旧命令（默认操作 cache 实例）
redis-shell: redis-cache-shell ## 进入 Redis 容器 Shell (默认: cache)
redis-cli: redis-cache-cli ## 进入 Redis CLI (默认: cache)

# Redis 清理和重建
redis-clean: ## 清理 Redis 所有数据（容器、数据卷、宿主机数据）
	@echo "$(RED)警告: 即将删除所有 Redis 数据！$(RESET)"
	@echo "$(YELLOW)包括: 容器、数据卷、宿主机数据目录、ACL 配置文件$(RESET)"
	@read -p "确认要继续吗？(yes/no): " confirm && [ "$$confirm" = "yes" ] || (echo "$(GREEN)操作已取消$(RESET)" && exit 1)
	@echo "$(BLUE)正在清理 Redis...$(RESET)"
	@cd $(COMPONENTS_DIR)/redis && bash rebuild.sh "../../compose/env/$(ENV)/.env" --clean-only || \
		$(call shell_error_msg,Redis 清理失败)
	$(call success_msg,Redis 数据已清理)

redis-rebuild: ## 完全重建 Redis（清理数据 + 重新部署）
	@echo "$(RED)警告: 即将删除所有 Redis 数据并重新部署！$(RESET)"
	@read -p "确认要继续吗？(yes/no): " confirm && [ "$$confirm" = "yes" ] || (echo "$(GREEN)操作已取消$(RESET)" && exit 1)
	@echo "$(BLUE)正在重建 Redis...$(RESET)"
	@cd $(COMPONENTS_DIR)/redis && bash rebuild.sh "../../compose/env/$(ENV)/.env" || \
		$(call shell_error_msg,Redis 重建失败)
	$(call success_msg,Redis 已重建完成)

redis-acl-regenerate: ## 重新生成 Redis ACL 配置文件
	@echo "$(BLUE)正在重新生成 Redis ACL 配置...$(RESET)"
	@cd $(COMPONENTS_DIR)/redis && bash generate-acl.sh "../../compose/env/$(ENV)/.env" || \
		$(call shell_error_msg,ACL 配置生成失败)
	@echo "$(YELLOW)提示: 需要重启 Redis 容器使配置生效: make redis-restart$(RESET)"
	$(call success_msg,Redis ACL 配置已重新生成)

redis-acl-list: ## 查看 Redis ACL 用户列表
	@echo "$(CYAN)=== Redis Cache ACL 用户列表 ===$(RESET)"
	@docker exec redis-cache redis-cli --user admin --pass "$${REDIS_ADMIN_PASSWORD}" ACL LIST 2>/dev/null || \
		echo "$(RED)无法连接到 Redis Cache（请检查容器是否运行和密码是否正确）$(RESET)"
	@echo ""
	@echo "$(CYAN)=== Redis Store ACL 用户列表 ===$(RESET)"
	@docker exec redis-store redis-cli -p 6380 --user admin --pass "$${REDIS_ADMIN_PASSWORD}" ACL LIST 2>/dev/null || \
		echo "$(RED)无法连接到 Redis Store（请检查容器是否运行和密码是否正确）$(RESET)"

redis-test: ## 测试 Redis 功能和所有 ACL 用户
	@echo "$(BLUE)正在测试 Redis 功能...$(RESET)"
	@cd $(COMPONENTS_DIR)/redis && bash test-redis.sh "../../compose/env/$(ENV)/.env" || \
		$(call shell_error_msg,Redis 测试失败)

# --- MongoDB -----------------------------------------------------------------
.PHONY: mongo-start mongo-stop mongo-restart mongo-logs mongo-shell mongo-status
.PHONY: mongo-backup mongo-monitor mongo-tune mongo-init-users mongo-stats
mongo-start: init-infra ## 启动 MongoDB
	@cd $(COMPONENTS_DIR)/mongo && docker compose up -d
	$(call success_msg,MongoDB 已启动)

mongo-stop: ## 停止 MongoDB
	@cd $(COMPONENTS_DIR)/mongo && docker compose down
	$(call success_msg,MongoDB 已停止)

mongo-restart: mongo-stop mongo-start ## 重启 MongoDB

mongo-logs: ## 查看 MongoDB 日志
	@docker logs -f --tail=$(LOG_LINES) mongo 2>/dev/null || \
		$(call shell_error_msg,MongoDB 容器不存在或未运行)

mongo-shell: ## 进入 MongoDB Shell (需要认证)
	@if [ -z "$(MONGO_INITDB_ROOT_USERNAME)" ] || [ -z "$(MONGO_INITDB_ROOT_PASSWORD)" ]; then \
		$(call shell_error_msg,缺少 MONGO_INITDB_ROOT_USERNAME 或 MONGO_INITDB_ROOT_PASSWORD 环境变量); \
		$(call shell_info_msg,请先运行: make env-init ENV=$(ENV)); \
		exit 1; \
	fi
	@docker exec -it mongo mongosh \
		-u "$(MONGO_INITDB_ROOT_USERNAME)" \
		-p "$(MONGO_INITDB_ROOT_PASSWORD)" \
		--authenticationDatabase admin || \
		$(call shell_error_msg,无法连接到 MongoDB)

mongo-status: ## 查看 MongoDB 状态
	@docker ps --filter "name=mongo" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

mongo-backup: ## 备份 MongoDB 数据
	@bash $(COMPONENTS_SCRIPTS)/backup-mongo.sh

mongo-monitor: ## 实时监控 MongoDB 性能指标
	@bash $(COMPONENTS_SCRIPTS)/monitor-mongo.sh

mongo-tune: ## 系统调优（宿主机内核参数）
	@$(call warning_msg,此命令需要 root 权限，将在宿主机执行系统调优)
	@bash $(SERVER_SCRIPTS)/tune-host.sh

mongo-init-users: ## 创建 MongoDB 业务用户
	@bash $(COMPONENTS_SCRIPTS)/init-mongo-users.sh

mongo-stats: ## 查看 MongoDB 统计信息
	@if [ -z "$(MONGO_INITDB_ROOT_USERNAME)" ] || [ -z "$(MONGO_INITDB_ROOT_PASSWORD)" ]; then \
		$(call shell_error_msg,缺少认证信息); \
		exit 1; \
	fi
	@docker exec mongo mongosh \
		-u "$(MONGO_INITDB_ROOT_USERNAME)" \
		-p "$(MONGO_INITDB_ROOT_PASSWORD)" \
		--authenticationDatabase admin \
		--quiet \
		--eval "db.serverStatus()" | head -n 50

# --- Kafka -------------------------------------------------------------------
.PHONY: kafka-start kafka-stop kafka-restart kafka-logs kafka-shell kafka-status
.PHONY: kafka-topics kafka-create-topic kafka-delete-topic kafka-describe-topic
kafka-start: init-infra ## 启动 Kafka
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up message
	$(call success_msg,Kafka 已启动)

kafka-stop: ## 停止 Kafka
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra down message
	$(call success_msg,Kafka 已停止)

kafka-restart: kafka-stop kafka-start ## 重启 Kafka

kafka-logs: ## 查看 Kafka 日志
	@docker logs -f --tail=$(LOG_LINES) kafka 2>/dev/null || \
		$(call shell_error_msg,Kafka 容器不存在或未运行)

kafka-shell: ## 进入 Kafka 容器 Shell
	@docker exec -it kafka bash || \
		$(call shell_error_msg,无法连接到 Kafka 容器)

kafka-status: ## 查看 Kafka 状态
	@docker ps --filter "name=kafka" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

kafka-topics: ## 列出所有 Kafka Topics
	@docker exec kafka kafka-topics.sh --list --bootstrap-server $(KAFKA_BOOTSTRAP_SERVER) || \
		$(call shell_error_msg,无法连接到 Kafka)

kafka-create-topic: ## 创建 Kafka Topic (TOPIC=名称 PARTITIONS=3 REPLICAS=1)
	$(call require_param,TOPIC,make kafka-create-topic TOPIC=my-topic)
	@docker exec kafka kafka-topics.sh --create \
		--topic $(TOPIC) \
		--partitions $(or $(PARTITIONS),$(KAFKA_DEFAULT_PARTITIONS)) \
		--replication-factor $(or $(REPLICAS),$(KAFKA_DEFAULT_REPLICAS)) \
		--bootstrap-server $(KAFKA_BOOTSTRAP_SERVER)
	$(call success_msg,Topic 创建成功: $(TOPIC))

kafka-delete-topic: ## 删除 Kafka Topic (TOPIC=名称)
	$(call require_param,TOPIC,make kafka-delete-topic TOPIC=my-topic)
	@docker exec kafka kafka-topics.sh --delete --topic $(TOPIC) \
		--bootstrap-server $(KAFKA_BOOTSTRAP_SERVER)
	$(call success_msg,Topic 删除成功: $(TOPIC))

kafka-describe-topic: ## 查看 Kafka Topic 详情 (TOPIC=名称)
	$(call require_param,TOPIC,make kafka-describe-topic TOPIC=my-topic)
	@docker exec kafka kafka-topics.sh --describe --topic $(TOPIC) \
		--bootstrap-server $(KAFKA_BOOTSTRAP_SERVER)

# --- NSQ ---------------------------------------------------------------------
.PHONY: nsq-start nsq-stop nsq-restart nsq-logs nsq-admin nsq-status
.PHONY: nsq-shell nsq-lookupd-logs nsq-admin-logs nsq-topics nsq-stats
nsq-start: init-infra ## 启动 NSQ
	@if [ -d "$(COMPONENTS_DIR)/nsq" ]; then \
		cd $(COMPONENTS_DIR)/nsq && docker compose --env-file ../../compose/env/$(ENV)/env up -d; \
		$(call success_msg,NSQ 已启动); \
	else \
		$(call shell_error_msg,NSQ 组件目录不存在); \
	fi

nsq-stop: ## 停止 NSQ
	@docker stop nsqd nsqlookupd nsqadmin 2>/dev/null || true
	$(call success_msg,NSQ 已停止)

nsq-restart: nsq-stop nsq-start ## 重启 NSQ

nsq-logs: ## 查看 NSQ 日志
	@docker logs -f --tail=$(LOG_LINES) nsqd 2>/dev/null || \
		$(call shell_error_msg,NSQ 容器不存在或未运行)

nsq-admin: ## 访问 NSQ Admin Web UI (需要 SSH 隧道)
	@echo "$(YELLOW)⚠️  NSQAdmin 绑定到 127.0.0.1:4171（仅本机访问）$(RESET)"
	@echo "$(BLUE)ℹ️  访问方法:$(RESET)"
	@echo "  1. 建立 SSH 隧道: $(CYAN)ssh -L 4171:127.0.0.1:4171 user@serverB$(RESET)"
	@echo "  2. 在本地浏览器打开: $(CYAN)http://localhost:4171$(RESET)"
	@echo ""
	@if docker ps --filter "name=nsqadmin" --format "{{.Status}}" | grep -q "Up"; then \
		echo "$(GREEN)✅ NSQAdmin 正在运行$(RESET)"; \
	else \
		echo "$(RED)❌ NSQAdmin 未运行，请先执行: make nsq-start$(RESET)"; \
	fi

nsq-status: ## 查看 NSQ 状态
	@docker ps --filter "name=nsq" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

nsq-shell: ## 进入 NSQd 容器 Shell
	@docker exec -it nsqd sh || \
		$(call shell_error_msg,无法连接到 NSQd 容器)

nsq-lookupd-logs: ## 查看 NSQLookupd 日志
	@docker logs -f --tail=$(LOG_LINES) nsqlookupd 2>/dev/null || \
		$(call shell_error_msg,NSQLookupd 容器不存在或未运行)

nsq-admin-logs: ## 查看 NSQAdmin 日志
	@docker logs -f --tail=$(LOG_LINES) nsqadmin 2>/dev/null || \
		$(call shell_error_msg,NSQAdmin 容器不存在或未运行)

nsq-topics: ## 查看 NSQ Topics 和统计
	@echo "$(CYAN)=== NSQ Topics ===$(RESET)"
	@curl -s http://localhost:4151/stats?format=json 2>/dev/null | grep -o '"topic_name":"[^"]*"' | cut -d'"' -f4 || \
		echo "$(YELLOW)无法获取 Topics（nsqd 未运行）$(RESET)"
	@echo ""
	@echo "$(CYAN)=== NSQ Stats (前 20 行) ===$(RESET)"
	@curl -s http://localhost:4151/stats 2>/dev/null | head -20 || \
		echo "$(YELLOW)无法获取统计信息$(RESET)"

nsq-stats: ## 查看 NSQ 详细统计信息
	@curl -s http://localhost:4151/stats?format=json 2>/dev/null || \
		curl -s http://localhost:4151/stats 2>/dev/null || \
		echo "$(RED)无法连接到 NSQd$(RESET)"

# ==============================================================================
# 4. 网络管理
# ==============================================================================
.PHONY: network-list network-create network-delete network-inspect
.PHONY: net-list net-create net-delete net-inspect
.PHONY: network-init network-status network-reset
.PHONY: swarm-init swarm-leave swarm-status port-check

network-init: ## 初始化基础设施网络 (infra-network)
	$(call info_msg,初始化基础设施网络...)
	@$(INFRA_SCRIPT) create
	$(call success_msg,基础设施网络创建成功)

network-status: ## 查看基础设施网络状态
	$(call info_msg,基础设施网络状态:)
	@if docker network ls --format '{{.Name}}' | grep -q '^infra-network$$'; then \
		echo "  $(GREEN)✅$(RESET) infra-network (overlay 分布式网络)"; \
		docker network inspect infra-network --format '    子网: {{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null; \
	else \
		echo "  $(RED)❌$(RESET) infra-network (未创建)"; \
	fi

network-reset: ## 重置基础设施网络 (删除并重建)
	$(call warning_msg,重置基础设施网络...)
	@$(INFRA_SCRIPT) reset
	$(call success_msg,网络重置完成)

network-list: ## 列出所有 Docker 网络
	@docker network ls --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"

net-list: network-list ## 列出网络 (别名)

network-create: ## 创建自定义网络 (NAME=名称 DRIVER=bridge/overlay)
	$(call require_param,NAME,make network-create NAME=my-network DRIVER=bridge)
	@docker network create --driver=$(or $(DRIVER),bridge) $(NAME)
	$(call success_msg,网络创建成功: $(NAME))

net-create: network-create ## 创建网络 (别名)

network-delete: ## 删除网络 (NAME=名称)
	$(call require_param,NAME,make network-delete NAME=my-network)
	@docker network rm $(NAME)
	$(call success_msg,网络删除成功: $(NAME))

net-delete: network-delete ## 删除网络 (别名)

network-inspect: ## 检查网络详情 (NAME=名称)
	$(call require_param,NAME,make network-inspect NAME=infra-net)
	@docker network inspect $(NAME)

net-inspect: network-inspect ## 检查网络 (别名)

swarm-init: ## 初始化 Docker Swarm
	@docker swarm init

# ==============================================================================
# VPN 网络管理 (Mihomo)
# ==============================================================================
.PHONY: vpn-setup vpn-status vpn-test vpn-enable vpn-disable
.PHONY: vpn-proxies vpn-switch vpn-docker-test vpn-uninstall vpn-diagnose

vpn-setup: ## 安装和配置 VPN (Mihomo)
	@echo "$(BLUE)ℹ️  安装 Mihomo VPN...$(RESET)"
	@sudo bash $(NETWORK_SCRIPTS)/setup.sh

vpn-status: ## 查看 VPN 状态
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh status

vpn-test: ## 测试 VPN 连接
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh test

vpn-enable: ## 启用 VPN 模式
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh enable

vpn-disable: ## 禁用 VPN 模式 (直连)
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh disable

vpn-proxies: ## 显示所有代理组状态
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh proxies

vpn-switch: ## 切换代理选择 (交互式)
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh switch

vpn-docker-test: ## 测试 Docker 容器 VPN 连接
	@bash $(NETWORK_SCRIPTS)/vpn-manager.sh docker-test

vpn-uninstall: ## 完全卸载 VPN
	@echo "$(YELLOW)⚠️  这将完全卸载 Mihomo VPN$(RESET)"
	@sudo bash $(NETWORK_SCRIPTS)/uninstall.sh

vpn-diagnose: ## 网络环境诊断
	@sudo bash $(NETWORK_SCRIPTS)/diagnose.sh
	$(call success_msg,Swarm 集群已初始化)

swarm-leave: ## 离开 Docker Swarm
	@docker swarm leave --force
	$(call success_msg,已离开 Swarm 集群)

swarm-status: ## 查看 Swarm 状态
	@docker node ls 2>/dev/null || echo "$(YELLOW)未加入 Swarm 集群$(RESET)"

port-check: ## 检查端口占用 (PORT=端口号)
	$(call require_param,PORT,make port-check PORT=80)
	@echo "$(BLUE)检查端口 $(PORT) 占用情况:$(RESET)"
	@lsof -i :$(PORT) || echo "$(GREEN)端口 $(PORT) 未被占用$(RESET)"

# ==============================================================================
# 5. SSL 证书管理
# ==============================================================================
.PHONY: ssl-wildcard ssl-obtain ssl-import ssl-renew ssl-list ssl-remove ssl-setup-aliyun

ssl-wildcard: ## 申请通配符证书 (DOMAIN=域名 EMAIL=邮箱) - 使用阿里云 DNS API
	$(call require_param,DOMAIN,make ssl-wildcard DOMAIN=yangshujie.com EMAIL=admin@example.com)
	$(call require_param,EMAIL,make ssl-wildcard DOMAIN=yangshujie.com EMAIL=admin@example.com)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh wildcard $(DOMAIN) $(EMAIL)
	$(call success_msg,通配符证书申请成功: $(DOMAIN) + *.$(DOMAIN))

ssl-obtain: ## 申请单域名证书 (DOMAIN=域名 EMAIL=邮箱) - HTTP 验证
	$(call require_param,DOMAIN,make ssl-obtain DOMAIN=example.com EMAIL=admin@example.com)
	$(call require_param,EMAIL,make ssl-obtain DOMAIN=example.com EMAIL=admin@example.com)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh obtain $(DOMAIN) $(EMAIL)
	$(call success_msg,证书申请成功: $(DOMAIN))

ssl-import: ## 导入自有证书 (DOMAIN=域名 CERT=证书路径 KEY=私钥路径)
	$(call require_param,DOMAIN,make ssl-import DOMAIN=example.com CERT=/path/cert.pem KEY=/path/key.pem)
	$(call require_param,CERT,make ssl-import DOMAIN=example.com CERT=/path/cert.pem KEY=/path/key.pem)
	$(call require_param,KEY,make ssl-import DOMAIN=example.com CERT=/path/cert.pem KEY=/path/key.pem)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh import $(DOMAIN) $(CERT) $(KEY)
	$(call success_msg,证书导入成功: $(DOMAIN))

ssl-renew: ## 续期所有 SSL 证书
	@$(TOOLS_SCRIPTS)/ssl-manager.sh renew
	$(call success_msg,证书续期完成)

ssl-list: ## 列出所有 SSL 证书
	@$(TOOLS_SCRIPTS)/ssl-manager.sh list

ssl-remove: ## 删除 SSL 证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-remove DOMAIN=example.com)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh remove $(DOMAIN)
	$(call success_msg,证书删除成功: $(DOMAIN))

ssl-setup-aliyun: ## 设置阿里云 DNS API 凭证（交互式）
	@$(TOOLS_SCRIPTS)/ssl-manager.sh setup-aliyun
	$(call success_msg,阿里云凭证配置完成)

# ==============================================================================
# 6. Nginx 应用管理
# ==============================================================================
.PHONY: nginx-start nginx-stop nginx-restart nginx-logs nginx-reload nginx-test nginx-status
.PHONY: app-deploy app-remove app-list app-enable app-disable

nginx-start: init-infra ## 启动 Nginx
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra up nginx
	$(call success_msg,Nginx 已启动)

nginx-stop: ## 停止 Nginx
	@$(COMPOSE_MANAGER_ENV) $(COMPOSE_MANAGER) infra down nginx
	$(call success_msg,Nginx 已停止)

nginx-restart: nginx-stop nginx-start ## 重启 Nginx

nginx-logs: ## 查看 Nginx 日志
	@docker logs -f --tail=$(LOG_LINES) nginx 2>/dev/null || \
		$(call shell_error_msg,Nginx 容器不存在或未运行)

nginx-reload: ## 重载 Nginx 配置
	@docker exec nginx nginx -s reload
	$(call success_msg,Nginx 配置已重载)

nginx-test: ## 测试 Nginx 配置
	@docker exec nginx nginx -t

nginx-status: ## 查看 Nginx 状态
	@docker ps --filter "name=nginx" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

app-deploy: ## 部署应用配置 (APP=应用名 DOMAIN=域名 PORT=后端端口 SSL=yes/no)
	$(call require_param,APP,make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000)
	$(call require_param,DOMAIN,make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000)
	$(call require_param,PORT,make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000)
	@$(TOOLS_SCRIPTS)/nginx-app-manager.sh deploy $(APP) $(DOMAIN) $(PORT) $(or $(SSL),no)
	$(call success_msg,应用配置部署成功: $(APP))

app-remove: ## 删除应用配置 (APP=应用名)
	$(call require_param,APP,make app-remove APP=myapp)
	@$(TOOLS_SCRIPTS)/nginx-app-manager.sh remove $(APP)
	$(call success_msg,应用配置已删除: $(APP))

app-list: ## 列出所有应用配置
	@$(TOOLS_SCRIPTS)/nginx-app-manager.sh list

app-enable: ## 启用应用配置 (APP=应用名)
	$(call require_param,APP,make app-enable APP=myapp)
	@$(TOOLS_SCRIPTS)/nginx-app-manager.sh enable $(APP)
	@$(MAKE) nginx-reload

app-disable: ## 禁用应用配置 (APP=应用名)
	$(call require_param,APP,make app-disable APP=myapp)
	@$(TOOLS_SCRIPTS)/nginx-app-manager.sh disable $(APP)
	@$(MAKE) nginx-reload

# ==============================================================================
# 7. 监控与诊断
# ==============================================================================
.PHONY: stats top disk-usage logs troubleshoot service-ports diagnose

stats: ## 查看容器资源使用统计
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

top: ## 查看容器进程
	@docker ps -q | xargs -I {} docker top {}

disk-usage: ## 查看 Docker 磁盘使用
	@docker system df -v

logs: ## 查看所有服务日志 (SERVICE=服务名,可选)
	@if [ -n "$(SERVICE)" ]; then \
		docker logs -f --tail=$(LOG_LINES) $(SERVICE); \
	else \
		echo "$(BLUE)ℹ️  显示最近所有服务日志...$(RESET)"; \
		docker ps --format '{{.Names}}' | xargs -I {} sh -c 'echo "=== {} ===" && docker logs --tail=20 {}'; \
	fi

troubleshoot: ## 运行故障诊断
	$(call section_title,系统诊断)
	@echo "$(BLUE)1. 检查 Docker 状态$(RESET)"
	@docker version || $(call shell_error_msg,Docker 未运行)
	@echo ""
	@echo "$(BLUE)2. 检查容器健康状态$(RESET)"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "unhealthy|Restarting" || echo "$(GREEN)所有容器健康$(RESET)"
	@echo ""
	@echo "$(BLUE)3. 检查网络连接$(RESET)"
	@$(NETWORK_SCRIPTS)/diagnose.sh test || $(call shell_warning_msg,网络存在问题)
	@echo ""
	@echo "$(BLUE)4. 检查磁盘空间$(RESET)"
	@df -h | grep -E "Filesystem|/$$" || true
	@echo ""
	@echo "$(BLUE)5. 检查错误日志$(RESET)"
	@docker ps --format '{{.Names}}' | xargs -I {} sh -c 'docker logs --tail=50 {} 2>&1 | grep -i error | head -3' || true

service-ports: ## 显示所有服务端口映射
	$(call section_title,服务端口映射)
	@echo "$(CYAN)Nginx:$(RESET)     80, 443"
	@echo "$(CYAN)MySQL:$(RESET)     3306"
	@echo "$(CYAN)Redis:$(RESET)     6379"
	@echo "$(CYAN)MongoDB:$(RESET)   27017"
	@echo "$(CYAN)Kafka:$(RESET)     9092"
	@echo "$(CYAN)NSQ:$(RESET)       4150, 4151, 4160, 4161, 4171"
	@echo "$(CYAN)Jenkins:$(RESET)   8080, 50000"

diagnose: troubleshoot ## 诊断 (别名)

# ==============================================================================
# 8. 测试与验证
# ==============================================================================
.PHONY: test-all test-mysql test-redis test-mongo test-kafka test-nsq test-nginx test-jenkins

test-all: ## 测试所有服务连接
	$(call section_title,测试所有服务)
	@echo ""
	@$(MAKE) test-nginx || true
	@$(MAKE) test-mysql || true
	@$(MAKE) test-redis || true
	@$(MAKE) test-mongo || true
	@$(MAKE) test-kafka || true
	@$(MAKE) test-nsq || true
	@$(MAKE) test-jenkins || true
	@echo ""
	$(call success_msg,测试完成)

test-mysql: ## 测试 MySQL 连接
	@printf "$(BLUE)MySQL:$(RESET)     "
	@docker exec mysql mysqladmin ping -h localhost 2>/dev/null && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

test-redis: ## 测试 Redis 连接（双实例）
	@printf "$(BLUE)Redis Cache (6379):$(RESET) "
	@docker exec redis-cache redis-cli -a "$${REDIS_CACHE_PASSWORD}" --no-auth-warning ping 2>/dev/null | grep -q PONG && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"
	@printf "$(BLUE)Redis Store (6380):$(RESET) "
	@docker exec redis-store redis-cli -p 6380 -a "$${REDIS_STORE_PASSWORD}" --no-auth-warning ping 2>/dev/null | grep -q PONG && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

test-mongo: ## 测试 MongoDB 连接
	@printf "$(BLUE)MongoDB:$(RESET)   "
	@if [ -z "$(MONGO_INITDB_ROOT_USERNAME)" ] || [ -z "$(MONGO_INITDB_ROOT_PASSWORD)" ]; then \
		echo "$(YELLOW)⚠️  跳过（缺少认证信息）$(RESET)"; \
	else \
		docker exec mongo mongosh \
			-u "$(MONGO_INITDB_ROOT_USERNAME)" \
			-p "$(MONGO_INITDB_ROOT_PASSWORD)" \
			--authenticationDatabase admin \
			--quiet \
			--eval "db.adminCommand('ping')" 2>/dev/null | grep -q '"ok" : 1' && \
			echo "$(GREEN)✅ 正常$(RESET)" || \
			echo "$(RED)❌ 失败$(RESET)"; \
	fi

test-kafka: ## 测试 Kafka 连接
	@printf "$(BLUE)Kafka:$(RESET)     "
	@docker exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092 2>/dev/null | grep -q ApiVersion && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

test-nsq: ## 测试 NSQ 连接
	@printf "$(BLUE)NSQ:$(RESET)       "
	@curl -s http://localhost:4171/ping 2>/dev/null | grep -q OK && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

test-nginx: ## 测试 Nginx 连接
	@printf "$(BLUE)Nginx:$(RESET)     "
	@curl -s -o /dev/null -w "%{http_code}" http://localhost 2>/dev/null | grep -q 200 && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

test-jenkins: ## 测试 Jenkins 连接
	@printf "$(BLUE)Jenkins:$(RESET)   "
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null | grep -qE "200|403" && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

# ==============================================================================
# 9. 维护与清理
# ==============================================================================
.PHONY: backup clean clean-all clean-volumes clean-networks clean-images prune shell

backup: ## 备份所有数据卷 (TARGET=/path/to/backup)
	$(call require_param,TARGET,make backup TARGET=/backup/dir)
	$(call info_msg,备份数据卷到: $(TARGET))
	@mkdir -p $(TARGET)
	@for volume in $$(docker volume ls -q | grep infra); do \
		echo "$(CYAN)备份卷: $$volume$(RESET)"; \
		docker run --rm -v $$volume:/source -v $(TARGET):/backup alpine tar czf /backup/$$volume-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /source .; \
	done
	$(call success_msg,备份完成)

clean: ## 清理停止的容器和悬空镜像
	$(call shell_warning_msg,清理停止的容器和悬空镜像...)
	@docker container prune -f
	@docker image prune -f
	$(call success_msg,清理完成)

clean-all: ## 清理所有未使用的 Docker 资源 (谨慎!)
	$(call shell_error_msg,警告: 这将清理所有未使用的容器、网络、镜像!)
	@read -p "确认清理? (输入 'yes' 确认): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker system prune -a -f; \
		echo "$(GREEN)✅ 清理完成$(RESET)"; \
	else \
		echo "$(YELLOW)⚠️  操作已取消$(RESET)"; \
	fi

clean-volumes: ## 清理未使用的数据卷 (危险!)
	$(call shell_error_msg,警告: 这将删除所有未使用的数据卷!)
	@read -p "确认删除? (输入 'yes' 确认): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker volume prune -f; \
		echo "$(GREEN)✅ 数据卷清理完成$(RESET)"; \
	else \
		echo "$(YELLOW)⚠️  操作已取消$(RESET)"; \
	fi

clean-networks: ## 清理未使用的网络
	@docker network prune -f
	$(call success_msg,网络清理完成)

clean-images: ## 清理悬空镜像
	@docker image prune -f
	$(call success_msg,镜像清理完成)

prune: clean ## 清理 (别名)

shell: ## 进入指定容器 Shell (NAME=容器名)
	$(call require_param,NAME,make shell NAME=nginx)
	@docker exec -it $(NAME) sh || docker exec -it $(NAME) bash || \
		$(call error_msg,无法连接到容器: $(NAME))

# ==============================================================================
# 10. 快速参考
# ==============================================================================
.PHONY: help-mongo help-redis help-mysql

help-mongo: ## MongoDB 快速参考
	$(call section_title,MongoDB 管理命令)
	@echo ""
	@echo "$(BLUE)$(BOLD)🍃 基础操作:$(RESET)"
	@echo "  $(CYAN)make mongo-start$(RESET)          启动 MongoDB"
	@echo "  $(CYAN)make mongo-stop$(RESET)           停止 MongoDB"
	@echo "  $(CYAN)make mongo-restart$(RESET)        重启 MongoDB"
	@echo "  $(CYAN)make mongo-status$(RESET)         查看状态"
	@echo "  $(CYAN)make mongo-logs$(RESET)           查看日志"
	@echo ""
	@echo "$(BLUE)$(BOLD)🔐 连接与管理:$(RESET)"
	@echo "  $(CYAN)make mongo-shell$(RESET)          连接 MongoDB Shell (需要认证)"
	@echo "  $(CYAN)make mongo-init-users$(RESET)     创建业务用户 (交互式)"
	@echo "  $(CYAN)make mongo-stats$(RESET)          查看服务器统计信息"
	@echo ""
	@echo "$(BLUE)$(BOLD)📊 监控与优化:$(RESET)"
	@echo "  $(CYAN)make mongo-monitor$(RESET)        实时监控性能指标"
	@echo "  $(CYAN)make mongo-backup$(RESET)         备份数据库"
	@echo "  $(CYAN)make mongo-tune$(RESET)           系统调优 (需要 root 权限)"
	@echo ""
	@echo "$(BLUE)$(BOLD)🧪 测试:$(RESET)"
	@echo "  $(CYAN)make test-mongo$(RESET)           测试 MongoDB 连接"
	@echo ""
	@echo "$(YELLOW)$(BOLD)💡 配置说明:$(RESET)"
	@echo "  • 容器名称: $(GREEN)mongo$(RESET)"
	@echo "  • 端口映射: $(GREEN)127.0.0.1:27017:27017$(RESET) (仅本地)"
	@echo "  • 资源配额: $(GREEN)1536M 内存 / 0.30 CPU$(RESET)"
	@echo "  • WiredTiger 缓存: $(GREEN)900MB$(RESET) (60% 容器内存)"
	@echo "  • 认证模式: $(GREEN)已启用 (--auth)$(RESET)"
	@echo "  • 数据卷: $(GREEN)infra_mongo_data$(RESET)"
	@echo "  • 日志卷: $(GREEN)infra_mongo_logs$(RESET)"
	@echo ""
	@echo "$(YELLOW)$(BOLD)📝 环境变量:$(RESET)"
	@echo "  MONGO_INITDB_ROOT_USERNAME  - Root 用户名"
	@echo "  MONGO_INITDB_ROOT_PASSWORD  - Root 密码"
	@echo "  MONGO_DATABASE              - 初始数据库名"
	@echo "  MONGO_PORT                  - 端口 (默认 27017)"
	@echo "  MONGO_MEMORY_LIMIT          - 内存限制"
	@echo "  MONGO_CPUS                  - CPU 配额"
	@echo ""
	@echo "$(YELLOW)$(BOLD)🚀 首次部署流程:$(RESET)"
	@echo "  1. $(CYAN)make mongo-tune$(RESET)         # 宿主机系统调优 (只需一次)"
	@echo "  2. $(CYAN)make mongo-start$(RESET)        # 启动 MongoDB"
	@echo "  3. $(CYAN)make mongo-shell$(RESET)        # 验证 root 账户"
	@echo "  4. $(CYAN)make mongo-init-users$(RESET)   # 创建业务用户"
	@echo "  5. $(CYAN)make mongo-monitor$(RESET)      # 检查性能指标"
	@echo ""
	@echo "$(YELLOW)$(BOLD)📚 相关文档:$(RESET)"
	@echo "  • $(CYAN)components/mongo/README.md$(RESET)        - 完整运维指南"
	@echo "  • $(CYAN)docs/为什么需要宿主机调优.md$(RESET)      - 系统调优说明"
	@echo "  • $(CYAN)scripts/components/backup-mongo.sh$(RESET) - 备份脚本"
	@echo "  • $(CYAN)scripts/components/monitor-mongo.sh$(RESET) - 监控脚本"
	@echo ""

# ==============================================================================
# 结束
# ==============================================================================

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
	@echo "  compose/env/            - 环境变量配置"
	@echo "  scripts/                - 管理脚本"
	@echo ""
	@echo "$(BLUE)$(BOLD)核心命令:$(RESET)"
	@echo "  $(CYAN)quick-start$(RESET)          快速启动开发环境 (Nginx + MySQL + Redis)"
	@echo "  $(CYAN)full-install$(RESET)         完整安装所有服务"
	@echo "  $(CYAN)status$(RESET)               查看所有服务状态"
	@echo "  $(CYAN)test-all$(RESET)             测试所有服务连接"
	@echo "  $(CYAN)troubleshoot$(RESET)         运行故障诊断"
	@echo ""
	@echo "$(BLUE)模块命令:$(RESET)"
	@echo "  1. 快速开始: $(CYAN)init, install, up, down, restart$(RESET)"
	@echo "  2. 环境管理: $(CYAN)env-init, env-edit, dev, prod$(RESET)"
	@echo "  3. 服务管理: $(CYAN)<service>-start/stop/logs/shell$(RESET)"
	@echo "     服务: mysql, redis, mongo, kafka, nsq, jenkins"
	@echo "  4. 网络管理: $(CYAN)net-create/delete/list, swarm-*$(RESET)"
	@echo "  5. SSL 证书: $(CYAN)ssl-obtain/import/renew/list$(RESET)"
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
		module_order[1] = "1. 快速开始"; \
		module_order[2] = "2. 环境管理"; \
		module_order[3] = "3. 服务管理 - MySQL"; \
		module_order[4] = "3. 服务管理 - Redis"; \
		module_order[5] = "3. 服务管理 - MongoDB"; \
		module_order[6] = "3. 服务管理 - Kafka"; \
		module_order[7] = "3. 服务管理 - NSQ"; \
		module_order[8] = "3. 服务管理 - Jenkins"; \
		module_order[9] = "4. 网络管理"; \
		module_order[10] = "5. SSL 证书"; \
		module_order[11] = "6. Nginx"; \
		module_order[12] = "7. 监控诊断"; \
		module_order[13] = "8. 测试验证"; \
		module_order[14] = "9. 维护清理"; \
		module_order[15] = "10. 帮助文档"; \
		modules["1. 快速开始"] = "^(check-env|check-scripts|init$$|init-infra|reset|clean-infra|install$$|install-nginx|install-mysql|install-redis|install-mongo|install-kafka|install-nsq|install-jenkins|up$$|down$$|restart$$|status$$|ps$$|health|quick-start|full-install|dev-setup|prod-setup)"; \
		modules["2. 环境管理"] = "^(dev$$|prod$$|env-init|env-copy|env-edit|env-show|config-show|config-validate)"; \
		modules["3. 服务管理 - MySQL"] = "^mysql-"; \
		modules["3. 服务管理 - Redis"] = "^redis-"; \
		modules["3. 服务管理 - MongoDB"] = "^mongo-"; \
		modules["3. 服务管理 - Kafka"] = "^kafka-"; \
		modules["3. 服务管理 - NSQ"] = "^nsq-"; \
		modules["3. 服务管理 - Jenkins"] = "^jenkins-"; \
		modules["4. 网络管理"] = "^(network-|net-|swarm-|port-check)"; \
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
		$(call shell_error_msg,环境文件不存在: $(ENV_FILE)); \
		$(call shell_warning_msg,请运行: make env-init); \
		exit 1; \
	fi
	$(call success_msg,环境配置正常: $(ENV))

check-scripts: ## 检查必要脚本
	@for script in "$(INFRA_SCRIPT)" "$(INSTALL_SCRIPT)" "$(COMPOSE_MANAGER)"; do \
		if [ ! -f "$$script" ]; then \
			$(call shell_error_msg,脚本不存在: $$script); \
			exit 1; \
		fi; \
	done
	$(call success_msg,脚本检查通过)

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
		$(call shell_warning_msg,操作已取消); \
	fi

.PHONY: install install-nginx install-mysql install-redis install-mongo install-kafka install-nsq install-jenkins
install: init ## 安装所有基础设施服务
	$(call shell_info_msg,安装所有基础设施服务...)
	@$(INSTALL_SCRIPT) all

install-nginx: init ## 安装 Nginx
	@$(INSTALL_SCRIPT) nginx

install-mysql: init ## 安装 MySQL
	@$(INSTALL_SCRIPT) mysql

install-redis: init ## 安装 Redis
	@$(INSTALL_SCRIPT) redis

install-mongo: init ## 安装 MongoDB
	@$(INSTALL_SCRIPT) mongo

install-kafka: init ## 安装 Kafka
	@$(INSTALL_SCRIPT) kafka

install-nsq: init ## 安装 NSQ
	@$(INSTALL_SCRIPT) nsq

install-jenkins: init ## 安装 Jenkins
	@$(INSTALL_SCRIPT) jenkins

.PHONY: up down restart
up: ## 启动所有基础设施服务
	$(call shell_info_msg,启动基础设施服务...)
	@$(COMPOSE_MANAGER) infra up all

down: ## 停止所有服务
	$(call shell_info_msg,停止基础设施服务...)
	@$(COMPOSE_MANAGER) infra down all

restart: down up ## 重启所有服务

.PHONY: status ps health
status: ## 查看基础设施和服务状态
	$(call section_title,基础设施状态)
	@$(INFRA_SCRIPT) status
	@echo ""
	$(call section_title,服务状态)
	@$(COMPOSE_MANAGER) status

ps: ## 查看运行的容器
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

health: ## 健康检查
	$(call shell_info_msg,服务健康检查...)
	@$(INFRA_SCRIPT) test

.PHONY: quick-start full-install dev-setup prod-setup
quick-start: init install-nginx install-mysql install-redis ## 快速启动开发环境
	@$(COMPOSE_MANAGER) infra up nginx
	@$(COMPOSE_MANAGER) infra up storage
	$(call success_msg,🚀 开发环境已就绪!)
	@echo ""
	$(call shell_info_msg,已启动服务:)
	@echo "  $(GREEN)•$(RESET) Nginx  (80, 443)"
	@echo "  $(GREEN)•$(RESET) MySQL  (3306)"
	@echo "  $(GREEN)•$(RESET) Redis  (6379)"

full-install: init install ## 完整安装所有服务

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
		mkdir -p compose/env/$(ENV); \
		if [ -f "compose/env/.env.example" ]; then \
			cp compose/env/.env.example "$(ENV_FILE)"; \
		else \
			touch "$(ENV_FILE)"; \
		fi; \
		$(call shell_success_msg,已创建环境配置: $(ENV_FILE)); \
		$(call shell_warning_msg,请编辑配置文件后再继续); \
	else \
		$(call shell_warning_msg,环境配置已存在: $(ENV_FILE)); \
	fi

env-copy: ## 复制环境配置 (FROM=源 TO=目标)
	$(call require_param,FROM,make env-copy FROM=dev TO=prod)
	$(call require_param,TO,make env-copy FROM=dev TO=prod)
	@mkdir -p compose/env/$(TO)
	@cp compose/env/$(FROM)/.env compose/env/$(TO)/.env
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
		$(call shell_success_msg,Docker Compose 配置有效); \
	else \
		$(call shell_error_msg,Docker Compose 配置无效); \
		exit 1; \
	fi

# ==============================================================================
# 3. 服务管理
# ==============================================================================

# --- MySQL -------------------------------------------------------------------
.PHONY: mysql-start mysql-stop mysql-restart mysql-logs mysql-shell mysql-status mysql-backup
mysql-start: init-infra ## 启动 MySQL
	@$(COMPOSE_MANAGER) infra up storage
	$(call success_msg,MySQL 已启动)

mysql-stop: ## 停止 MySQL
	@$(COMPOSE_MANAGER) infra down storage
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
	@docker exec mysql mysqldump -u root -p$(DB) > backup-$(DB)-$(shell date +%Y%m%d-%H%M%S).sql
	$(call success_msg,MySQL 备份完成)

# --- Redis -------------------------------------------------------------------
.PHONY: redis-start redis-stop redis-restart redis-logs redis-shell redis-cli redis-status redis-info
redis-start: init-infra ## 启动 Redis
	@$(COMPOSE_MANAGER) infra up storage
	$(call success_msg,Redis 已启动)

redis-stop: ## 停止 Redis
	@docker stop redis 2>/dev/null || true
	$(call success_msg,Redis 已停止)

redis-restart: redis-stop redis-start ## 重启 Redis

redis-logs: ## 查看 Redis 日志
	@docker logs -f --tail=$(LOG_LINES) redis 2>/dev/null || \
		$(call shell_error_msg,Redis 容器不存在或未运行)

redis-shell: ## 进入 Redis 容器 Shell
	@docker exec -it redis sh || \
		$(call shell_error_msg,无法连接到 Redis 容器)

redis-cli: ## 进入 Redis CLI
	@docker exec -it redis redis-cli || \
		$(call shell_error_msg,无法连接到 Redis)

redis-status: ## 查看 Redis 状态
	@docker ps --filter "name=redis" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

redis-info: ## 查看 Redis 信息
	@docker exec redis redis-cli INFO | head -20

# --- MongoDB -----------------------------------------------------------------
.PHONY: mongo-start mongo-stop mongo-restart mongo-logs mongo-shell mongo-status
mongo-start: init-infra ## 启动 MongoDB
	@$(COMPOSE_MANAGER) infra up storage
	$(call success_msg,MongoDB 已启动)

mongo-stop: ## 停止 MongoDB
	@docker stop mongodb 2>/dev/null || true
	$(call success_msg,MongoDB 已停止)

mongo-restart: mongo-stop mongo-start ## 重启 MongoDB

mongo-logs: ## 查看 MongoDB 日志
	@docker logs -f --tail=$(LOG_LINES) mongodb 2>/dev/null || \
		$(call shell_error_msg,MongoDB 容器不存在或未运行)

mongo-shell: ## 进入 MongoDB Shell
	@docker exec -it mongodb mongosh || \
		docker exec -it mongodb mongo || \
		$(call shell_error_msg,无法连接到 MongoDB)

mongo-status: ## 查看 MongoDB 状态
	@docker ps --filter "name=mongodb" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# --- Kafka -------------------------------------------------------------------
.PHONY: kafka-start kafka-stop kafka-restart kafka-logs kafka-shell kafka-status
.PHONY: kafka-topics kafka-create-topic kafka-delete-topic kafka-describe-topic
kafka-start: init-infra ## 启动 Kafka
	@$(COMPOSE_MANAGER) infra up message
	$(call success_msg,Kafka 已启动)

kafka-stop: ## 停止 Kafka
	@$(COMPOSE_MANAGER) infra down message
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
nsq-start: init-infra ## 启动 NSQ
	@$(COMPOSE_MANAGER) infra up message
	$(call success_msg,NSQ 已启动)

nsq-stop: ## 停止 NSQ
	@docker stop nsqd nsqlookupd nsqadmin 2>/dev/null || true
	$(call success_msg,NSQ 已停止)

nsq-restart: nsq-stop nsq-start ## 重启 NSQ

nsq-logs: ## 查看 NSQ 日志
	@docker logs -f --tail=$(LOG_LINES) nsqd 2>/dev/null || \
		$(call shell_error_msg,NSQ 容器不存在或未运行)

nsq-admin: ## 打开 NSQ Admin Web UI
	$(call shell_info_msg,NSQ Admin: http://localhost:4171)
	@which open >/dev/null 2>&1 && open http://localhost:4171 || \
		which xdg-open >/dev/null 2>&1 && xdg-open http://localhost:4171 || \
		echo "$(BLUE)请在浏览器中打开: http://localhost:4171$(RESET)"

nsq-status: ## 查看 NSQ 状态
	@docker ps --filter "name=nsq" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# --- Jenkins -----------------------------------------------------------------
.PHONY: jenkins-start jenkins-stop jenkins-restart jenkins-logs jenkins-shell jenkins-status jenkins-password
jenkins-start: init-infra ## 启动 Jenkins
	@$(COMPOSE_MANAGER) infra up cicd
	$(call success_msg,Jenkins 已启动)
	$(call shell_info_msg,Jenkins URL: http://localhost:8080)

jenkins-stop: ## 停止 Jenkins
	@$(COMPOSE_MANAGER) infra down cicd
	$(call success_msg,Jenkins 已停止)

jenkins-restart: jenkins-stop jenkins-start ## 重启 Jenkins

jenkins-logs: ## 查看 Jenkins 日志
	@docker logs -f --tail=$(LOG_LINES) jenkins 2>/dev/null || \
		$(call shell_error_msg,Jenkins 容器不存在或未运行)

jenkins-shell: ## 进入 Jenkins 容器 Shell
	@docker exec -it jenkins bash || \
		$(call shell_error_msg,无法连接到 Jenkins 容器)

jenkins-status: ## 查看 Jenkins 状态
	@docker ps --filter "name=jenkins" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

jenkins-password: ## 获取 Jenkins 初始管理员密码
	@docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null || \
		$(call shell_error_msg,无法获取密码，Jenkins 可能未完全启动)

# ==============================================================================
# 4. 网络管理
# ==============================================================================
.PHONY: network-list network-create network-delete network-inspect
.PHONY: net-list net-create net-delete net-inspect
.PHONY: network-init network-status network-reset
.PHONY: swarm-init swarm-leave swarm-status port-check

network-init: ## 初始化基础设施网络 (infra-frontend, infra-network)
	$(call info_msg,初始化基础设施网络...)
	@$(INFRA_SCRIPT) create
	$(call success_msg,基础设施网络创建成功)

network-status: ## 查看基础设施网络状态
	$(call info_msg,基础设施网络状态:)
	@if docker network ls --format '{{.Name}}' | grep -q '^infra-frontend$$'; then \
		echo "  $(GREEN)✅$(RESET) infra-frontend (前端网络)"; \
		docker network inspect infra-frontend --format '    子网: {{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null; \
	else \
		echo "  $(RED)❌$(RESET) infra-frontend (未创建)"; \
	fi
	@if docker network ls --format '{{.Name}}' | grep -q '^infra-network$$'; then \
		echo "  $(GREEN)✅$(RESET) infra-network (后端网络)"; \
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
.PHONY: ssl-obtain ssl-import ssl-renew ssl-list ssl-test ssl-remove

ssl-obtain: ## 申请 SSL 证书 (DOMAIN=域名 EMAIL=邮箱)
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

ssl-renew: ## 续期 SSL 证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-renew DOMAIN=example.com)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh renew $(DOMAIN)
	$(call success_msg,证书续期成功: $(DOMAIN))

ssl-list: ## 列出所有 SSL 证书
	@$(TOOLS_SCRIPTS)/ssl-manager.sh list

ssl-test: ## 测试 SSL 证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-test DOMAIN=example.com)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh test $(DOMAIN)

ssl-remove: ## 删除 SSL 证书 (DOMAIN=域名)
	$(call require_param,DOMAIN,make ssl-remove DOMAIN=example.com)
	@$(TOOLS_SCRIPTS)/ssl-manager.sh remove $(DOMAIN)
	$(call success_msg,证书删除成功: $(DOMAIN))

# ==============================================================================
# 6. Nginx 应用管理
# ==============================================================================
.PHONY: nginx-start nginx-stop nginx-restart nginx-logs nginx-reload nginx-test nginx-status
.PHONY: app-deploy app-remove app-list app-enable app-disable

nginx-start: init-infra ## 启动 Nginx
	@$(COMPOSE_MANAGER) infra up nginx
	$(call success_msg,Nginx 已启动)

nginx-stop: ## 停止 Nginx
	@$(COMPOSE_MANAGER) infra down nginx
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
		$(call shell_info_msg,显示最近所有服务日志...); \
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
	@$(NETWORK_SCRIPTS)/diagnose-network.sh test || $(call shell_warning_msg,网络存在问题)
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

test-redis: ## 测试 Redis 连接
	@printf "$(BLUE)Redis:$(RESET)     "
	@docker exec redis redis-cli ping 2>/dev/null | grep -q PONG && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

test-mongo: ## 测试 MongoDB 连接
	@printf "$(BLUE)MongoDB:$(RESET)   "
	@docker exec mongodb mongosh --eval "db.adminCommand('ping')" 2>/dev/null | grep -q ok && \
		echo "$(GREEN)✅ 正常$(RESET)" || \
		echo "$(RED)❌ 失败$(RESET)"

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
		$(call success_msg,清理完成); \
	else \
		$(call warning_msg,操作已取消); \
	fi

clean-volumes: ## 清理未使用的数据卷 (危险!)
	$(call shell_error_msg,警告: 这将删除所有未使用的数据卷!)
	@read -p "确认删除? (输入 'yes' 确认): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker volume prune -f; \
		$(call success_msg,数据卷清理完成); \
	else \
		$(call warning_msg,操作已取消); \
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
# 结束
# ==============================================================================


# Infrastructure Management Makefile
# 简化的基础设施项目管理工具
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
INIT_SCRIPTS_DIR := $(SCRIPTS_DIR)/init-components
INFRA_SCRIPT := $(INIT_SCRIPTS_DIR)/init-infrastructure.sh
INSTALL_SCRIPT := $(INIT_SCRIPTS_DIR)/install-components.sh
COMPOSE_MANAGER := $(INIT_SCRIPTS_DIR)/compose-manager.sh

# Compose 配置路径
COMPOSE_DIR := compose/infra
COMPOSE_FILES := -f $(COMPOSE_DIR)/docker-compose.yml

# 颜色定义
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
CYAN := \033[36m
RESET := \033[0m

# ==============================================================================
# 默认目标和帮助
# ==============================================================================
.DEFAULT_GOAL := help

.PHONY: help
help: ## 显示帮助信息
	@echo ""
	@echo "$(GREEN)🐳 基础设施项目管理工具$(RESET)"
	@echo ""
	@echo "$(BLUE)项目结构:$(RESET)"
	@echo "  compose/infra/          - 基础设施 Docker Compose 配置"
	@echo "  compose/env/            - 环境变量配置"
	@echo "  components/             - 服务组件配置"
	@echo "  scripts/                - 管理脚本"
	@echo ""
	@echo "$(BLUE)可用命令:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BLUE)快速开始:$(RESET)"
	@echo "  1. make init             # 初始化基础设施"
	@echo "  2. make install          # 安装所有服务"
	@echo "  3. make up               # 启动所有服务"
	@echo "  4. make status           # 查看服务状态"
	@echo ""
	@echo "$(BLUE)应用配置管理:$(RESET)"
	@echo "  make app-deploy APP=blog CONFIG=./nginx/blog.conf  # 部署应用配置"
	@echo "  make app-remove APP=blog                           # 移除应用配置"
	@echo "  make app-list                                      # 列出所有配置"
	@echo "  make nginx-test                                    # 测试配置"
	@echo "  make nginx-reload                                  # 重载配置"
	@echo ""
	@echo "$(BLUE)SSL 证书管理:$(RESET)"
	@echo "  make ssl-obtain DOMAIN=blog.example.com EMAIL=admin@example.com  # 申请证书"
	@echo "  make ssl-import DOMAIN=blog.example.com CERT=./blog.crt KEY=./blog.key  # 导入证书"
	@echo "  make ssl-renew                                     # 续期所有证书"
	@echo "  make ssl-list                                      # 列出所有证书"
	@echo "  make ssl-config DOMAIN=blog.example.com            # 生成 SSL 配置"
	@echo "  make ssl-setup                                     # 设置自动续期"
	@echo ""
	@echo "$(BLUE)环境变量:$(RESET)"
	@echo "  ENV=dev|prod            指定环境 (默认: dev)"
	@echo "  APP=app-name            指定应用名称"
	@echo "  CONFIG=config-file      指定配置文件路径"
	@echo "  DOMAIN=domain-name      指定域名"
	@echo "  CERT=cert-file-path     指定证书文件路径"
	@echo "  KEY=key-file-path       指定私钥文件路径"
	@echo "  EMAIL=email-address     指定邮箱地址"
	@echo ""
	@echo "$(BLUE)示例:$(RESET)"
	@echo "  make ENV=prod init       # 生产环境初始化"
	@echo "  make status              # 查看服务状态"
	@echo "  make logs SERVICE=nginx  # 查看 nginx 日志"

# ==============================================================================
# 环境检查
# ==============================================================================
.PHONY: check-env check-scripts
check-env: ## 检查环境配置
	@echo "$(BLUE)检查环境配置 ($(ENV))...$(RESET)"
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "$(RED)❌ 环境文件不存在: $(ENV_FILE)$(RESET)"; \
		echo "$(YELLOW)请先创建环境配置文件$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)✅ 环境配置正常: $(ENV)$(RESET)"

check-scripts: ## 检查必要脚本
	@echo "$(BLUE)检查脚本完整性...$(RESET)"
	@for script in "$(INFRA_SCRIPT)" "$(INSTALL_SCRIPT)" "$(COMPOSE_MANAGER)"; do \
		if [ ! -f "$$script" ]; then \
			echo "$(RED)❌ 脚本不存在: $$script$(RESET)"; \
			exit 1; \
		fi; \
	done
	@echo "$(GREEN)✅ 脚本检查通过$(RESET)"

# ==============================================================================
# 基础设施初始化
# ==============================================================================
.PHONY: init init-infra
init: check-scripts init-infra ## 完整初始化 (网络+卷)
	@echo "$(GREEN)✅ 基础设施初始化完成$(RESET)"

init-infra: ## 初始化基础设施网络和卷
	@echo "$(BLUE)初始化基础设施网络和卷...$(RESET)"
	@$(INFRA_SCRIPT) create

.PHONY: reset clean-infra
reset: ## 重置基础设施 (删除后重新创建)
	@echo "$(YELLOW)重置基础设施...$(RESET)"
	@$(INFRA_SCRIPT) reset

clean-infra: ## 清理基础设施 (谨慎操作)
	@echo "$(RED)清理基础设施...$(RESET)"
	@read -p "确认删除所有基础设施网络和卷? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		$(INFRA_SCRIPT) remove; \
	else \
		echo "$(YELLOW)操作已取消$(RESET)"; \
	fi

# ==============================================================================
# 服务安装
# ==============================================================================
.PHONY: install install-nginx install-mysql install-redis install-mongo install-kafka install-jenkins
install: init ## 安装所有基础设施服务
	@echo "$(BLUE)安装所有基础设施服务...$(RESET)"
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

install-jenkins: init ## 安装 Jenkins
	@$(INSTALL_SCRIPT) jenkins

# ==============================================================================
# 服务管理
# ==============================================================================
.PHONY: up down restart
up: ## 启动所有基础设施服务
	@echo "$(BLUE)启动基础设施服务...$(RESET)"
	@$(COMPOSE_MANAGER) infra up all

down: ## 停止所有服务
	@echo "$(BLUE)停止基础设施服务...$(RESET)"
	@$(COMPOSE_MANAGER) infra down all

restart: down up ## 重启所有服务

.PHONY: up-nginx up-storage up-message up-cicd
up-nginx: ## 启动网关服务
	@$(COMPOSE_MANAGER) infra up nginx

up-storage: ## 启动存储服务 (MySQL, Redis, MongoDB)
	@$(COMPOSE_MANAGER) infra up storage

up-message: ## 启动消息服务 (Kafka)
	@$(COMPOSE_MANAGER) infra up message

up-cicd: ## 启动 CI/CD 服务 (Jenkins)
	@$(COMPOSE_MANAGER) infra up cicd

# ==============================================================================
# 状态和监控
# ==============================================================================
.PHONY: status logs ps health
status: ## 查看基础设施和服务状态
	@echo "$(BLUE)基础设施状态:$(RESET)"
	@$(INFRA_SCRIPT) status
	@echo ""
	@echo "$(BLUE)服务状态:$(RESET)"
	@$(COMPOSE_MANAGER) status

logs: ## 查看服务日志 (SERVICE=服务名)
ifdef SERVICE
	@$(COMPOSE_MANAGER) logs $(SERVICE)
else
	@echo "$(YELLOW)请指定服务名: make logs SERVICE=nginx$(RESET)"
	@echo "$(BLUE)可用服务: nginx, mysql, redis, mongo, kafka, jenkins$(RESET)"
endif

ps: ## 查看运行的容器
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

health: ## 健康检查
	@echo "$(BLUE)服务健康检查...$(RESET)"
	@$(INFRA_SCRIPT) test

# ==============================================================================
# 开发和维护
# ==============================================================================
.PHONY: shell backup clean
shell: ## 进入服务容器 (SERVICE=服务名)
ifdef SERVICE
	@docker exec -it $(SERVICE) /bin/bash || docker exec -it $(SERVICE) /bin/sh
else
	@echo "$(YELLOW)请指定服务名: make shell SERVICE=nginx$(RESET)"
endif

backup: ## 备份数据 (基本实现)
	@echo "$(BLUE)创建数据备份...$(RESET)"
	@mkdir -p backups
	@tar -czf backups/infra-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz \
		/data/infra 2>/dev/null || echo "$(YELLOW)注意: 某些文件可能需要 sudo 权限$(RESET)"
	@echo "$(GREEN)✅ 备份完成$(RESET)"

clean: ## 清理未使用的 Docker 资源
	@echo "$(BLUE)清理 Docker 资源...$(RESET)"
	@docker system prune -f
	@docker volume prune -f
	@echo "$(GREEN)✅ 清理完成$(RESET)"

# ==============================================================================
# 网络和测试
# ==============================================================================
.PHONY: network-test port-check
network-test: ## 测试网络连通性
	@echo "$(BLUE)测试网络连通性...$(RESET)"
	@docker network ls | grep infra || echo "$(RED)❌ infra 网络不存在$(RESET)"
	@for net in infra-frontend infra-backend; do \
		if docker network inspect $$net >/dev/null 2>&1; then \
			echo "$(GREEN)✅ $$net 网络正常$(RESET)"; \
		else \
			echo "$(RED)❌ $$net 网络不存在$(RESET)"; \
		fi; \
	done

port-check: ## 检查端口占用
	@echo "$(BLUE)检查常用端口占用...$(RESET)"
	@for port in 80 443 3306 6379 27017 9092 8080; do \
		if lsof -i:$$port >/dev/null 2>&1; then \
			echo "$(YELLOW)⚠️  端口 $$port 已占用$(RESET)"; \
		else \
			echo "$(GREEN)✅ 端口 $$port 可用$(RESET)"; \
		fi; \
	done

# ==============================================================================
# 环境切换
# ==============================================================================
.PHONY: dev prod
dev: ## 切换到开发环境
	@$(MAKE) ENV=dev status

prod: ## 切换到生产环境  
	@$(MAKE) ENV=prod status

# ==============================================================================
# 配置管理
# ==============================================================================
.PHONY: config-show config-validate
config-show: check-env ## 显示当前环境配置
	@echo "$(BLUE)当前环境配置 ($(ENV)):$(RESET)"
	@echo "环境文件: $(ENV_FILE)"
	@if [ -f "$(ENV_FILE)" ]; then \
		echo ""; \
		grep -E '^[^#].*=' "$(ENV_FILE)" | head -10; \
		echo "..."; \
	fi

config-validate: check-env ## 验证配置文件
	@echo "$(BLUE)验证配置文件...$(RESET)"
	@if docker compose $(COMPOSE_FILES) --env-file $(ENV_FILE) config >/dev/null 2>&1; then \
		echo "$(GREEN)✅ Docker Compose 配置有效$(RESET)"; \
	else \
		echo "$(RED)❌ Docker Compose 配置无效$(RESET)"; \
		exit 1; \
	fi

# ==============================================================================
# 应用 Nginx 配置管理
# ==============================================================================
.PHONY: app-deploy app-remove app-list nginx-reload nginx-test

app-deploy: ## 部署应用 nginx 配置 (使用: make app-deploy APP=blog CONFIG=./nginx/blog.conf)
	@if [ -z "$(APP)" ] || [ -z "$(CONFIG)" ]; then \
		echo "$(RED)错误: 请提供应用名称和配置文件$(RESET)"; \
		echo "$(YELLOW)使用方式: make app-deploy APP=blog CONFIG=./nginx/blog.conf$(RESET)"; \
		exit 1; \
	fi
	@bash scripts/utils/nginx-app-manager.sh deploy $(APP) $(CONFIG)

app-remove: ## 移除应用 nginx 配置 (使用: make app-remove APP=blog)
	@if [ -z "$(APP)" ]; then \
		echo "$(RED)错误: 请提供应用名称$(RESET)"; \
		echo "$(YELLOW)使用方式: make app-remove APP=blog$(RESET)"; \
		exit 1; \
	fi
	@bash scripts/utils/nginx-app-manager.sh remove $(APP)

app-list: ## 列出所有已部署的应用配置
	@bash scripts/utils/nginx-app-manager.sh list

nginx-reload: ## 重载 nginx 配置
	@bash scripts/utils/nginx-app-manager.sh reload

nginx-test: ## 测试 nginx 配置
	@bash scripts/utils/nginx-app-manager.sh test

# ==============================================================================
# SSL 证书管理
# ==============================================================================
.PHONY: ssl-obtain ssl-import ssl-renew ssl-list ssl-remove ssl-config ssl-setup

ssl-obtain: ## 申请 SSL 证书 (使用: make ssl-obtain DOMAIN=blog.example.com EMAIL=admin@example.com)
	@if [ -z "$(DOMAIN)" ]; then \
		echo "$(RED)错误: 请提供域名$(RESET)"; \
		echo "$(YELLOW)使用方式: make ssl-obtain DOMAIN=blog.example.com EMAIL=admin@example.com$(RESET)"; \
		exit 1; \
	fi
	@bash scripts/utils/ssl-manager.sh obtain $(DOMAIN) $(EMAIL)

ssl-import: ## 导入外部 SSL 证书 (使用: make ssl-import DOMAIN=blog.example.com CERT=./blog.crt KEY=./blog.key)
	@if [ -z "$(DOMAIN)" ] || [ -z "$(CERT)" ] || [ -z "$(KEY)" ]; then \
		echo "$(RED)错误: 请提供域名、证书文件和私钥文件$(RESET)"; \
		echo "$(YELLOW)使用方式: make ssl-import DOMAIN=blog.example.com CERT=./blog.crt KEY=./blog.key$(RESET)"; \
		exit 1; \
	fi
	@bash scripts/utils/ssl-manager.sh import $(DOMAIN) $(CERT) $(KEY)

ssl-renew: ## 续期所有 SSL 证书
	@bash scripts/utils/ssl-manager.sh renew

ssl-list: ## 列出所有 SSL 证书
	@bash scripts/utils/ssl-manager.sh list

ssl-remove: ## 删除 SSL 证书 (使用: make ssl-remove DOMAIN=blog.example.com)
	@if [ -z "$(DOMAIN)" ]; then \
		echo "$(RED)错误: 请提供域名$(RESET)"; \
		echo "$(YELLOW)使用方式: make ssl-remove DOMAIN=blog.example.com$(RESET)"; \
		exit 1; \
	fi
	@bash scripts/utils/ssl-manager.sh remove $(DOMAIN)

ssl-config: ## 生成 SSL 配置模板 (使用: make ssl-config DOMAIN=blog.example.com)
	@if [ -z "$(DOMAIN)" ]; then \
		echo "$(RED)错误: 请提供域名$(RESET)"; \
		echo "$(YELLOW)使用方式: make ssl-config DOMAIN=blog.example.com > blog-ssl.conf$(RESET)"; \
		exit 1; \
	fi
	@bash scripts/utils/ssl-manager.sh config $(DOMAIN)

ssl-setup: ## 设置 SSL 证书自动续期
	@bash scripts/utils/ssl-manager.sh setup-auto


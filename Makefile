# Shared Infrastructure Makefile
# 统一管理 Nginx, MySQL, Redis 基础设施

# ==============================================================================
# 全局变量 - 组件化配置
# ==============================================================================
PROJECT_NAME := shared-infra
ENV_FILE := compose/env/prod/.env

# 基础配置文件
BASE_COMPOSE := compose/base/docker-compose.yml

# 节点覆盖文件
NODE_A_OVERRIDE := compose/nodes/a.override.yml
NODE_B_OVERRIDE := compose/nodes/b.override.yml

# 组件覆盖文件
NGINX_OVERRIDE := components/nginx/override.yml
MYSQL_OVERRIDE := components/mysql/override.yml
REDIS_OVERRIDE := components/redis/override.yml
MONGO_OVERRIDE := components/mongo/override.yml
KAFKA_OVERRIDE := components/kafka/override.yml

# 节点 A 组合命令
NODE_A_CMD := docker compose --env-file $(ENV_FILE) -f $(BASE_COMPOSE) -f $(NODE_A_OVERRIDE) -f $(NGINX_OVERRIDE) -f $(MYSQL_OVERRIDE) -f $(REDIS_OVERRIDE) -f $(MONGO_OVERRIDE)

# 节点 B 组合命令  
NODE_B_CMD := docker compose --env-file $(ENV_FILE) -f $(BASE_COMPOSE) -f $(NODE_B_OVERRIDE) -f $(KAFKA_OVERRIDE)

# 检测当前节点类型 (通过检查服务是否运行)
NODE_TYPE := $(shell if docker ps --format '{{.Names}}' | grep -q nginx 2>/dev/null; then echo "node-a"; elif docker ps --format '{{.Names}}' | grep -q kafka 2>/dev/null; then echo "node-b"; else echo "unknown"; fi)

# 服务名称
NGINX_SERVICE := nginx
MYSQL_SERVICE := mysql
REDIS_SERVICE := redis
MONGO_SERVICE := mongo
KAFKA_SERVICE := kafka

# 业务服务管理 - 通过外部项目独立管理
# 注意: 具体业务服务应该在各自项目中定义和管理
# infra 项目只提供基础设施和应用接入能力

# 网络配置
FRONTEND_NETWORK := frontend
BACKEND_NETWORK := backend

# 颜色定义
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
RESET := \033[0m

# ==============================================================================
# 默认目标和帮助
# ==============================================================================
.PHONY: help
help: ## 显示帮助信息
	@echo ""
	@echo "$(BOLD)$(GREEN)🐳 组件化基础设施项目管理工具$(RESET)"
	@echo ""
	@echo "$(BOLD)项目结构:$(RESET)"
	@echo "  compose/base/           - 基础服务定义"
	@echo "  compose/nodes/          - 节点特定配置"
	@echo "  components/             - 组件配置文件"
	@echo "  scripts/                - 部署脚本"
	@echo ""
	@echo "$(BOLD)可用命令:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BOLD)部署流程:$(RESET)"
	@echo "  1. make init-node-a      # 初始化节点 A"
	@echo "  2. 编辑 .env 文件         # 配置环境变量"
	@echo "  3. make deploy-a         # 部署节点 A"
	@echo ""
	@echo "$(BOLD)开发命令示例:$(RESET)"
	@echo "  make dev-start NODE=a SERVICE=nginx"
	@echo "  make dev-logs NODE=a SERVICE=mysql"
	@echo "  make config-show NODE=a"
	@echo "  make ssl-setup DOMAIN=example.com"
	@echo ""

.PHONY: all
all: help

# ==============================================================================
# 环境管理
# ==============================================================================
.PHONY: init
init: ## 初始化项目环境
	@echo "$(BLUE)初始化生产环境...$(RESET)"
	@echo "$(YELLOW)请选择节点类型:$(RESET)"
	@echo "  1. 节点 A (Web/事务侧): make init-node-a"
	@echo "  2. 节点 B (计算侧): make init-node-b"
	@echo "  3. 单机部署: 使用原有的 make init-single"

.PHONY: init-node-a
init-node-a: ## 初始化节点 A 环境 (Web/事务侧)
	@echo "$(BLUE)初始化节点 A 环境...$(RESET)"
	@if [ ! -f "$(ENV_FILE)" ]; then \
		cp compose/env/prod/.env.example $(ENV_FILE); \
		echo "$(YELLOW)已创建环境配置文件: $(ENV_FILE)$(RESET)"; \
		echo "$(YELLOW)请编辑文件并配置节点IP和密码$(RESET)"; \
	fi
	@mkdir -p components/nginx/{conf.d,ssl} components/mysql/init components/redis components/mongo
	@sudo mkdir -p /data/{mysql,mongo,redis,jenkins,logs/{nginx,mysql,mongo,redis,jenkins}}
	@sudo chown -R $(USER):$(USER) /data
	@docker network create infra-frontend 2>/dev/null || true
	@docker network create infra-backend 2>/dev/null || true
	@echo "$(GREEN)✅ 节点 A 环境初始化完成$(RESET)"
	@echo "$(YELLOW)📋 下一步:$(RESET)"
	@echo "  1. 编辑配置: vim $(ENV_FILE)"
	@echo "  2. 部署节点A: ./scripts/deploy_a.sh"

.PHONY: init-node-b  
init-node-b: ## 初始化节点 B 环境 (计算侧)
	@echo "$(BLUE)初始化节点 B 环境...$(RESET)"
	@if [ ! -f "$(ENV_FILE)" ]; then \
		cp compose/env/prod/.env.example $(ENV_FILE); \
		echo "$(YELLOW)已创建环境配置文件: $(ENV_FILE)$(RESET)"; \
		echo "$(YELLOW)请编辑文件并配置节点IP和密码$(RESET)"; \
	fi
	@mkdir -p components/kafka
	@sudo mkdir -p /data/{kafka,logs/{kafka,qs}}
	@sudo chown -R $(USER):$(USER) /data
	@docker network create infra-backend 2>/dev/null || true
	@echo "$(GREEN)✅ 节点 B 环境初始化完成$(RESET)"
	@echo "$(YELLOW)📋 下一步:$(RESET)"
	@echo "  1. 编辑配置: vim $(ENV_FILE)"
	@echo "  2. 部署节点B: ./scripts/deploy_b.sh"

.PHONY: init-single
init-single: ## 初始化单机环境 (向后兼容)
	@echo "$(BLUE)初始化单机环境...$(RESET)"
	@if [ ! -f "$(ENV_FILE)" ]; then \
		cp .env.example $(ENV_FILE); \
		echo "$(YELLOW)已创建 .env 文件，请根据需要修改配置$(RESET)"; \
	fi
	@mkdir -p nginx/conf.d nginx/ssl mysql/init logs
	@sudo mkdir -p /data/{mysql,mongo,redis,kafka,logs/{nginx,mysql,mongo,redis,kafka,miniblog,qs}}
	@sudo chown -R $(USER):$(USER) /data
	@docker network create $(FRONTEND_NETWORK) 2>/dev/null || true
	@docker network create $(BACKEND_NETWORK) 2>/dev/null || true
	@echo "$(GREEN)✅ 单机环境初始化完成$(RESET)"

.PHONY: check-env
check-env: ## 检查环境配置
	@echo "$(BLUE)检查环境配置...$(RESET)"
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "$(RED)❌ .env 文件不存在，请先运行 make init$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)✅ 环境配置正常$(RESET)"

# ==============================================================================
# 服务管理 - 统一操作
# ==============================================================================
.PHONY: up
up: check-env ## 智能启动服务 (根据配置自动检测节点类型)
	@echo "$(BLUE)检测节点类型...$(RESET)"
	@if [ -f "$(ENV_FILE)" ] && grep -q "NODE_A_IP" $(ENV_FILE); then \
		if grep -q "KAFKA_PORT" $(ENV_FILE) && ! grep -q "NGINX_HTTP_PORT" $(ENV_FILE); then \
			echo "$(BLUE)检测到节点 B 配置$(RESET)"; \
			$(MAKE) up-node-b; \
		else \
			echo "$(BLUE)检测到节点 A 配置$(RESET)"; \
			$(MAKE) up-node-a; \
		fi \
	else \
		echo "$(YELLOW)使用自动部署脚本：./scripts/deploy_a.sh 或 ./scripts/deploy_b.sh$(RESET)"; \
	fi

.PHONY: up-node-a
up-node-a: check-env ## 启动节点 A 服务 (Web/事务侧)
	@echo "$(BLUE)启动节点 A 所有服务...$(RESET)"
	@$(NODE_A_CMD) up -d
	@echo "$(GREEN)✅ 节点 A 服务启动完成$(RESET)"
	@$(MAKE) info-node-a

.PHONY: up-node-b
up-node-b: check-env ## 启动节点 B 服务 (计算侧)  
	@echo "$(BLUE)启动节点 B 所有服务...$(RESET)"
	@$(NODE_B_CMD) up -d
	@echo "$(GREEN)✅ 节点 B 服务启动完成$(RESET)"
	@$(MAKE) info-node-b

.PHONY: down
down: ## 智能停止服务 (自动检测运行的节点类型)
	@echo "$(BLUE)停止服务...$(RESET)"
	@if [ "$(NODE_TYPE)" = "node-a" ]; then \
		echo "$(BLUE)检测到节点 A，停止节点 A 服务$(RESET)"; \
		$(NODE_A_CMD) down; \
	elif [ "$(NODE_TYPE)" = "node-b" ]; then \
		echo "$(BLUE)检测到节点 B，停止节点 B 服务$(RESET)"; \
		$(NODE_B_CMD) down; \
	else \
		echo "$(YELLOW)未检测到运行的服务$(RESET)"; \
	fi
	@echo "$(GREEN)✅ 服务已停止$(RESET)"

.PHONY: restart
restart: down up ## 重启所有服务

.PHONY: status
status: ## 查看服务状态
	@echo "$(BLUE)服务状态 ($(NODE_TYPE)):$(RESET)"
	@if [ "$(NODE_TYPE)" = "node-a" ]; then \
		$(NODE_A_CMD) ps; \
	elif [ "$(NODE_TYPE)" = "node-b" ]; then \
		$(NODE_B_CMD) ps; \
	else \
		echo "$(YELLOW)未检测到运行的服务$(RESET)"; \
		docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"; \
	fi

.PHONY: logs
logs: ## 查看所有服务日志
	@if [ "$(NODE_ROLE)" = "web" ]; then \
		docker compose -f $(NODE_A_COMPOSE_FILE) logs -f; \
	elif [ "$(NODE_ROLE)" = "compute" ]; then \
		docker compose -f $(NODE_B_COMPOSE_FILE) logs -f; \
	else \
		docker compose logs -f; \
	fi

.PHONY: stats
stats: ## 查看资源使用统计
	@echo "$(BLUE)资源使用统计 (节点: $(NODE_ROLE)):$(RESET)"
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.PIDs}}"

# ==============================================================================
# 服务管理 - 单独操作
# ==============================================================================
.PHONY: nginx-up
nginx-up: check-env ## 启动 Nginx 服务
	@echo "$(BLUE)启动 Nginx 服务...$(RESET)"
	@docker compose up -d $(NGINX_SERVICE)
	@echo "$(GREEN)✅ Nginx 服务启动完成$(RESET)"

.PHONY: mysql-up
mysql-up: check-env ## 启动 MySQL 服务
	@echo "$(BLUE)启动 MySQL 服务...$(RESET)"
	@docker compose up -d $(MYSQL_SERVICE)
	@echo "$(GREEN)✅ MySQL 服务启动完成$(RESET)"

.PHONY: redis-up
redis-up: check-env ## 启动 Redis 服务
	@echo "$(BLUE)启动 Redis 服务...$(RESET)"
	@docker compose up -d $(REDIS_SERVICE)
	@echo "$(GREEN)✅ Redis 服务启动完成$(RESET)"

.PHONY: nginx-logs
nginx-logs: ## 查看 Nginx 日志
	@docker compose logs -f $(NGINX_SERVICE)

.PHONY: mysql-logs
mysql-logs: ## 查看 MySQL 日志
	@docker compose logs -f $(MYSQL_SERVICE)

.PHONY: redis-logs
redis-logs: ## 查看 Redis 日志
	@docker compose logs -f $(REDIS_SERVICE)

# ==============================================================================
# 应用管理
# ==============================================================================
.PHONY: add-app
add-app: ## 添加新应用 (APP_NAME=xxx APP_PORT=xxx APP_PATH=xxx)
	@if [ -z "$(APP_NAME)" ]; then \
		echo "$(RED)❌ 请指定应用名称: make add-app APP_NAME=myapp APP_PORT=8080 APP_PATH=/myapp$(RESET)"; \
		exit 1; \
	fi
	@echo "$(BLUE)添加应用: $(APP_NAME)...$(RESET)"
	@./scripts/add-app.sh "$(APP_NAME)" "$(APP_PORT)" "$(APP_PATH)"
	@echo "$(GREEN)✅ 应用 $(APP_NAME) 添加完成$(RESET)"

.PHONY: remove-app
remove-app: ## 移除应用 (APP_NAME=xxx)
	@if [ -z "$(APP_NAME)" ]; then \
		echo "$(RED)❌ 请指定应用名称: make remove-app APP_NAME=myapp$(RESET)"; \
		exit 1; \
	fi
	@echo "$(BLUE)移除应用: $(APP_NAME)...$(RESET)"
	@./scripts/remove-app.sh "$(APP_NAME)"
	@echo "$(GREEN)✅ 应用 $(APP_NAME) 移除完成$(RESET)"

.PHONY: list-apps
list-apps: ## 列出所有已配置的应用
	@echo "$(BLUE)已配置的应用:$(RESET)"
	@ls -1 nginx/conf.d/apps/*.conf 2>/dev/null | sed 's|nginx/conf.d/apps/||' | sed 's|.conf||' || echo "暂无应用配置"

# ==============================================================================
# Nginx 管理
# ==============================================================================
.PHONY: nginx-reload
nginx-reload: ## 重新加载 Nginx 配置
	@echo "$(BLUE)重新加载 Nginx 配置...$(RESET)"
	@docker compose exec $(NGINX_SERVICE) nginx -s reload
	@echo "$(GREEN)✅ Nginx 配置重新加载完成$(RESET)"

.PHONY: nginx-test
nginx-test: ## 测试 Nginx 配置
	@echo "$(BLUE)测试 Nginx 配置...$(RESET)"
	@docker compose exec $(NGINX_SERVICE) nginx -t

.PHONY: nginx-status
nginx-status: ## 查看 Nginx 状态页面
	@curl -s http://localhost/nginx_status || echo "$(YELLOW)Nginx 状态页面未配置$(RESET)"

# ==============================================================================
# 数据库管理
# ==============================================================================
.PHONY: mysql-shell
mysql-shell: ## 连接到 MySQL 命令行
	@echo "$(BLUE)连接到 MySQL...$(RESET)"
	@docker compose exec $(MYSQL_SERVICE) mysql -uroot -p

.PHONY: mysql-backup
mysql-backup: ## 备份所有数据库 (BACKUP_NAME=xxx)
	@echo "$(BLUE)备份 MySQL 数据库...$(RESET)"
	@./scripts/backup.sh mysql "$(BACKUP_NAME)"

.PHONY: redis-shell
redis-shell: ## 连接到 Redis 命令行
	@echo "$(BLUE)连接到 Redis...$(RESET)"
	@docker compose exec $(REDIS_SERVICE) redis-cli

.PHONY: redis-backup
redis-backup: ## 备份 Redis 数据
	@echo "$(BLUE)备份 Redis 数据...$(RESET)"
	@./scripts/backup.sh redis "$(BACKUP_NAME)"

# ==============================================================================
# 监控和维护
# ==============================================================================
.PHONY: health
health: ## 检查所有服务健康状态
	@echo "$(BLUE)检查服务健康状态...$(RESET)"
	@echo "Nginx: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "DOWN")"
	@echo "MySQL: $(shell docker compose exec -T $(MYSQL_SERVICE) mysqladmin ping -uroot --password=$${MYSQL_ROOT_PASSWORD} --silent && echo "UP" || echo "DOWN")"
	@echo "Redis: $(shell docker compose exec -T $(REDIS_SERVICE) redis-cli ping 2>/dev/null || echo "DOWN")"

.PHONY: info
info: ## 显示服务信息 (智能检测节点类型)
	@if [ "$(NODE_ROLE)" = "web" ]; then \
		$(MAKE) info-node-a; \
	elif [ "$(NODE_ROLE)" = "compute" ]; then \
		$(MAKE) info-node-b; \
	else \
		$(MAKE) info-single; \
	fi

.PHONY: info-node-a
info-node-a: ## 显示节点 A 服务信息
	@echo "$(BLUE)🅰️ 节点 A 服务信息 (Web/事务侧):$(RESET)"
	@echo "$(YELLOW)📋 对外服务端口:$(RESET)"
	@echo "  🌐 Nginx HTTP:  http://localhost:80"
	@echo "  🌐 Nginx HTTPS: https://localhost:443"
	@echo "  🔧 Jenkins:     http://localhost:8080"
	@echo ""
	@echo "$(YELLOW)🔗 内部服务端口:$(RESET)"
	@echo "  🗄️ MySQL:      localhost:3306"
	@echo "  💾 Redis:      localhost:6379"
	@echo "  🍃 MongoDB:    localhost:27017"
	@echo ""
	@echo "$(YELLOW)📱 业务应用:$(RESET)"
	@echo "  📝 MiniBlog:   http://localhost/blog/"
	@echo "  📊 QS API:     http://localhost/qs/api/"
	@echo "  📈 QS Collect: http://localhost/qs/collect/"
	@echo ""
	@echo "$(YELLOW)🔧 管理工具:$(RESET)"
	@echo "  健康检查: curl http://localhost/health"
	@echo "  Nginx 状态: curl http://localhost/nginx_status"

.PHONY: info-node-b
info-node-b: ## 显示节点 B 服务信息
	@echo "$(BLUE)🅱️ 节点 B 服务信息 (计算侧):$(RESET)"
	@echo "$(YELLOW)📋 对外服务端口:$(RESET)"
	@echo "  🔍 QS Evaluation: http://localhost:8080"
	@echo ""
	@echo "$(YELLOW)🔗 内部服务端口:$(RESET)"
	@echo "  ⚡ Kafka:      localhost:9092"
	@echo ""
	@echo "$(YELLOW)🧠 计算服务:$(RESET)"
	@echo "  🔍 数据评估:   内部处理，通过节点A访问"
	@echo ""
	@echo "$(YELLOW)🔧 管理工具:$(RESET)"
	@echo "  健康检查: curl http://localhost:8080/health"

.PHONY: info-single
info-single: ## 显示单机服务信息 (向后兼容)
	@echo "$(BLUE)基础设施服务信息 (单机模式):$(RESET)"
	@echo "$(YELLOW)📋 服务端口:$(RESET)"
	@echo "  Nginx:  http://localhost:80"
	@echo "  MySQL:  localhost:3306"
	@echo "  Redis:  localhost:6379"
	@echo ""
	@echo "$(YELLOW)🔗 管理工具:$(RESET)"
	@echo "  健康检查: curl http://localhost/health"
	@echo "  Nginx 状态: curl http://localhost/nginx_status"
	@echo ""
	@echo "$(YELLOW)📁 配置文件:$(RESET)"
	@echo "  应用配置: nginx/conf.d/apps/"
	@echo "  SSL 证书: nginx/ssl/"
	@echo "  数据目录: mysql/data/, redis/data/"

.PHONY: clean
clean: ## 清理未使用的 Docker 资源
	@echo "$(BLUE)清理 Docker 资源...$(RESET)"
	@docker system prune -f
	@echo "$(GREEN)✅ 清理完成$(RESET)"

.PHONY: backup-all
backup-all: ## 完整备份所有数据
	@echo "$(BLUE)完整备份所有数据...$(RESET)"
	@./scripts/backup.sh all "$(shell date +%Y%m%d_%H%M%S)"

# ==============================================================================
# 开发和调试
# ==============================================================================
.PHONY: dev-setup
dev-setup: init up ## 开发环境快速设置
	@echo "$(GREEN)🚀 开发环境设置完成！$(RESET)"
	@$(MAKE) info

.PHONY: port-check
port-check: ## 检查端口占用情况
	@echo "$(BLUE)检查端口占用情况...$(RESET)"
	@lsof -i :80 -i :443 -i :3306 -i :6379 2>/dev/null || echo "所有端口都可用"

.PHONY: network-diagnose
network-diagnose: ## 网络诊断
	@echo "$(BLUE)网络诊断...$(RESET)"
	@docker network inspect $(NETWORK_NAME) || echo "网络不存在"
	@docker compose exec $(NGINX_SERVICE) ping -c 1 $(MYSQL_SERVICE) || echo "Nginx -> MySQL 连接失败"
	@docker compose exec $(NGINX_SERVICE) ping -c 1 $(REDIS_SERVICE) || echo "Nginx -> Redis 连接失败"

# ==============================================================================
# 生产环境专用命令
# ==============================================================================
.PHONY: prod-setup
prod-setup: init system-optimize ## 生产环境完整设置
	@echo "$(GREEN)🚀 生产环境设置完成！$(RESET)"
	@$(MAKE) info

.PHONY: system-optimize
system-optimize: ## 系统参数优化
	@echo "$(BLUE)优化系统参数...$(RESET)"
	@echo "fs.file-max=500000" | sudo tee -a /etc/sysctl.conf
	@echo "net.core.somaxconn=1024" | sudo tee -a /etc/sysctl.conf
	@echo "net.ipv4.tcp_max_syn_backlog=2048" | sudo tee -a /etc/sysctl.conf
	@echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
	@sudo sysctl -p
	@echo "$(GREEN)✅ 系统参数优化完成$(RESET)"

.PHONY: setup-swap
setup-swap: ## 设置 2G 交换空间
	@echo "$(BLUE)设置交换空间...$(RESET)"
	@sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
	@sudo mkswap /swapfile && sudo swapon /swapfile
	@echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
	@echo "$(GREEN)✅ 交换空间设置完成$(RESET)"

.PHONY: mongo-up
mongo-up: check-env ## 启动 MongoDB 服务
	@echo "$(BLUE)启动 MongoDB 服务...$(RESET)"
	@docker compose up -d $(MONGO_SERVICE)
	@echo "$(GREEN)✅ MongoDB 服务启动完成$(RESET)"

.PHONY: kafka-up
kafka-up: check-env ## 启动 Kafka 服务
	@echo "$(BLUE)启动 Kafka 服务...$(RESET)"
	@docker compose up -d $(KAFKA_SERVICE)
	@echo "$(GREEN)✅ Kafka 服务启动完成$(RESET)"

.PHONY: apps-up
apps-up: check-env ## 启动业务应用 (需要业务项目独立部署)
	@echo "$(YELLOW)⚠️  业务应用应该通过各自项目独立部署$(RESET)"
	@echo "$(BLUE)infra 项目只管理基础设施服务$(RESET)"
	@echo "$(GREEN)✅ 基础设施已就绪，请在业务项目中执行部署$(RESET)"

.PHONY: infra-up
infra-up: check-env ## 启动基础设施服务
	@echo "$(BLUE)启动基础设施服务...$(RESET)"
	@docker compose up -d $(MYSQL_SERVICE) $(REDIS_SERVICE) $(MONGO_SERVICE) $(KAFKA_SERVICE)
	@echo "$(GREEN)✅ 基础设施服务启动完成$(RESET)"

.PHONY: staged-up
staged-up: infra-up nginx-up ## 分阶段启动基础设施服务
	@echo "$(GREEN)✅ 基础设施按阶段启动完成$(RESET)"
	@echo "$(YELLOW)📋 下一步: 在各业务项目中部署应用服务$(RESET)"
	@$(MAKE) info

.PHONY: mongo-logs
mongo-logs: ## 查看 MongoDB 日志
	@docker compose logs -f $(MONGO_SERVICE)

.PHONY: kafka-logs
kafka-logs: ## 查看 Kafka 日志  
	@docker compose logs -f $(KAFKA_SERVICE)

.PHONY: app-logs
app-logs: ## 业务应用日志请在各业务项目中查看
	@echo "$(YELLOW)⚠️  业务应用日志请在各自项目中查看$(RESET)"
	@echo "$(BLUE)建议命令:$(RESET)"
	@echo "  cd ../miniblog && docker compose logs -f"
	@echo "  cd ../qs-system && docker compose logs -f"

.PHONY: mongo-shell
mongo-shell: ## 连接到 MongoDB 命令行
	@echo "$(BLUE)连接到 MongoDB...$(RESET)"
	@docker compose exec $(MONGO_SERVICE) mongosh

.PHONY: kafka-topics
kafka-topics: ## 列出 Kafka 主题
	@echo "$(BLUE)Kafka 主题列表:$(RESET)"
	@docker compose exec $(KAFKA_SERVICE) kafka-topics.sh --bootstrap-server localhost:9092 --list

.PHONY: resource-monitor
resource-monitor: ## 监控资源使用情况
	@echo "$(BLUE)资源监控:$(RESET)"
	@docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}"

.PHONY: health-check-all
health-check-all: ## 完整健康检查 (包含跨节点连通性)
	@echo "$(BLUE)完整系统健康检查 (节点: $(NODE_ROLE))...$(RESET)"
	@if [ "$(NODE_ROLE)" = "web" ]; then \
		$(MAKE) health-check-node-a; \
	elif [ "$(NODE_ROLE)" = "compute" ]; then \
		$(MAKE) health-check-node-b; \
	else \
		$(MAKE) health-check-single; \
	fi

.PHONY: health-check-node-a
health-check-node-a: ## 节点 A 健康检查
	@echo "$(BLUE)🅰️ 节点 A 健康检查...$(RESET)"
	@echo "Nginx: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "DOWN")"
	@echo "MySQL: $(shell docker exec -T mysql mysqladmin ping -uroot --password=$${MYSQL_ROOT_PASSWORD} --silent 2>/dev/null && echo "UP" || echo "DOWN")"
	@echo "Redis: $(shell docker exec -T redis redis-cli ping 2>/dev/null || echo "DOWN")"
	@echo "MongoDB: $(shell docker exec -T mongo mongosh --quiet --eval "db.runCommand({ ping: 1 }).ok" 2>/dev/null || echo "DOWN")"
	@echo "MiniBlog: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost/blog/health 2>/dev/null || echo "DOWN")"
	@echo "QS-API: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost/qs/api/health 2>/dev/null || echo "DOWN")"
	@echo "QS-Collection: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost/qs/collect/health 2>/dev/null || echo "DOWN")"
	@echo "Jenkins: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/login 2>/dev/null || echo "DOWN")"
	@echo ""
	@echo "$(YELLOW)🔗 跨节点连通性测试:$(RESET)"
	@if [ -n "$${NODE_B_IP}" ]; then \
		echo "节点B Kafka: $$(nc -z $${NODE_B_IP} 9092 && echo "UP" || echo "DOWN")"; \
		echo "节点B QS-Eval: $$(curl -s -o /dev/null -w "%{http_code}" http://$${NODE_B_IP}:8080/health 2>/dev/null || echo "DOWN")"; \
	fi

.PHONY: health-check-node-b
health-check-node-b: ## 节点 B 健康检查
	@echo "$(BLUE)🅱️ 节点 B 健康检查...$(RESET)"
	@echo "Kafka: $(shell docker exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1 && echo "UP" || echo "DOWN")"
	@echo "QS-Evaluation: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null || echo "DOWN")"
	@echo ""
	@echo "$(YELLOW)🔗 跨节点连通性测试:$(RESET)"
	@if [ -n "$${NODE_A_IP}" ]; then \
		echo "节点A MySQL: $$(nc -z $${NODE_A_IP} 3306 && echo "UP" || echo "DOWN")"; \
		echo "节点A Redis: $$(nc -z $${NODE_A_IP} 6379 && echo "UP" || echo "DOWN")"; \
		echo "节点A MongoDB: $$(nc -z $${NODE_A_IP} 27017 && echo "UP" || echo "DOWN")"; \
	fi

.PHONY: health-check-single
health-check-single: ## 单机健康检查 (向后兼容)
	@echo "$(BLUE)单机模式健康检查...$(RESET)"
	@echo "Nginx: $(shell curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "DOWN")"
	@echo "MySQL: $(shell docker compose exec -T $(MYSQL_SERVICE) mysqladmin ping -uroot --password=$${MYSQL_ROOT_PASSWORD} --silent 2>/dev/null && echo "UP" || echo "DOWN")"
	@echo "Redis: $(shell docker compose exec -T $(REDIS_SERVICE) redis-cli ping 2>/dev/null || echo "DOWN")"
	@echo "MongoDB: $(shell docker compose exec -T $(MONGO_SERVICE) mongosh --quiet --eval "db.runCommand({ ping: 1 }).ok" 2>/dev/null || echo "DOWN")"
	@echo "Kafka: $(shell docker compose exec -T $(KAFKA_SERVICE) kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1 && echo "UP" || echo "DOWN")"

# ==============================================================================
# 组件管理命令
# ==============================================================================
.PHONY: deploy-a
deploy-a: ## 部署节点 A (使用自动化脚本)
	@./scripts/deploy_a.sh

.PHONY: deploy-b
deploy-b: ## 部署节点 B (使用自动化脚本)
	@./scripts/deploy_b.sh

.PHONY: config-validate
config-validate: ## 验证 Docker Compose 配置
	@echo "$(BLUE)验证节点 A 配置...$(RESET)"
	@$(NODE_A_CMD) config > /dev/null && echo "$(GREEN)✅ 节点 A 配置正确$(RESET)" || echo "$(RED)❌ 节点 A 配置错误$(RESET)"
	@echo "$(BLUE)验证节点 B 配置...$(RESET)"
	@$(NODE_B_CMD) config > /dev/null && echo "$(GREEN)✅ 节点 B 配置正确$(RESET)" || echo "$(RED)❌ 节点 B 配置错误$(RESET)"

.PHONY: config-show
config-show: ## 显示合成后的配置 (NODE=a|b)
	@if [ "$(NODE)" = "a" ]; then \
		echo "$(BLUE)节点 A 配置:$(RESET)"; \
		$(NODE_A_CMD) config; \
	elif [ "$(NODE)" = "b" ]; then \
		echo "$(BLUE)节点 B 配置:$(RESET)"; \
		$(NODE_B_CMD) config; \
	else \
		echo "$(YELLOW)用法: make config-show NODE=a 或 make config-show NODE=b$(RESET)"; \
	fi

.PHONY: ssl-setup
ssl-setup: ## 设置 SSL 证书 (DOMAIN=example.com)
	@if [ -z "$(DOMAIN)" ]; then \
		echo "$(RED)❌ 请指定域名: make ssl-setup DOMAIN=example.com$(RESET)"; \
		exit 1; \
	fi
	@mkdir -p components/nginx/ssl/$(DOMAIN)
	@echo "$(BLUE)SSL 证书目录已创建: components/nginx/ssl/$(DOMAIN)$(RESET)"
	@echo "$(YELLOW)请将证书文件放入此目录:$(RESET)"
	@echo "  fullchain.pem - 完整证书链"
	@echo "  privkey.pem   - 私钥文件"

.PHONY: backup-config
backup-config: ## 备份配置文件
	@echo "$(BLUE)备份配置文件...$(RESET)"
	@tar -czf "config-backup-$(shell date +%Y%m%d_%H%M%S).tar.gz" \
		components/ compose/ scripts/ Makefile .gitignore
	@echo "$(GREEN)✅ 配置文件备份完成$(RESET)"

.PHONY: dev-start
dev-start: ## 启动开发环境 (NODE=a|b SERVICE=service_name)
	@if [ -z "$(NODE)" ]; then \
		echo "$(RED)❌ 请指定节点: make dev-start NODE=a SERVICE=nginx$(RESET)"; \
		exit 1; \
	fi
	@if [ -z "$(SERVICE)" ]; then \
		echo "$(RED)❌ 请指定服务: make dev-start NODE=a SERVICE=nginx$(RESET)"; \
		exit 1; \
	fi
	@if [ "$(NODE)" = "a" ]; then \
		$(NODE_A_CMD) up -d $(SERVICE); \
	elif [ "$(NODE)" = "b" ]; then \
		$(NODE_B_CMD) up -d $(SERVICE); \
	else \
		echo "$(RED)❌ 无效的节点类型: $(NODE)$(RESET)"; \
	fi

.PHONY: dev-logs
dev-logs: ## 查看开发服务日志 (NODE=a|b SERVICE=service_name)
	@if [ -z "$(NODE)" ] || [ -z "$(SERVICE)" ]; then \
		echo "$(YELLOW)用法: make dev-logs NODE=a SERVICE=nginx$(RESET)"; \
		exit 1; \
	fi
	@if [ "$(NODE)" = "a" ]; then \
		$(NODE_A_CMD) logs -f $(SERVICE); \
	elif [ "$(NODE)" = "b" ]; then \
		$(NODE_B_CMD) logs -f $(SERVICE); \
	fi

.PHONY: dev-shell
dev-shell: ## 进入服务容器 (NODE=a|b SERVICE=service_name)
	@if [ -z "$(NODE)" ] || [ -z "$(SERVICE)" ]; then \
		echo "$(YELLOW)用法: make dev-shell NODE=a SERVICE=nginx$(RESET)"; \
		exit 1; \
	fi
	@if [ "$(NODE)" = "a" ]; then \
		$(NODE_A_CMD) exec $(SERVICE) /bin/bash || $(NODE_A_CMD) exec $(SERVICE) /bin/sh; \
	elif [ "$(NODE)" = "b" ]; then \
		$(NODE_B_CMD) exec $(SERVICE) /bin/bash || $(NODE_B_CMD) exec $(SERVICE) /bin/sh; \
	fi

.PHONY: network-test
network-test: ## 测试服务间网络连通性
	@echo "$(BLUE)测试服务间连通性...$(RESET)"
	@if docker network ls | grep -q "infra_default"; then \
		echo "$(GREEN)✅ Docker 网络 'infra_default' 存在$(RESET)"; \
		docker network inspect infra_default --format "{{range .Containers}}{{.Name}}: {{.IPv4Address}}{{println}}{{end}}"; \
	else \
		echo "$(RED)❌ Docker 网络 'infra_default' 不存在$(RESET)"; \
	fi

# ==============================================================================
# 默认目标
# ==============================================================================
.DEFAULT_GOAL := help
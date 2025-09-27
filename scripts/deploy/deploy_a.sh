#!/bin/bash
# 节点 A 部署脚本 - Web/事务处理侧
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}🅰️  节点 A 部署脚本 - Web/事务处理侧${NC}"
echo "========================================"

# 检查环境文件
ENV_FILE="compose/env/prod/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ 环境配置文件不存在: $ENV_FILE${NC}"
    echo -e "${YELLOW}请复制并配置环境文件:${NC}"
    echo "  cp compose/env/prod/.env.example $ENV_FILE"
    echo "  vim $ENV_FILE"
    exit 1
fi

# 检查必要的目录
echo -e "${BLUE}📁 检查数据目录...${NC}"
sudo mkdir -p /data/{mysql,redis,mongo,jenkins,logs/{nginx,mysql,redis,mongo,jenkins}}
sudo chown -R $USER:$USER /data

# 检查 SSL 证书目录
if [ ! -d "components/nginx/ssl" ]; then
    mkdir -p components/nginx/ssl
    echo -e "${YELLOW}⚠️  SSL 证书目录已创建: components/nginx/ssl${NC}"
    echo -e "${YELLOW}   请将证书文件放入此目录${NC}"
fi

# 检查 Docker 和 Docker Compose
echo -e "${BLUE}🐳 检查 Docker 环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose 未安装${NC}"
    exit 1
fi

# 创建 Docker 网络
echo -e "${BLUE}🌐 创建 Docker 网络...${NC}"
docker network create infra-frontend 2>/dev/null || echo "网络 infra-frontend 已存在"
docker network create infra-backend 2>/dev/null || echo "网络 infra-backend 已存在"

# 验证配置文件
echo -e "${BLUE}🔧 验证配置文件...${NC}"

# 检查 Nginx 配置
if [ -f "components/nginx/nginx.conf" ]; then
    echo "✅ Nginx 配置文件存在"
else
    echo -e "${RED}❌ Nginx 配置文件缺失: components/nginx/nginx.conf${NC}"
    exit 1
fi

# 构建 Docker Compose 命令
COMPOSE_CMD="docker compose"
COMPOSE_CMD+=" --env-file $ENV_FILE"
COMPOSE_CMD+=" -f compose/base/docker-compose.yml"
COMPOSE_CMD+=" -f compose/nodes/a.override.yml"
COMPOSE_CMD+=" -f components/nginx/override.yml"
COMPOSE_CMD+=" -f components/mysql/override.yml"
COMPOSE_CMD+=" -f components/redis/override.yml"
COMPOSE_CMD+=" -f components/mongo/override.yml"

# 验证配置合成
echo -e "${BLUE}🔍 验证配置合成...${NC}"
if ! $COMPOSE_CMD config > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker Compose 配置验证失败${NC}"
    echo -e "${YELLOW}详细错误信息:${NC}"
    $COMPOSE_CMD config
    exit 1
fi
echo "✅ 配置验证通过"

# 启动服务
echo -e "${BLUE}🚀 启动节点 A 服务...${NC}"
echo -e "${YELLOW}服务列表:${NC}"
echo "  🌐 Nginx (80/443)"
echo "  🗄️ MySQL (3306)"
echo "  💾 Redis (6379)"  
echo "  🍃 MongoDB (27017)"
echo "  📝 MiniBlog"
echo "  📊 QS-API"
echo "  📈 QS-Collection"
echo "  🔧 Jenkins (8080)"
echo ""

read -p "确认启动节点 A 服务? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}启动中...${NC}"
    
    # 分阶段启动
    echo -e "${YELLOW}阶段 1: 启动基础设施服务${NC}"
    $COMPOSE_CMD up -d mysql redis mongo
    
    echo -e "${YELLOW}等待数据库启动...${NC}"
    sleep 15
    
    echo -e "${YELLOW}阶段 2: 启动业务应用${NC}"
    $COMPOSE_CMD up -d miniblog qs-api qs-collection jenkins
    
    echo -e "${YELLOW}阶段 3: 启动前端代理${NC}"
    $COMPOSE_CMD up -d nginx
    
    echo -e "${GREEN}✅ 节点 A 部署完成！${NC}"
else
    echo -e "${YELLOW}部署已取消${NC}"
    exit 0
fi

# 健康检查
echo -e "${BLUE}🩺 服务健康检查...${NC}"
sleep 5

# 检查容器状态
echo -e "${YELLOW}容器状态:${NC}"
$COMPOSE_CMD ps

# 基础服务健康检查
echo -e "${YELLOW}服务健康状态:${NC}"

# Nginx
NGINX_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "DOWN")
echo "  Nginx: $NGINX_STATUS"

# MySQL  
MYSQL_STATUS=$(docker exec mysql mysqladmin ping -uroot --password="${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null && echo "UP" || echo "DOWN")
echo "  MySQL: $MYSQL_STATUS"

# Redis
REDIS_STATUS=$(docker exec redis redis-cli ping 2>/dev/null || echo "DOWN")
echo "  Redis: $REDIS_STATUS"

# MongoDB
MONGO_STATUS=$(docker exec mongo mongosh --quiet --eval "db.runCommand({ping: 1}).ok" 2>/dev/null || echo "DOWN")
echo "  MongoDB: $MONGO_STATUS"

echo ""
echo -e "${GREEN}🎉 节点 A 部署完成！${NC}"
echo ""
echo -e "${YELLOW}📋 访问地址:${NC}"
echo "  系统首页: http://localhost/"
echo "  Jenkins:  http://localhost:8080"
echo "  健康检查: http://localhost/health"
echo ""
echo -e "${YELLOW}🔧 管理命令:${NC}"
echo "  查看状态: make status"
echo "  查看日志: make logs"  
echo "  健康检查: make health-check-node-a"
echo ""
echo -e "${YELLOW}⚠️  下一步:${NC}"
echo "  1. 在节点 B 上运行 ./scripts/deploy_b.sh"
echo "  2. 配置 SSL 证书 (生产环境)"
echo "  3. 配置域名解析指向节点 A"
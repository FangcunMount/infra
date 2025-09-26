#!/bin/bash
# 节点 B 部署脚本 - 计算/流处理侧
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

echo -e "${BLUE}🅱️  节点 B 部署脚本 - 计算/流处理侧${NC}"
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
sudo mkdir -p /data/{kafka,logs/{kafka,qs}}
sudo chown -R $USER:$USER /data

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
docker network create infra-backend 2>/dev/null || echo "网络 infra-backend 已存在"

# 检查与节点 A 的连通性
echo -e "${BLUE}🔗 检查节点间连通性...${NC}"
NODE_A_IP=$(grep NODE_A_IP $ENV_FILE | cut -d'=' -f2)
if [ -z "$NODE_A_IP" ]; then
    echo -e "${RED}❌ NODE_A_IP 未配置${NC}"
    exit 1
fi

echo "检查到节点 A 的连接: $NODE_A_IP"
if ! ping -c 1 "$NODE_A_IP" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  无法 ping 通节点 A ($NODE_A_IP)${NC}"
    echo -e "${YELLOW}   请检查网络配置${NC}"
fi

# 构建 Docker Compose 命令
COMPOSE_CMD="docker compose"
COMPOSE_CMD+=" --env-file $ENV_FILE"
COMPOSE_CMD+=" -f compose/base/docker-compose.yml"
COMPOSE_CMD+=" -f compose/nodes/b.override.yml"
COMPOSE_CMD+=" -f components/kafka/override.yml"

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
echo -e "${BLUE}🚀 启动节点 B 服务...${NC}"
echo -e "${YELLOW}服务列表:${NC}"
echo "  ⚡ Kafka (9092)"
echo "  🔍 QS-Evaluation (8080)"
echo ""

read -p "确认启动节点 B 服务? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}启动中...${NC}"
    
    # 分阶段启动
    echo -e "${YELLOW}阶段 1: 启动 Kafka${NC}"
    $COMPOSE_CMD up -d kafka
    
    echo -e "${YELLOW}等待 Kafka 启动...${NC}"
    sleep 20
    
    echo -e "${YELLOW}阶段 2: 启动 QS-Evaluation${NC}"
    $COMPOSE_CMD up -d qs-evaluation
    
    echo -e "${GREEN}✅ 节点 B 部署完成！${NC}"
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

# Kafka
KAFKA_STATUS=$(docker exec kafka /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1 && echo "UP" || echo "DOWN")
echo "  Kafka: $KAFKA_STATUS"

# QS-Evaluation
QS_EVAL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null || echo "DOWN")
echo "  QS-Evaluation: $QS_EVAL_STATUS"

# 跨节点连通性测试
echo -e "${YELLOW}跨节点连通性测试:${NC}"
if command -v nc &> /dev/null; then
    MYSQL_CONN=$(nc -z "$NODE_A_IP" 3306 && echo "UP" || echo "DOWN")
    echo "  节点A MySQL: $MYSQL_CONN"
    
    REDIS_CONN=$(nc -z "$NODE_A_IP" 6379 && echo "UP" || echo "DOWN") 
    echo "  节点A Redis: $REDIS_CONN"
    
    MONGO_CONN=$(nc -z "$NODE_A_IP" 27017 && echo "UP" || echo "DOWN")
    echo "  节点A MongoDB: $MONGO_CONN"
else
    echo "  nc 命令未安装，跳过端口测试"
fi

echo ""
echo -e "${GREEN}🎉 节点 B 部署完成！${NC}"
echo ""
echo -e "${YELLOW}📋 服务信息:${NC}"
echo "  QS-Evaluation API: http://localhost:8080"
echo "  Kafka Broker: localhost:9092"
echo ""
echo -e "${YELLOW}🔧 管理命令:${NC}"
echo "  查看状态: make status"
echo "  查看日志: make logs"
echo "  健康检查: make health-check-node-b"
echo "  Kafka 主题: make kafka-topics"
echo ""
echo -e "${YELLOW}✅ 部署完成提醒:${NC}"
echo "  1. 节点 A 可通过 /qs/eval/ 路径访问本节点服务"
echo "  2. 检查防火墙设置，确保端口 9092 和 8080 对节点 A 开放"
echo "  3. 应用程序需要使用正确的节点 B IP 连接 Kafka"
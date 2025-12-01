#!/bin/bash
# NSQ 测试脚本 - 测试 NSQ 服务是否正常工作

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🧪 NSQ 服务测试${NC}"
echo "================================"

# 检查环境
echo -e "${BLUE}检查 NSQ 服务状态...${NC}"

# 1. 检查容器是否运行
echo -e "\n${YELLOW}1. 检查容器状态${NC}"
for service in nsqlookupd nsqd nsqadmin; do
    if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
        echo -e "  ✅ ${service} 运行中"
    else
        echo -e "  ${RED}❌ ${service} 未运行${NC}"
        exit 1
    fi
done

# 2. 健康检查
echo -e "\n${YELLOW}2. 健康检查${NC}"
NSQLOOKUPD_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4161/ping 2>/dev/null || echo "000")
NSQD_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4151/ping 2>/dev/null || echo "000")
NSQADMIN_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4171/ping 2>/dev/null || echo "000")

if [ "$NSQLOOKUPD_HEALTH" == "200" ]; then
    echo -e "  ✅ NSQLookupd 健康检查通过"
else
    echo -e "  ${RED}❌ NSQLookupd 健康检查失败 (HTTP $NSQLOOKUPD_HEALTH)${NC}"
fi

if [ "$NSQD_HEALTH" == "200" ]; then
    echo -e "  ✅ NSQd 健康检查通过"
else
    echo -e "  ${RED}❌ NSQd 健康检查失败 (HTTP $NSQD_HEALTH)${NC}"
fi

if [ "$NSQADMIN_HEALTH" == "200" ]; then
    echo -e "  ✅ NSQAdmin 健康检查通过"
else
    echo -e "  ${RED}❌ NSQAdmin 健康检查失败 (HTTP $NSQADMIN_HEALTH)${NC}"
fi

# 3. 检查 nsqd 是否注册到 nsqlookupd
echo -e "\n${YELLOW}3. 检查服务发现${NC}"
NODES=$(curl -s http://localhost:4161/nodes 2>/dev/null || echo "{}")
if echo "$NODES" | grep -q "producers"; then
    echo -e "  ✅ NSQd 已注册到 NSQLookupd"
    if command -v jq &> /dev/null; then
        echo "$NODES" | jq '.producers[] | {broadcast_address, tcp_port, http_port}' 2>/dev/null || true
    fi
else
    echo -e "  ${YELLOW}⚠️  NSQd 尚未注册到 NSQLookupd（可能正在初始化）${NC}"
fi

# 4. 功能测试
echo -e "\n${YELLOW}4. 功能测试${NC}"
TEST_TOPIC="test_topic_$(date +%s)"

# 创建主题并发送测试消息
echo -e "  创建测试主题: ${TEST_TOPIC}"
PUBLISH_RESULT=$(curl -s -d 'Hello NSQ!' "http://localhost:4151/pub?topic=${TEST_TOPIC}" 2>/dev/null || echo "FAILED")

if echo "$PUBLISH_RESULT" | grep -q "OK"; then
    echo -e "  ✅ 消息发布成功"
    
    # 等待一下，让消息被处理
    sleep 2
    
    # 检查主题是否创建
    TOPICS=$(curl -s http://localhost:4161/topics 2>/dev/null || echo "{}")
    if echo "$TOPICS" | grep -q "${TEST_TOPIC}"; then
        echo -e "  ✅ 主题创建成功"
        
        # 查看主题详情
        if command -v jq &> /dev/null; then
            STATS=$(curl -s http://localhost:4151/stats?format=json 2>/dev/null)
            echo -e "  📊 主题统计:"
            echo "$STATS" | jq ".topics[] | select(.topic_name == \"${TEST_TOPIC}\") | {topic_name, message_count, depth}" 2>/dev/null || true
        fi
        
        # 清理测试主题
        echo -e "  🧹 清理测试主题..."
        curl -s -X POST "http://localhost:4151/topic/delete?topic=${TEST_TOPIC}" >/dev/null 2>&1 || true
    else
        echo -e "  ${YELLOW}⚠️  主题未在 NSQLookupd 中找到${NC}"
    fi
else
    echo -e "  ${RED}❌ 消息发布失败${NC}"
    exit 1
fi

# 5. 显示服务信息
echo -e "\n${YELLOW}5. 服务信息${NC}"
echo -e "  NSQd TCP:            localhost:4150"
echo -e "  NSQd HTTP:           http://localhost:4151"
echo -e "  NSQLookupd TCP:      localhost:4160"
echo -e "  NSQLookupd HTTP:     http://localhost:4161"
echo -e "  NSQAdmin Web UI:     http://localhost:4171"

# 6. 显示当前主题
echo -e "\n${YELLOW}6. 当前主题列表${NC}"
CURRENT_TOPICS=$(curl -s http://localhost:4161/topics 2>/dev/null || echo "{}")
if command -v jq &> /dev/null; then
    if echo "$CURRENT_TOPICS" | jq -e '.topics | length > 0' >/dev/null 2>&1; then
        echo "$CURRENT_TOPICS" | jq -r '.topics[]' | while read topic; do
            echo -e "  📬 $topic"
        done
    else
        echo -e "  ${YELLOW}暂无主题${NC}"
    fi
else
    echo "$CURRENT_TOPICS"
fi

echo -e "\n${GREEN}✅ NSQ 测试完成！${NC}"
echo -e "\n${BLUE}💡 提示:${NC}"
echo -e "  查看 Web 管理界面: http://localhost:4171"
echo -e "  查看所有主题: curl http://localhost:4161/topics"
echo -e "  发送测试消息: curl -d 'test message' 'http://localhost:4151/pub?topic=test'"
echo -e "  查看统计信息: curl http://localhost:4151/stats?format=json | jq '.'"

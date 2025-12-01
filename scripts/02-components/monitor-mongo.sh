#!/usr/bin/env bash
#
# MongoDB 监控指标采集脚本
# 用途：采集关键性能指标，用于监控告警
#
# 用法：
#   bash scripts/components/monitor-mongo.sh
#   配合 watch: watch -n 5 bash scripts/components/monitor-mongo.sh
#

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 根据 ENV 参数选择环境配置文件
# ENV=prod (默认) -> serverA.env (MongoDB 部署在 serverA)
# ENV=dev -> dev/.env
ENV="${ENV:-prod}"
if [[ "$ENV" == "prod" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/prod/serverA.env"
elif [[ "$ENV" == "dev" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/dev/.env"
else
    ENV_FILE="$INFRA_ROOT/compose/env/$ENV/.env"
fi

# 告警阈值
CACHE_USAGE_THRESHOLD=85      # 缓存使用率告警阈值 (%)
PAGE_FAULT_THRESHOLD=100      # Page fault 告警阈值（每秒增量）
QUEUE_THRESHOLD=10            # 队列等待数告警阈值
DIRTY_BYTES_THRESHOLD_MB=400  # 脏数据阈值 (MB)

# 状态文件（用于增量计算）
STATE_FILE="/tmp/mongo-monitor-state.txt"

# 加载环境变量
if [[ -f "$ENV_FILE" ]]; then
    source "$ENV_FILE"
fi

# 检查容器状态
if ! docker ps | grep -q "mongo"; then
    echo -e "${RED}❌ MongoDB 容器未运行${NC}"
    exit 1
fi

echo "=========================================="
echo -e "${CYAN}MongoDB 性能监控 - $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo "=========================================="

# 获取服务器状态
STATS=$(docker exec mongo mongosh \
    -u "${MONGO_INITDB_ROOT_USERNAME:-root}" \
    -p "${MONGO_INITDB_ROOT_PASSWORD}" \
    --authenticationDatabase admin \
    --quiet \
    --eval "
        var status = db.serverStatus();
        var stats = {
            // 基本信息
            version: status.version,
            uptime: status.uptimeEstimate,
            
            // 连接信息
            currentConn: status.connections.current,
            availableConn: status.connections.available,
            totalCreated: status.connections.totalCreated,
            
            // WiredTiger 缓存
            cacheSize: status.wiredTiger.cache['bytes currently in the cache'],
            dirtyBytes: status.wiredTiger.cache['tracked dirty bytes in the cache'],
            maxCache: status.wiredTiger.cache['maximum bytes configured'],
            pagesRead: status.wiredTiger.cache['pages read into cache'],
            pagesWritten: status.wiredTiger.cache['pages written from cache'],
            
            // 操作计数
            insertOps: status.opcounters.insert,
            queryOps: status.opcounters.query,
            updateOps: status.opcounters.update,
            deleteOps: status.opcounters.delete,
            commandOps: status.opcounters.command,
            
            // 全局锁
            lockTime: status.globalLock.totalTime,
            lockCurrentQueue: status.globalLock.currentQueue.total,
            lockCurrentQueueReaders: status.globalLock.currentQueue.readers,
            lockCurrentQueueWriters: status.globalLock.currentQueue.writers,
            
            // 内存
            residentMem: status.mem.resident,
            virtualMem: status.mem.virtual,
            
            // Page Faults（累计值，需计算增量）
            pageFaults: status.extra_info.page_faults,
            
            // WiredTiger Tickets（并发控制）
            ticketsAvailableReads: status.wiredTiger.concurrentTransactions.read.available,
            ticketsAvailableWrites: status.wiredTiger.concurrentTransactions.write.available
        };
        printjson(stats);
    " 2>/dev/null)

if [[ -z "$STATS" ]]; then
    echo -e "${RED}❌ 无法获取 MongoDB 状态${NC}"
    exit 1
fi

# 解析 JSON（使用 Python 或 jq，这里用简单的 grep）
parse_stat() {
    echo "$STATS" | grep -oP "\"$1\":\s*\K[0-9.]+" | head -n 1
}

parse_str() {
    echo "$STATS" | grep -oP "\"$1\":\s*\"\K[^\"]+" | head -n 1
}

# 提取指标
VERSION=$(parse_str "version")
UPTIME=$(parse_stat "uptime")
CURRENT_CONN=$(parse_stat "currentConn")
AVAILABLE_CONN=$(parse_stat "availableConn")
CACHE_SIZE=$(parse_stat "cacheSize")
DIRTY_BYTES=$(parse_stat "dirtyBytes")
MAX_CACHE=$(parse_stat "maxCache")
PAGES_READ=$(parse_stat "pagesRead")
PAGES_WRITTEN=$(parse_stat "pagesWritten")
INSERT_OPS=$(parse_stat "insertOps")
QUERY_OPS=$(parse_stat "queryOps")
UPDATE_OPS=$(parse_stat "updateOps")
DELETE_OPS=$(parse_stat "deleteOps")
COMMAND_OPS=$(parse_stat "commandOps")
LOCK_QUEUE=$(parse_stat "lockCurrentQueue")
LOCK_QUEUE_READERS=$(parse_stat "lockCurrentQueueReaders")
LOCK_QUEUE_WRITERS=$(parse_stat "lockCurrentQueueWriters")
RESIDENT_MEM=$(parse_stat "residentMem")
VIRTUAL_MEM=$(parse_stat "virtualMem")
PAGE_FAULTS=$(parse_stat "pageFaults")
TICKETS_READS=$(parse_stat "ticketsAvailableReads")
TICKETS_WRITES=$(parse_stat "ticketsAvailableWrites")

# 计算百分比
CACHE_USAGE_PCT=0
if [[ -n "$CACHE_SIZE" ]] && [[ -n "$MAX_CACHE" ]] && [[ "$MAX_CACHE" != "0" ]]; then
    CACHE_USAGE_PCT=$(echo "scale=1; $CACHE_SIZE / $MAX_CACHE * 100" | bc)
fi

CONN_USAGE_PCT=0
TOTAL_CONN=$((CURRENT_CONN + AVAILABLE_CONN))
if [[ "$TOTAL_CONN" -gt 0 ]]; then
    CONN_USAGE_PCT=$(echo "scale=1; $CURRENT_CONN / $TOTAL_CONN * 100" | bc)
fi

DIRTY_BYTES_MB=$(echo "scale=1; $DIRTY_BYTES / 1024 / 1024" | bc)
CACHE_SIZE_MB=$(echo "scale=1; $CACHE_SIZE / 1024 / 1024" | bc)
MAX_CACHE_MB=$(echo "scale=1; $MAX_CACHE / 1024 / 1024" | bc)

# 读取上次的状态（用于增量计算）
PREV_TIMESTAMP=0
PREV_PAGE_FAULTS=0
if [[ -f "$STATE_FILE" ]]; then
    source "$STATE_FILE"
fi

# 当前时间戳
CURRENT_TIMESTAMP=$(date +%s)

# 计算时间间隔
if [[ "$PREV_TIMESTAMP" -gt 0 ]]; then
    TIME_INTERVAL=$((CURRENT_TIMESTAMP - PREV_TIMESTAMP))
    if [[ "$TIME_INTERVAL" -gt 0 ]]; then
        # 计算 Page Faults 增量（每秒）
        PAGE_FAULTS_DELTA=$((PAGE_FAULTS - PREV_PAGE_FAULTS))
        PAGE_FAULTS_PER_SEC=$(echo "scale=2; $PAGE_FAULTS_DELTA / $TIME_INTERVAL" | bc)
    else
        PAGE_FAULTS_PER_SEC="0"
    fi
else
    # 首次运行，无增量数据
    PAGE_FAULTS_PER_SEC="N/A"
    TIME_INTERVAL=0
fi

# 保存当前状态供下次使用
cat > "$STATE_FILE" << EOF
PREV_TIMESTAMP=$CURRENT_TIMESTAMP
PREV_PAGE_FAULTS=$PAGE_FAULTS
EOF

# 显示指标
echo ""
echo -e "${BLUE}📊 基本信息${NC}"
echo "   版本:     $VERSION"
echo "   运行时间: $UPTIME 秒 ($(echo "scale=1; $UPTIME / 3600" | bc) 小时)"
echo ""

echo -e "${BLUE}🔌 连接状态${NC}"
printf "   当前连接: %s / %s " "$CURRENT_CONN" "$TOTAL_CONN"
if (( $(echo "$CONN_USAGE_PCT > 80" | bc -l) )); then
    echo -e "${RED}(${CONN_USAGE_PCT}% ⚠️  高负载)${NC}"
elif (( $(echo "$CONN_USAGE_PCT > 50" | bc -l) )); then
    echo -e "${YELLOW}(${CONN_USAGE_PCT}% 注意)${NC}"
else
    echo -e "${GREEN}(${CONN_USAGE_PCT}% ✓)${NC}"
fi
echo ""

echo -e "${BLUE}💾 WiredTiger 缓存${NC}"
printf "   缓存使用: %.1f MB / %.1f MB " "$CACHE_SIZE_MB" "$MAX_CACHE_MB"
if (( $(echo "$CACHE_USAGE_PCT > $CACHE_USAGE_THRESHOLD" | bc -l) )); then
    echo -e "${RED}(${CACHE_USAGE_PCT}% ⚠️  缓存压力)${NC}"
elif (( $(echo "$CACHE_USAGE_PCT > 70" | bc -l) )); then
    echo -e "${YELLOW}(${CACHE_USAGE_PCT}% 注意)${NC}"
else
    echo -e "${GREEN}(${CACHE_USAGE_PCT}% ✓)${NC}"
fi

printf "   脏数据:   %.1f MB " "$DIRTY_BYTES_MB"
if (( $(echo "$DIRTY_BYTES_MB > $DIRTY_BYTES_THRESHOLD_MB" | bc -l) )); then
    echo -e "${RED}(⚠️  高于阈值 ${DIRTY_BYTES_THRESHOLD_MB}MB)${NC}"
else
    echo -e "${GREEN}(✓)${NC}"
fi

echo "   读页面:   $PAGES_READ"
echo "   写页面:   $PAGES_WRITTEN"
echo ""

echo -e "${BLUE}📈 操作统计（累计）${NC}"
echo "   Insert:   $INSERT_OPS"
echo "   Query:    $QUERY_OPS"
echo "   Update:   $UPDATE_OPS"
echo "   Delete:   $DELETE_OPS"
echo "   Command:  $COMMAND_OPS"
echo ""

echo -e "${BLUE}🔒 锁与队列${NC}"
printf "   等待队列: %s (读: %s, 写: %s) " "$LOCK_QUEUE" "$LOCK_QUEUE_READERS" "$LOCK_QUEUE_WRITERS"
if [[ "$LOCK_QUEUE" -gt "$QUEUE_THRESHOLD" ]]; then
    echo -e "${RED}(⚠️  队列积压)${NC}"
else
    echo -e "${GREEN}(✓)${NC}"
fi

echo -e "${BLUE}🎫 WiredTiger Tickets（并发控制）${NC}"
printf "   可用读 Tickets: %s " "$TICKETS_READS"
if [[ "$TICKETS_READS" -lt 20 ]]; then
    echo -e "${RED}(⚠️  读并发受限)${NC}"
elif [[ "$TICKETS_READS" -lt 64 ]]; then
    echo -e "${YELLOW}(注意)${NC}"
else
    echo -e "${GREEN}(✓)${NC}"
fi

printf "   可用写 Tickets: %s " "$TICKETS_WRITES"
if [[ "$TICKETS_WRITES" -lt 20 ]]; then
    echo -e "${RED}(⚠️  写并发受限)${NC}"
elif [[ "$TICKETS_WRITES" -lt 64 ]]; then
    echo -e "${YELLOW}(注意)${NC}"
else
    echo -e "${GREEN}(✓)${NC}"
fi
echo ""

echo -e "${BLUE}🧠 内存使用${NC}"
echo "   常驻内存: ${RESIDENT_MEM} MB"
echo "   虚拟内存: ${VIRTUAL_MEM} MB"
echo ""

echo -e "${BLUE}📄 Page Faults${NC}"
echo "   累计缺页:     $PAGE_FAULTS"
if [[ "$PAGE_FAULTS_PER_SEC" != "N/A" ]]; then
    printf "   增量速率:     %.2f/秒 " "$PAGE_FAULTS_PER_SEC"
    if (( $(echo "$PAGE_FAULTS_PER_SEC > $PAGE_FAULT_THRESHOLD" | bc -l) )); then
        echo -e "${RED}(⚠️  缺页速率过高，缓存不足)${NC}"
    elif (( $(echo "$PAGE_FAULTS_PER_SEC > 50" | bc -l) )); then
        echo -e "${YELLOW}(注意：考虑增加缓存)${NC}"
    else
        echo -e "${GREEN}(✓)${NC}"
    fi
    echo "   采样间隔:     ${TIME_INTERVAL}秒"
else
    echo "   增量速率:     N/A (首次运行，等待下次采样)"
fi
echo ""

# 告警汇总
ALERTS=()
if (( $(echo "$CACHE_USAGE_PCT > $CACHE_USAGE_THRESHOLD" | bc -l) )); then
    ALERTS+=("缓存使用率高 (${CACHE_USAGE_PCT}%)")
fi
if (( $(echo "$DIRTY_BYTES_MB > $DIRTY_BYTES_THRESHOLD_MB" | bc -l) )); then
    ALERTS+=("脏数据过多 (${DIRTY_BYTES_MB}MB)")
fi
if [[ "$LOCK_QUEUE" -gt "$QUEUE_THRESHOLD" ]]; then
    ALERTS+=("锁队列积压 ($LOCK_QUEUE, 读:$LOCK_QUEUE_READERS, 写:$LOCK_QUEUE_WRITERS)")
fi
if (( $(echo "$CONN_USAGE_PCT > 80" | bc -l) )); then
    ALERTS+=("连接数高 (${CONN_USAGE_PCT}%)")
fi
if [[ "$PAGE_FAULTS_PER_SEC" != "N/A" ]] && (( $(echo "$PAGE_FAULTS_PER_SEC > $PAGE_FAULT_THRESHOLD" | bc -l) )); then
    ALERTS+=("缺页速率过高 (${PAGE_FAULTS_PER_SEC}/秒)")
fi
if [[ "$TICKETS_READS" -lt 20 ]] || [[ "$TICKETS_WRITES" -lt 20 ]]; then
    ALERTS+=("WiredTiger Tickets 耗尽 (读:$TICKETS_READS, 写:$TICKETS_WRITES)")
fi

if [[ ${#ALERTS[@]} -gt 0 ]]; then
    echo -e "${RED}⚠️  告警：${NC}"
    for alert in "${ALERTS[@]}"; do
        echo -e "   ${RED}• $alert${NC}"
    done
    echo ""
fi

echo "=========================================="
echo -e "${GREEN}✅ 监控完成${NC}"
echo "=========================================="
echo ""
echo "💡 建议："
echo "   • 使用 watch 持续监控: watch -n 5 $0"
echo "   • 配置监控系统采集这些指标（Prometheus + Grafana）"
echo "   • 告警阈值可在脚本开头调整"
echo ""

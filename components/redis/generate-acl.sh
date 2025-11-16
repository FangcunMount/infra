#!/bin/bash
# 生成 Redis ACL 配置文件
# 用法: ./generate-acl.sh [env_file]

set -e

# 项目根目录中的 compose/env/<env>/.env
ENV_FILE="${1:-../../compose/env/prod/.env}"

# 确保脚本始终以脚本所在目录为基准，避免在不同 cwd 下生成到错误位置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACL_FILE="${SCRIPT_DIR}/users.acl"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 错误: 环境变量文件不存在: $ENV_FILE"
    exit 1
fi

# 加载环境变量（只导入 REDIS 相关的变量）
echo "📄 加载环境变量: $ENV_FILE"
export $(grep "^REDIS.*PASSWORD=" "$ENV_FILE" | xargs)

# 设置默认值（如果环境变量未设置）
REDIS_ADMIN_PASSWORD="${REDIS_ADMIN_PASSWORD:-change_me_admin_pass}"
REDIS_APP_PASSWORD="${REDIS_APP_PASSWORD:-change_me_app_pass}"
REDIS_READONLY_PASSWORD="${REDIS_READONLY_PASSWORD:-change_me_readonly_pass}"
REDIS_CACHE_USER_PASSWORD="${REDIS_CACHE_USER_PASSWORD:-change_me_cache_pass}"
REDIS_MONITOR_PASSWORD="${REDIS_MONITOR_PASSWORD:-change_me_monitor_pass}"

# 生成 ACL 文件
echo "🔐 生成 Redis ACL 文件: $ACL_FILE"

cat > "$ACL_FILE" << EOF
user default off nopass ~* &* +@all
user admin on >${REDIS_ADMIN_PASSWORD} ~* &* +@all
user app on >${REDIS_APP_PASSWORD} ~* &* +@all -@dangerous -@admin -flushall -flushdb -keys -config -shutdown -bgsave -bgrewriteaof -save -debug -migrate -slaveof -replicaof
user readonly on >${REDIS_READONLY_PASSWORD} ~* &* +@read +@connection +ping +info +auth
user cache on >${REDIS_CACHE_USER_PASSWORD} ~* &* +@read +@write +@string +@hash +@list +@set +@sortedset +@connection +@transaction +del +expire +ttl +persist +unlink
user monitor on >${REDIS_MONITOR_PASSWORD} ~* &* +@connection +ping +info +client +cluster +slowlog +latency +memory +config|get +auth
EOF

# 设置文件权限
chmod 644 "$ACL_FILE"

echo "✅ ACL 文件生成成功！"
echo ""
echo "📋 用户列表:"
echo "  - default  : 已禁用"
echo "  - admin    : 完全权限"
echo "  - app      : 常规读写（排除危险命令）"
echo "  - readonly : 仅读取"
echo "  - cache    : 缓存场景（读写+过期）"
echo "  - monitor  : 监控查询"
echo ""
echo "⚠️  注意: 请勿将此文件提交到版本控制系统（已在 .gitignore 中）"

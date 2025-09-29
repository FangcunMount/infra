#!/usr/bin/env bash
# 交互式组件安装演示脚本

# 模拟测试交互式功能（演示用）
test_interactive_simulation() {
    echo "========================================"
    echo "🎬 交互式安装演示"
    echo "========================================"
    echo
    echo "当您运行以下命令时:"
    echo "  bash install-components.sh"
    echo "  # 或"
    echo "  bash install-components.sh --interactive"
    echo
    echo "将会看到如下交互界面:"
    echo
    
    cat << 'EOF'
========================================
🐳 Docker 组件交互式安装
========================================
当前配置:
  用户: www
  环境: prod
  预览模式: false
========================================

📋 可选组件列表:

  1. Nginx       - Web 服务器          [未选择]
  2. MySQL       - 关系型数据库        [未选择]
  3. Redis       - 内存缓存数据库      [未选择]
  4. MongoDB     - NoSQL 文档数据库    [未选择]
  5. Kafka       - 分布式消息队列      [未选择]

操作选项:
  a. 全选所有组件
  r. 推荐组合 (nginx + mysql + redis)
  c. 清空选择
  i. 显示组件详细信息
  s. 开始安装已选择的组件
  q. 退出

请选择组件编号或操作 (1-5/a/c/s/q): 
EOF

    echo
    echo "💡 使用说明:"
    echo "  • 输入数字 1-5 选择/取消选择组件"
    echo "  • 输入 'r' 选择推荐组合 (nginx + mysql + redis)"
    echo "  • 输入 'i' 查看详细的组件信息和推荐安装顺序"
    echo "  • 输入 's' 开始安装已选择的组件"
    echo "  • 输入 'q' 退出程序"
    echo
    echo "🎯 交互式优势:"
    echo "  ✅ 多选组件，灵活组合"
    echo "  ✅ 实时显示选择状态"
    echo "  ✅ 推荐组合快速选择"
    echo "  ✅ 详细组件信息查看"
    echo "  ✅ 批量安装和结果汇总"
    echo
}

# 显示所有可用的安装方式
show_all_install_methods() {
    echo "========================================"
    echo "📋 所有安装方式汇总"
    echo "========================================"
    echo
    echo "🚀 1. 交互式安装 (推荐)"
    echo "     bash install-components.sh"
    echo "     bash install-components.sh --interactive"
    echo
    echo "📦 2. 单组件安装"
    echo "     bash install-components.sh nginx"
    echo "     bash install-nginx.sh"
    echo "     bash install-mysql.sh"
    echo "     bash install-redis.sh"
    echo "     bash install-mongo.sh"
    echo "     bash install-kafka.sh"
    echo
    echo "🌟 3. 全量安装"
    echo "     bash install-components.sh all"
    echo "     bash install-all-components.sh"
    echo
    echo "🔧 4. 高级选项"
    echo "     bash install-components.sh nginx --user root"
    echo "     bash install-components.sh mysql --dry-run"
    echo "     bash install-components.sh redis --env dev"
    echo
    echo "💡 建议使用交互式安装，可以灵活选择组件组合！"
}

echo "========================================"
echo "🎯 Docker 组件安装方案总览"
echo "========================================"

test_interactive_simulation
echo
show_all_install_methods
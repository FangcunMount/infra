// MongoDB 初始化脚本
// 此脚本在容器首次启动时自动执行（仅执行一次）
// 用于创建业务数据库和用户

print('========================================');
print('MongoDB 初始化脚本开始执行');
print('========================================');

// 从环境变量读取配置
const dbName = process.env.MONGO_DATABASE || 'infrastructure_dev';
const appUser = process.env.MONGO_APP_USER || 'app_user';
const appPassword = process.env.MONGO_APP_PASSWORD || 'dev_app_pass_123';
const readonlyUser = process.env.MONGO_READONLY_USER || 'readonly_user';
const readonlyPassword = process.env.MONGO_READONLY_PASSWORD || 'dev_readonly_pass_123';
const replicaSetName = 'rs0';  // 必须与 mongod.conf 保持一致
const replicaMemberHost = 'mongo:27017';

print(`数据库: ${dbName}`);
print(`应用用户: ${appUser}`);
print(`只读用户: ${readonlyUser}`);
print('');

// 切换到业务数据库
db = db.getSiblingDB(dbName);

// 创建应用用户（读写权限）
try {
    db.createUser({
        user: appUser,
        pwd: appPassword,
        roles: [
            { role: 'readWrite', db: dbName },
            { role: 'dbAdmin', db: dbName }  // 允许管理索引和集合
        ]
    });
    print(`✅ 应用用户 '${appUser}' 创建成功 (readWrite + dbAdmin)`);
} catch (e) {
    if (e.code === 51003) {
        print(`⚠️  用户 '${appUser}' 已存在，跳过创建`);
    } else {
        print(`❌ 创建用户 '${appUser}' 失败: ${e.message}`);
    }
}

// 创建只读用户
try {
    db.createUser({
        user: readonlyUser,
        pwd: readonlyPassword,
        roles: [
            { role: 'read', db: dbName }
        ]
    });
    print(`✅ 只读用户 '${readonlyUser}' 创建成功 (read)`);
} catch (e) {
    if (e.code === 51003) {
        print(`⚠️  用户 '${readonlyUser}' 已存在，跳过创建`);
    } else {
        print(`❌ 创建用户 '${readonlyUser}' 失败: ${e.message}`);
    }
}

// 验证用户列表
print('');
print('📊 当前数据库用户列表:');
db.getUsers().users.forEach(function(user) {
    print(`  - ${user.user} (角色: ${user.roles.map(r => r.role).join(', ')})`);
});

// 初始化单节点副本集（仅首次空数据目录启动时执行）
print('');
print('🔁 检查副本集状态...');

try {
    const status = rs.status();
    if (status.set === replicaSetName) {
        print(`✅ 副本集 '${replicaSetName}' 已初始化，跳过`);
    } else {
        print(`⚠️  检测到已初始化的副本集 '${status.set}'，与预期 '${replicaSetName}' 不一致`);
    }
} catch (e) {
    if (e.codeName === 'NotYetInitialized' || e.code === 94) {
        print(`🚀 开始初始化单节点副本集 '${replicaSetName}' ...`);
        const result = rs.initiate({
            _id: replicaSetName,
            members: [
                { _id: 0, host: replicaMemberHost }
            ]
        });
        printjson(result);
    } else {
        print(`❌ 检查副本集状态失败: ${e.message}`);
    }
}

print('');
print('========================================');
print('MongoDB 初始化完成');
print('========================================');
print('');
print('📝 连接信息:');
print(`  应用连接: mongodb://${appUser}:${appPassword}@localhost:27017/${dbName}?authSource=${dbName}&replicaSet=${replicaSetName}&directConnection=true`);
print(`  只读连接: mongodb://${readonlyUser}:${readonlyPassword}@localhost:27017/${dbName}?authSource=${dbName}&replicaSet=${replicaSetName}&directConnection=true`);
print('');

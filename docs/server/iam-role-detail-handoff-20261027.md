# IAM 角色授权详情读取错误：独立 session 交接

结论：已发现一条确定的代码缺陷路径，与生产页面现象吻合。角色授权查询仍调用 `WithinTx`，而当前事务模式注入的 `PlannedUnitOfWork.WithinTx` 无条件拒绝，返回 `ErrWritePlanRequired`。应先用实际请求/日志或真实装配测试闭环确认，不把静态分析直接写成生产根因已验证。当前尚未修复、未部署修复。

## 已观察事实

- 2026-10-27 M4 上线验收时，Qlume 后台 `/admin/authz`，合法 system 账号（actor 10001）选择角色，会出现“服务器端出错”“获取角色授权详情失败”。在 M4 最终镜像部署前后均出现；不能据此断言问题早于 M3。
- 角色列表和新空角色创建成功；M4 专用空角色 `m4-20261027-rmq-acceptance` 已创建，数据库确认零授权、零成员，策略版本176→177。事务 witness 和 IAM/QS 双订阅独立通过；这些证据不代表详情读取接口通过。
- 目前未保存能定位该现象的原始 HTTP status/body/request_id 或对应服务端错误日志。前端把两个并发请求的失败归并为同一个 toast，单凭 toast 不能确定失败的是 grants 还是 assignments。

## 前端请求链

本地只读源码：`/Users/yangshujie/workspace/typescript/github.com/fangcun-mount/qs-operating-system`，核对 SHA `8eefb9e0660bc1ffeef6dde31805a9b8caaa5623`。这不是本次重新核验的生产前端 SHA。

- `src/store/authStore.ts:117` 的 `fetchRoleDetails` 使用 Promise.all 并发查询两条接口；任一失败都显示同一个“获取角色授权详情失败”。
- `src/api/path/authz.ts:195` → `GET /api/v4/authz/roles/{roleId}/grants`。
- `src/api/path/authz.ts:213` → `GET /api/v4/authz/roles/{roleId}/assignments`。
- `src/api/iamV4Server.ts:29` 生成生产 IAM v4 baseURL，响应拦截器区分 HTTP 错误与业务 code；排查时要同时记录 HTTP status 和业务 code。

## 已发现的后端代码缺陷

只读工作区：`/Users/yangshujie/.codex/worktrees/rocketmq-m4/iam-disposition`，main基线 `d22910071e8e5d21fb411b7c0856c18d8d2aefc6`；生产M4应用源码基线 `4609d4542d9303130ab94ed67593d0a69d0d010d`，具体运行镜像见 infra M4 发布索引。

1. `internal/apiserver/transport/rest/authz/router.go:55`：角色grants GET注册 ListRoleGrants，要求 permission_grants/list 权限。
2. `internal/apiserver/transport/rest/authz/handler/permission_grant.go:114`：ListRoleGrants调用 service.ListByRole。
3. `internal/apiserver/application/authz/permissiongrant/service.go:185`：ListByRole调用 `s.uow.WithinTx`，callback原本要查询角色、RequireVisible，再读取grants。
4. `internal/apiserver/container/authz/infra.go:43`：事务模式从 eventStager.ApplicationUnitOfWork 获取实际UOW；`application.go:25` 将其注入permissionGrantService。
5. `internal/apiserver/infra/mysql/uow/authz/planned.go:239`：ApplicationUnitOfWork返回PlannedUnitOfWork副本。
6. 同文件`:79`：`PlannedUnitOfWork.WithinTx`无条件返回 `app.ErrWritePlanRequired`，不会运行读取callback。
7. 同文件`:82`已有 `ReadPlan`，委托原 TransactionUnitOfWork 的只读事务能力。`application/authz/uow/planning.go:12`定义错误文本 `explicit authorization write plan required`。

因此即使角色没有grant，也可能在真正查库前失败；“零grant导致mapper失败”不能作为默认解释。assignment查询走独立Directory，仍须单独验证，不能因共享toast一起判定失败。

## 建议新 session 的执行顺序

1. 更新各仓库main并独立建工作区；先核对实际部署SHA及合法system会话。
2. 在页面选择该专用空角色，分别记录grants/assignments两请求的HTTP状态、业务code与request_id；只保留脱敏信息，不能复制令牌、Cookie或完整账号资料。
3. 读取对应IAM错误日志，确认是否为ErrWritePlanRequired；为“真实事务模式装配→ListRoleGrants”补失败用例，同时覆盖空角色和有授权角色。
4. 给只读查询使用明确的只读边界（例如现有ReadOnlyPlanner），保留角色可见性与权限检查。不要为了修读接口放开PlannedUnitOfWork.WithinTx写入保护，也不要给GET构造半消息或修改策略版本。
5. 查找其他只读服务是否误用WithinTx，逐项证明范围；避免顺手扩大到全部授权写链重构。
6. 验证有权限读取、无权限拒绝、空列表、已有grant、角色成员、快速切换角色；GET不得新增witness、消息、操作或策略版本。
7. 源码测试、完整CI、部署健康、合法system页面验收分别记账，再更新infra现存问题条目。

## 当前 session 边界

这里只整理说明，没有修改IAM/前端业务源码或执行权限数据修复。历史资产处置及自动生产CD恢复现已完成，见infra的M4追加操作总表。三库自动CD已恢复，修复合并main后的成功CI可能触发部署；新session应先核对最新运行基线及共享部署锁，分别记录源码、部署与页面验收。

可直接给新 session：

> 请按此交接说明先复现并修复 IAM 角色授权详情读取错误。重点验证 `permissiongrant.Service.ListByRole -> PlannedUnitOfWork.WithinTx -> ErrWritePlanRequired`，采用明确只读边界，保留写计划强制保护与角色可见性检查，补实际事务装配测试。分别验收 grants/assignments，不将共享toast当作单接口根因证据。遵守现有部署锁和生产基线，修复源码/CI、生产部署、system页面验收分别记录。

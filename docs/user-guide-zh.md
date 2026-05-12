# A8 OA 用户使用手册

## 1. 系统用途

A8 OA 用于管理公司内部采购申请、差旅申请、审批流程、项目预算、实际费用、公司卡交易、收据政策和会计复核。

系统的核心目标是：

- 申请提交前检查项目和预算。
- 提交后自动匹配审批规则并创建审批任务。
- 审批通过后保留预算。
- 记录实际费用时消耗预算并释放对应保留预算。
- 将超预算、缺少收据、公司卡重复或异常等事项送入会计复核。
- 在申请关闭前确认审批、预算、附件、公司卡和会计复核事项都已完成。

## 2. 常见角色

| 角色 | 主要工作 |
| --- | --- |
| Requester / 申请人 | 创建 PR/TR、提交审批、上传附件、处理退回申请 |
| Approver / 审批人 | 审批、退回、拒绝、领取或释放审批任务 |
| Accounting / 会计 | 记录实际费用、处理会计复核、分配公司卡交易 |
| Finance Admin / 财务管理员 | 维护超预算政策、收据政策、查看财务报表 |
| System Admin / 系统管理员 | 维护用户、部门、项目、审批规则和系统设置 |

## 3. 登录、首页和导航

1. 打开系统网址。
2. 输入用户名和密码登录。
3. 登录后进入 Dashboard。

Dashboard 会按优先级分区：

- My Work Today：最紧急的事项，例如待审批、退回给我、缺少收据、待处理会计复核、未匹配公司卡和阻塞事项。
- Approval Summary：审批任务数量和最近审批活动。
- My Requests / My Recent Activity：草稿、待审批、已批准未关闭、创建 PR/TR 快捷入口和最近申请列表。
- Team / Department / Finance Oversight：有权限时显示团队、部门或财务例外事项。
- Admin / Setup Shortcuts：较低优先级的设置入口，通常会折叠或弱化显示。

普通申请人不会看到财务或系统管理卡片。

顶部导航按功能分组：

- Dashboard。
- Work：Purchase Requests、Travel Requests、My Tasks、My Approval History。
- Finance：Accounting Review Queue、Card Transactions、Finance Reports、Variance Report。
- Setup：Projects、有权限时显示 Create Project、Departments、Approval Rules、Over-Budget Policies、Receipt Policies。
- Admin：Django Admin 和系统设置入口。

菜单会根据权限显示。如果某个分组下没有你可访问的页面，该分组不会显示。

桌面浏览器中，鼠标悬停在 Work、Finance、Setup 或 Admin 上会自动展开下拉菜单，也可以点击分组打开或关闭。点击页面其他位置或按 Escape 可以关闭菜单。

列表和设置页面使用统一结构：

1. 页面标题和主要操作，例如 Create Rule 或 New Project。
2. 可选 summary cards。
3. Filters 区域，且只放筛选相关字段和 Apply / Clear。
4. 数据表格。
5. 如有需要显示分页。

Create、New、Add、Import 这类创建动作是页面级操作，不应放在 Filters 区域。

## 4. 采购申请流程

### 4.1 创建采购申请

1. 进入 Work > Purchase Requests。
2. 创建 Purchase Request。
3. 填写标题、部门、项目、币种、申请日期和用途说明。
4. 添加采购明细行，包括物品名称、数量、单价、金额和说明。
5. 保存草稿。

### 4.2 提交审批

提交时系统会检查项目状态、预算、审批规则，并创建审批任务。审批通过后系统会保留预算。

如果没有可用审批规则，提交会失败。

### 4.3 上传附件

可以在申请详情页上传报价单、合同、收据、发票或其他支持文件。附件上传和删除会写入审计记录。

### 4.4 记录实际采购费用

采购申请完全批准后，会计或授权用户可以记录实际费用。系统会：

- 应用超预算政策。
- 应用收据 / 发票政策。
- 创建实际费用记录。
- 消耗项目预算。
- 释放相关保留预算。
- 必要时创建会计复核事项。

### 4.5 关闭采购申请

PR 可以关闭的前提包括：

- 申请已批准。
- 没有未解决的 Accounting Review Item。
- 没有未完成审批任务。
- 没有未完成的 supplemental request。
- 相关公司卡交易已匹配和复核。

详情页顶部会显示 Financial Summary、Closeout Checklist、Available Actions 和 Open Issues。如果 Close Request 被禁用，页面会显示原因。

## 5. 差旅申请流程

1. 进入 Work > Travel Requests。
2. 创建 Travel Request。
3. 填写出差目的、部门、项目、出发地、目的地、开始日期、结束日期和币种。
4. 添加行程和预计费用。
5. 提交审批。

如果启用 per diem 政策，系统会根据差旅信息计算允许金额和申请金额。实际差旅费用与预计费用分开记录。

差旅申请关闭前同样需要确认实际费用、收据要求、会计复核、公司卡交易和 supplemental request 都已完成。

## 6. 超预算政策

| 策略 | 结果 |
| --- | --- |
| WARNING | 显示警告，但允许记录实际费用 |
| REVIEW | 创建会计复核事项，关闭前必须解决 |
| AMENDMENT_REQUIRED | 需要 supplemental request 或会计例外批准，关闭前必须解决 |
| BLOCK | 阻止记录实际费用，避免错误消耗预算 |

## 7. Supplemental Request

已批准申请不应直接修改金额。如果实际需要增加预算：

1. 从原申请创建 supplemental request。
2. Supplemental request 只表示新增金额。
3. 原申请保持不变。
4. Supplemental request 走审批流程。
5. 审批通过后只为新增金额保留预算。
6. 原申请会显示关联的 supplemental request。

原申请关闭前，所有未完成的 supplemental request 必须处理完。

## 8. 收据 / 发票政策

财务可以配置收据和发票规则，例如：

- 小金额收据可选。
- 达到一定金额后收据必填。
- 达到更高金额后发票必填。
- 公司卡交易默认需要收据，除非批准例外。

如果缺少必需附件，系统会创建 MISSING_RECEIPT 会计复核事项，并阻止申请关闭。当前版本按申请级附件判断，尚未做到逐条实际费用绑定收据。

## 9. 会计复核工作台

进入 Finance > Accounting Review Queue。

优先使用快速标签：

- All Pending。
- Over-Budget。
- Missing Receipt。
- Amendment Required。
- Duplicate Card。
- Returned。
- Resolved。

Basic Filters 默认显示：

- Keyword。
- Status。
- Reason。
- Source Type。
- Policy Action。

Advanced Filters 默认折叠，需要时展开：

- Requester。
- Department。
- Project。
- Minimum Aging Days。

Filter 只应用筛选条件。Reset 会清除筛选条件，但保留当前快速标签。

每条复核事项会显示来源申请或公司卡交易、申请人、部门、项目、原因、金额、超预算金额、策略动作、aging、severity、required action 和状态。复杂决策建议点击 View 进入 Accounting Review Detail 页面处理。

申请人不能复核自己的会计复核事项。

## 10. 公司卡交易

进入 Finance > Card Transactions 创建或查看公司卡交易。

公司卡交易详情页按 reconciliation 布局显示：

- Transaction Amount。
- Allocated Amount。
- Unallocated Amount。
- Match Status。
- Open Reviews。
- Duplicate Warning。

Unallocated Amount 是最重要的数字，表示还未分配的金额。

分配公司卡交易时，可以选择 Purchase Request、Travel Request 或 Project direct cost。系统会阻止分配金额超过未分配金额。完全匹配且没有未解决复核事项后，交易才能 Mark Reviewed。

## 11. 财务报表

进入 Finance > Finance Reports。

报表包括：

- Project Budget Summary。
- Department Spending Summary。
- Reserved vs Consumed Budget。
- Open Requests With Remaining Reserve。
- Over-Budget Exceptions。
- Company Card Unmatched Transactions。
- Accounting Review Aging。

所有金额会统一显示：

- 币种代码。
- 千分位。
- 两位小数。

示例：USD 12,710.00。

当前 Finance Reports 是基准币报表。公司基准币为 USD。

如果发生外币业务，系统会在来源记录、Accounting Review Item 和 Company Card Transaction 上保留原始交易币种与交易金额。预算控制、Consumed、Released 以及管理报表总额使用 USD 基准金额。

公司卡外币交易如果有账单入账 USD 金额，则以账单入账 USD 金额作为权威基准金额。

PR/TR 详情页的实际费用会显示基准金额，也会在有外币资料时显示原始交易金额。

如果外币实际费用超过批准 USD 基准金额只是因为汇率变化，系统可以识别为 FX Variance，而不是普通超支。如果原始交易金额本身也增加，则按 Spending Overrun 处理。

## 12. 设置页面

Setup 中可以维护：

- Projects。
- Departments。
- Approval Rules。
- Over-Budget Policies。
- Receipt Policies。

列表页的通用结构应为：页面标题和主要操作、筛选区、列表表格、分页。Create / New / Import 这类创建动作不应放在 Filters 区域中。

## 13. 常见问题

### 为什么申请不能关闭？

常见原因：

- 有未解决的 Accounting Review Item。
- 有未完成审批任务。
- 有未完成 supplemental request。
- 有未完全匹配或未复核的公司卡交易。
- 实际费用复核仍处于 pending。

请先查看详情页顶部的 Closeout Checklist 和 disabled action reason。

### 为什么实际费用不能保存？

常见原因：

- 申请尚未批准。
- 金额小于等于 0。
- 项目预算不足。
- 超预算政策结果为 BLOCK。

### 上传了附件，为什么仍然有 missing receipt review？

当前系统按申请级附件判断。如果 review item 已经创建，上传附件后仍需要会计在 Accounting Review Detail 中 Resolve 或 Approve Exception。

## 14. 上线前建议

上线前建议完成：

- 确认审批规则。
- 确认项目和部门基础数据。
- 确认超预算政策。
- 确认收据政策。
- 建立测试用户。
- 跑一遍采购全流程 UAT。
- 跑一遍差旅全流程 UAT。
- 跑一遍公司卡分配 UAT。
- 跑一遍会计复核 UAT。

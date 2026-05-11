# A8 OA 用户使用手册

## 1. 系统用途

A8 OA 用于管理公司内部采购申请、差旅申请、审批流程、项目预算、实际费用、公司卡交易和会计复核。

系统的核心目标是：

- 申请前确认预算。
- 申请提交后自动匹配审批规则。
- 审批通过后保留预算。
- 实际费用发生后消耗预算。
- 超预算、缺少收据、公司卡异常等情况进入会计复核。
- 关闭申请前确认预算、附件、审批、会计复核和公司卡事项都已完成。

## 2. 常见角色

| 角色 | 主要工作 |
| --- | --- |
| Requester / 申请人 | 创建 PR/TR，提交审批，上传附件，处理退回申请 |
| Approver / 审批人 | 在 My Tasks 中审批、退回、拒绝、领取或释放任务 |
| Manager / 经理 | 审批部门内申请，查看相关任务 |
| Accounting / 会计 | 记录实际费用，处理会计复核，分配公司卡交易 |
| Finance Admin / 财务管理员 | 维护超预算策略、收据策略，查看财务报表 |
| System Admin / 系统管理员 | 维护用户、部门、项目、审批规则和基础数据 |

## 3. 登录、首页和导航

1. 打开系统地址。
2. 输入用户名和密码登录。
3. 登录后进入 Dashboard。

Dashboard 通常会显示：

- 当前待办审批任务。
- 最近的采购申请。
- 最近的差旅申请。
- 与你有关的申请状态。

顶部导航现在使用分组下拉菜单：

- Dashboard。
- Work：Purchase Requests、Travel Requests、My Tasks、My Approval History。
- Finance：Accounting Review Queue、Card Transactions、Finance Reports、Variance Report。
- Setup：Projects、Departments、Approval Rules、Over-Budget Policies、Receipt Policies。
- Admin：Django Admin 和系统设置入口。

你能看到哪些菜单取决于权限。如果一个分组里没有任何你有权限访问的菜单，该分组不会显示。

桌面浏览器中，可以把鼠标移到 Work、Finance、Setup 或 Admin 上自动展开下拉菜单，也可以点击菜单分组打开或关闭。点击页面其他位置或按 Escape 可以关闭菜单。键盘用户可以 Tab 到菜单分组后按 Enter 或 Space 打开。

## 4. 采购申请流程

### 4.1 创建采购申请

1. 进入 Work > Purchase Requests。
2. 点击创建采购申请。
3. 填写申请头信息：
   - 标题。
   - 申请部门。
   - 项目。
   - 币种。
   - 申请日期。
   - 用途或说明。
4. 添加采购明细行：
   - 物品名称。
   - 数量。
   - 单价。
   - 金额。
   - 说明。
5. 保存草稿。

### 4.2 上传附件

在采购申请详情页上传相关附件，例如：

- 报价单。
- 供应商资料。
- 合同草案。
- 收据或发票。
- 其他支持文件。

附件上传和删除会写入内容审计记录。

### 4.3 提交审批

1. 检查申请内容和预算。
2. 点击 Submit。
3. 系统会检查项目状态和预算、匹配审批规则、创建审批任务并保留预算。

如果没有可用审批规则，提交会失败。

### 4.4 审批

审批人进入 Work > My Tasks。

可执行：

- Approve：同意。
- Return：退回给申请人修改。
- Reject：拒绝。
- Claim：从审批池领取任务。
- Release：释放回审批池。

审批历史会记录每一步操作。

### 4.5 记录实际采购费用

采购申请完全批准后，会计或有权限用户可以记录实际费用。

填写：

- 实际日期。
- 金额。
- 供应商。
- 参考号或发票号。
- 备注。

系统会应用超预算策略和收据/发票策略，写入实际费用记录，消耗项目预算，释放对应的已保留预算。如有异常，会创建会计复核事项。

### 4.6 采购申请详情页和关闭检查

采购申请详情页顶部现在优先显示：

- 申请状态。
- 当前负责人 / 下一步处理人。
- 财务摘要。
- Closeout Checklist。
- Available Actions。
- Open Issues。

如果按钮不可用，系统会显示禁用原因。请先查看禁用原因和 Closeout Checklist，再判断下一步需要做什么。

采购申请可以关闭的前提：

- 申请已批准。
- 已记录实际费用。
- 没有未解决的 Accounting Review Item。
- 没有未完成的审批任务。
- 没有未完成的 amendment / supplemental request。
- 公司卡相关交易已完成匹配和复核。

关闭后，系统会释放剩余未使用的保留预算。

## 5. 差旅申请流程

### 5.1 创建差旅申请

1. 进入 Work > Travel Requests。
2. 创建差旅申请。
3. 填写：
   - 出差目的。
   - 申请部门。
   - 项目。
   - 出发城市和目的地。
   - 开始日期和结束日期。
   - 币种。
4. 添加行程。
5. 添加预计费用。

### 5.2 Per Diem

如果公司启用了 per diem 策略，系统会根据差旅信息计算允许金额、申请金额，以及是否超过允许额度。

提交前请确认 per diem 金额正确。

### 5.3 提交、审批和实际费用

提交差旅申请时，系统会检查行程、预计费用、项目预算，匹配审批规则，创建审批任务并保留预算。

差旅申请批准后，可以记录实际差旅费用。系统会保持预计费用和实际费用分离，应用超预算策略和收据/发票策略，消耗项目预算，释放对应保留预算，并在需要时创建会计复核事项。

### 5.4 差旅申请详情页和关闭检查

差旅申请详情页与采购申请详情页使用同样的结构。请先查看：

- 财务摘要。
- Closeout Checklist。
- Available Actions。
- Open Issues。
- Per Diem Summary。

关闭前必须确认：

- 实际费用已录入。
- 会计复核事项已解决。
- 收据或发票要求已满足，或会计已批准例外。
- 公司卡交易已完成匹配。
- 没有未完成的 amendment。

关闭后，剩余保留预算会释放。

## 6. 超预算策略

系统支持四类主要策略：

| 策略 | 结果 |
| --- | --- |
| WARNING | 显示警告，但允许记录实际费用 |
| REVIEW | 创建会计复核事项，关闭申请前必须解决 |
| AMENDMENT_REQUIRED | 要求创建补充申请或会计例外审批，关闭申请前必须解决 |
| BLOCK | 阻止记录实际费用，不会错误消耗预算 |

## 7. Amendment / Supplemental Request

已批准申请不应直接修改预算金额。

如果实际需要增加预算：

1. 在原申请上创建 supplemental request。
2. supplemental request 只表示新增金额。
3. 原申请保持不变。
4. supplemental request 走审批流程。
5. 审批通过后，系统只为新增金额保留预算。
6. 原申请会显示关联的 supplemental requests。

原申请关闭前，所有未完成的 supplemental requests 必须处理完成。

## 8. 收据 / 发票策略

财务可以配置：

- 金额低于某值时收据可选。
- 金额达到某值时收据必填。
- 金额达到更高值时发票必填。
- 公司卡交易必须有收据，除非批准例外。

如果实际费用缺少所需附件：

- 系统创建 MISSING_RECEIPT 会计复核事项。
- 申请关闭会被阻止。
- 用户需要上传附件，或会计批准例外 / 解决复核事项。

当前版本按申请级附件判断是否有支持文件，还没有逐行绑定收据。

## 9. 会计复核工作台

进入 Finance > Accounting Review Queue。

请优先使用快速标签：

- All Pending。
- Over-Budget。
- Missing Receipt。
- Amendment Required。
- Duplicate Card。
- Returned。
- Resolved。

也可以继续使用筛选条件：

- 状态。
- 原因。
- 来源类型。
- 策略动作。
- 申请人。
- 部门。
- 项目。
- Aging days。
- 关键词。

每条复核事项会显示：

- 来源申请或公司卡交易。
- 申请人、部门、项目。
- 原因。
- 策略动作。
- 金额和超预算金额。
- Aging badge。
- Severity badge。
- Required Action。
- 状态。

复杂决策请点击 View 打开 Accounting Review Detail 页面处理。Detail 页面会显示 Issue Summary、Source links、Financial Impact、Receipt / Attachment Status、Decision History 和 Action Panel。

会计可选择：

- Approve Exception。
- Return。
- Reject。
- Resolve。

申请人不能复核自己的会计复核事项。

## 10. 公司卡交易

### 10.1 创建或导入交易

进入 Finance > Card Transactions，创建公司卡交易。

填写：

- Statement date。
- Transaction date。
- Merchant。
- Amount。
- Currency。
- Cardholder。
- Reference。

系统会检测潜在重复交易。

### 10.2 公司卡交易详情页

公司卡交易详情页现在按 reconciliation 布局展示。

请先查看 Summary Cards：

- Transaction Amount。
- Allocated Amount。
- Unallocated Amount。
- Match Status。
- Open Reviews。
- Duplicate Warning。

Unallocated Amount 是最重要的数字，表示还有多少金额没有分配。

### 10.3 分配公司卡交易

在 Allocation Panel 中选择一个目标：

- Purchase Request。
- Travel Request。
- Project direct cost。

输入分配金额。系统会阻止分配金额超过剩余未分配金额。前端会先提示，后端仍会做最终校验。

一笔公司卡交易可以拆分到多个目标，但总分配金额不能超过公司卡交易金额。

### 10.4 匹配和复核状态

| 状态 | 含义 |
| --- | --- |
| Unmatched | 没有分配 |
| Partially Matched | 部分分配 |
| Matched | 已完整分配 |
| Reviewed | 会计已确认 |

只有 Matched 且无未解决复核事项时，才能 Mark Reviewed。

Mark Reviewed 按钮会保持可见。如果不可用，页面会显示禁用原因。

### 10.5 重复交易

如果系统发现相同日期、商户、金额和参考号的交易，会创建重复交易复核事项。

系统不会自动阻止交易，因为真实业务中可能存在合法重复交易。若页面显示 Duplicate Warning，请打开关联复核事项处理。

## 11. 财务报表

进入 Finance > Finance Reports。

当前报表包括：

- Project budget summary。
- Department spending summary。
- Reserved vs consumed budget。
- Open requests with remaining reserve。
- Over-budget exception report。
- Company card unmatched transaction report。
- Accounting review aging report。

这些报表用于日常运营和上线前 UAT，不是复杂 BI 看板。

## 12. 财务策略维护

### 12.1 超预算策略

进入 Setup > Over-Budget Policies。

可配置申请类型、部门、项目类型、支付方式、币种、超预算金额范围、超预算百分比范围、动作、优先级和启用状态。

### 12.2 收据策略

进入 Setup > Receipt Policies。

可配置申请类型、部门、项目类型、费用类型、支付方式、币种、金额范围、是否需要收据、是否需要发票、是否允许例外、优先级和启用状态。

优先级数字越小，越先匹配。

## 13. 项目预算

项目预算由以下动作影响：

- RESERVE：申请提交或 amendment 批准后保留预算。
- CONSUME：实际费用入账后消耗预算。
- RELEASE：申请关闭、退回、取消、拒绝或实际费用转换时释放预算。
- ADJUST：人工调整。

项目详情和预算 ledger 可查看完整记录。

## 14. 常见问题

### 为什么申请不能关闭？

常见原因：

- 有未解决的 Accounting Review Item。
- 有未完成审批任务。
- 有未完成 amendment。
- 有未完全匹配或未复核的公司卡交易。
- 实际费用复核仍处于 pending。

请先查看详情页顶部的 Closeout Checklist 和 disabled action reason。

### 为什么实际费用不能保存？

常见原因：

- 申请尚未批准。
- 金额小于等于 0。
- 项目预算不足。
- 超预算策略结果为 BLOCK。

### 上传了附件为什么仍有 missing receipt review？

当前系统按申请级附件判断。如果 review item 已经创建，上传附件后仍需要会计在 Accounting Review Detail 中 Resolve 或 Approve Exception。

### 导航 hover 不展开怎么办？

请先确认浏览器加载的是最新静态文件。部署到 GoDaddy 后需要确认已经执行 collectstatic，并硬刷新浏览器。如果 Edge 仍有问题，可以点击菜单分组打开下拉菜单。

## 15. 上线前建议

上线前建议完成：

- 确认审批规则。
- 确认项目和部门基础数据。
- 确认超预算策略。
- 确认收据策略。
- 建立测试用户。
- 跑一次采购全流程 UAT。
- 跑一次差旅全流程 UAT。
- 跑一次公司卡分配 UAT。
- 跑一次会计复核 UAT。

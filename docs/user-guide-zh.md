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
- Finance：Accounting Review Queue、Card Transactions、Accounting Periods、Finance Reports、Variance Report。
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

### 3.1 System Setup

System Setup 是业务设置中心，和 Django Admin 分开。

System Setup 会显示：

- Base Currency 和 Active Currencies。
- Departments、Projects、Approval Rules 和 Finance Policy 配置状态。
- Currency、Exchange Rate、FX Variance Policy 快捷入口。
- 当前版本和 setup health 信息。
- Role / Permission Matrix。

普通申请人不能访问 System Setup。

Finance/Admin 用户可以通过 System Setup 进入常用设置页面，不需要把 Django Admin 当成主要业务入口。

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

可以使用 Export CSV 下载报表。导出会包含基准币金额字段，并在有资料时包含原始交易币种和原始交易金额字段。

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

### 11.1 财务完整性控制

Accounting Period 可以从 Finance > Accounting Periods 或 System Setup > Accounting Periods 进入。

Accounting Period 可以配置为 Open、Closing 或 Closed。期间详情页会显示 Period Close Checklist，用来检查未解决会计复核、missing receipt、未匹配公司卡交易、有剩余 reserve 的未关闭申请，以及未完成 correction workflow。

当期间为 Closed 时，系统会阻止该期间内的普通财务修改，例如实际费用入账和公司卡分配变更。Finance/Admin 的调整处理会走单独控制。

Finance/Admin 用户可以填写 close notes 后关闭期间。重新打开已关闭期间必须填写原因，并且仅限 finance setup 用户操作。

Accounting 用户可以在 PR/TR 详情页记录 Refund / Credit / Reversal。退款和贷项会作为独立的负数实际费用记录，不会删除原始实际费用。退款会通过负数预算 ledger entry 减少 consumed budget。

已关闭的 PR/TR 只能由 Finance/Admin 重新打开进行 correction。Reopen 必须填写原因，会写入历史记录，重新关闭时仍会执行 closeout validation。

PR/TR 详情页已经可以进行实际费用行级别的 receipt/invoice 关联。在 Actual Expenses 区域，有权限的用户可以把收据或发票直接上传到某一条 actual expense line，也可以把已有的 request-level attachment 关联到具体费用行。

Missing receipt review 会指向具体缺少支持文件的 actual expense line。关联正确的 receipt 或 invoice 后，missing receipt 复核路径可以被清理，不再只依赖泛泛的申请级附件。

公司卡直接分配到 Project Direct Cost 会受政策控制。Finance 可以配置允许、复核、需要项目负责人审批或阻止。

Direct Project Cost Policies 可以从 Setup > Direct Project Cost Policies 或 System Setup 进入。Accounting 将公司卡交易直接分配到项目时，Card Transaction Detail 会显示 policy result，以及需要项目负责人复核时的 owner review status。

审批 delegation 可以从 Work > My Delegations 配置。审批人可以设置日期范围内的代理审批人；Finance/Admin 用户可以查看 active delegations，也可以带原因重派卡住的 approval task。Delegation 不允许 requester self-approval。

## 12. 设置页面

System Setup 是 Finance/Admin 用户的业务设置中心。现在 Currencies、Exchange Rates、FX Variance Policies、Accounting Periods 和 Finance Policies 都有业务 UI 入口，日常设置不需要依赖 Django Admin。

当前 company base currency 是 USD。System Setup 和 Finance Reports 会显示这个基准币。这个字段目前不开放普通 UI 修改，因为变更 base currency 会影响 budget ledger、actual expense、company card 和历史报表，需要单独的数据转换和迁移方案。

### 12.0 币种和汇率设置

打开 Currencies 可以维护 active transaction currencies，例如 USD、TWD、EUR、JPY。

打开 Exchange Rates 可以按 effective date 维护公司汇率。实际费用入账时会 snapshot 当时使用的 exchange rate，所以之后维护新汇率不会静默重算历史交易。

打开 FX Variance Policies 可以单独控制汇率变动造成的差异，避免把纯汇率差异全部当成普通超支。

Setup 中可以维护：

- Projects。
- Department General Budgets。
- Departments。
- Approval Rules。
- Over-Budget Policies。
- Receipt Policies。

列表页的通用结构应为：页面标题和主要操作、筛选区、列表表格、分页。Create / New / Import 这类创建动作不应放在 Filters 区域中。

## 13. Department General Budget

Finance/Admin 用户可以从 System Setup 或 Setup > Department General Budgets 进入 Department General Budget Setup。

这个页面用于把每个 department + fiscal year 绑定到一个 Department General Budget project，例如 `MIS-GENERAL-2026`。

规则：

- General project 必须属于选择的 department。
- Project type 必须是 Department General Budget。
- System Setup 会提示当前 fiscal year 哪些 active departments 缺少 general project setup。
- 一般部门费用的 PR/TR 应该使用对应部门的 general project。

如果 PR/TR 选择了 Department General Budget project，request department 必须和 project owning department 一致。

### 13.1 Budget Adjustment Request

项目预算调整不再是直接写入 ledger。

现在的规则是：

- Project manager 可以从 Project Budget Ledger 提交 Budget Adjustment Request。
- 提交 request 不会立刻影响项目预算。
- Finance/Admin 审批并 post 之后，系统才会创建 ADJUST ledger entry。
- Reject 的 adjustment 不影响预算。
- 每个 adjustment 都必须填写 reason，作为 audit 依据。

### 13.2 Approval Rule Snapshot

PR/TR/Project Budget 提交审批时，系统会在 Approval Task 上保存当时使用的 rule snapshot：

- Rule code。
- Rule name。
- Rule version。
- Step name。
- Step type。
- Assigned user。
- Candidate pool snapshot。

之后即使 Approval Rule 被修改，旧 request 的审批历史仍然显示提交当时的规则上下文。

### 13.3 Duplicate Actual Expense / Invoice Review

Accounting 录入 actual expense 时，系统会根据 vendor / merchant、expense date、amount、reference number 检查可能重复的 actual expense。

当 receipt / invoice 被 link 到 actual expense line 时，系统也会比较附件 file hash，用来发现同一张 receipt 或 invoice 被重复用于其他 actual expense line。

如果发现疑似重复：

- 系统不会自动删除或阻止 legitimate transaction。
- 系统会创建 Accounting Review Item。
- Accounting 可以在 review 中 resolve 或 approve exception。
- Accounting Review Detail 会显示 runtime 计算出来的 duplicate candidates，并在可以解析时链接回对应 PR/TR detail 页面。

重要限制：

- Duplicate candidates 是打开 review detail 时根据当前记录计算出来的，不是不可变的 persisted duplicate snapshot。

### 13.4 Attachment Retention

附件是审计证据。

当前规则：

- Draft 阶段授权用户可以删除附件。
- 删除采用 soft delete，保留审计信息。
- 已经 linked 到 actual expense line 的 receipt / invoice，普通 requester 在 posting 后不能删除。
- Accounting/Admin 用户 void 已 posting 或 linked evidence 时必须填写 reason。
- PR/TR detail 页面会在 Attachment History 中显示 soft-deleted / voided attachments。
- Closed request 的附件会被保留，不能正常删除。

当前限制：

- 目前是 void-with-reason workflow，还不是完整的 attachment replacement workflow。

### 13.5 Finance Reports Drill-Down

Finance Reports 现在提供 link-based drill-down 链接：

- Project Budget Summary 可打开 project budget ledger。
- Over-Budget Exceptions 可打开 Accounting Review Detail。
- Accounting Review Aging 可打开 Accounting Review Detail。
- Open Reserve 行可打开来源 PR/TR。
- Unmatched Card 行可打开 card transaction detail。

这是 operational drill-down，不是 advanced reporting / BI framework。

## 14. 常见问题

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
- 实际费用日期位于已关闭的 Accounting Period。

### 为什么公司卡交易不能分配？

常见原因：

- 分配金额超过未分配金额。
- 交易日期位于已关闭的 Accounting Period。
- Direct Project Cost Policy 阻止该分配。

### 上传了附件，为什么仍然有 missing receipt review？

Receipt support 需要关联到具体 actual expense line。请打开 PR/TR 详情页，在 Actual Expenses 区域找到对应费用行，然后使用 Upload 或 Link Existing Attachment。若 review item 已经存在，行级 receipt 关联可以清理 missing receipt 路径；必要时会计也可以在 Accounting Review Detail 中 Resolve 或 Approve Exception。

### 审批人不在时，如何设置代理审批？

打开 Work > My Delegations，创建 delegation，选择 delegate user，并设置 start/end date。Delegation 生效期间，代理人可以在 My Tasks 中看到 delegated tasks，但仍然不能审批自己的申请。

### 为什么 Project Direct Cost 的公司卡分配会被阻止？

Finance 可以配置 Direct Project Cost Policies。政策可以允许分配、创建会计复核、要求项目负责人复核，或直接阻止 direct posting。如果被阻止，请把公司卡交易分配到已批准的 PR/TR，或请 Finance 检查政策设置。

## 15. 上线前建议

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

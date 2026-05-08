# Pilot Hardening Priority Matrix

Use this matrix during the V0.6 business-control review meeting.

| # | Area | Recommended Label | Priority | Pilot Risk | Decision Owner | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Period Close / Financial Locking | Go-Live Blocker | High | Historical financials can change after month-end | Finance / Accounting | Review before full rollout |
| 2 | Refund / Credit / Return Handling | Go-Live Blocker | High | Actual spend and budget reports can be overstated | Accounting | Likely real-world scenario |
| 3 | Reopen / Correction Workflow | Go-Live Blocker | High | Manual data fixes may become necessary | Accounting / Finance | Needs controlled audit trail |
| 4 | Direct Project Cost Controls | Conditional Go-Live Blocker | High / Medium | Direct cost can bypass PR/TR approval | Finance / Project Owners | High if direct posting is used |
| 5 | Department General Budget Handling | Go-Live Blocker | High | General spending audit becomes messy | Finance / Department Owners | Recommend annual department general projects |
| 6 | Role / Permission Granularity | Go-Live Blocker | High | Staff permission is too broad | Finance / System Admin | Needed before broad production |
| 7 | Approval Rule Snapshot / Versioning Confirmation | Go-Live Blocker | High | Historical approvals may lack audit confidence | Finance / Internal Audit | Confirm current task snapshot sufficiency |
| 8 | Approval Delegation / Escalation | V0.6 | Medium-High | Requests may get stuck | Department Managers | Production blocker if approvals stall |
| 9 | Line-Level Receipt Matching | V0.6 | Medium-High | Request-level attachment can over-satisfy receipt policy | Accounting | Acceptable for pilot if monitored |
| 10 | Emergency / After-The-Fact Purchase | V0.6 | Medium-High | Users may bypass system for urgent spend | Finance / Operations | Add stronger review |
| 11 | Budget Adjustment Approval | V0.6 | Medium-High | Manual budget manipulation risk | Finance | Needs authorization workflow |
| 12 | Duplicate Reimbursement / Invoice Detection | V0.6 | Medium | Duplicate reimbursement risk remains | Accounting | Extends duplicate control beyond cards |
| 13 | Multi-Currency / Exchange Rate | Post-Go-Live / Conditional V0.6 | Medium | Foreign spend may be inaccurate | Finance | Move up if international spend is common |
| 14 | Tax / Shipping / Tip / Fee Breakdown | Post-Go-Live | Medium | False over-budget reviews | Accounting | Helps reduce noise |
| 15 | Sales Order / Service Order Costing | Future | Medium | Customer profitability not captured | Business / Service | Do not build until needed |
| 16 | Report Export / Period Reporting | Post-Go-Live | Medium | Manual finance reporting effort | Finance | CSV/Excel exports first |
| 17 | Notification / Reminder / Aging Escalation | Post-Go-Live | Medium | Queues may age unnoticed | Operations | Tune after pilot aging data |
| 18 | Attachment Retention / Deletion Control | V0.6 / Post-Go-Live | Medium | Receipts can be removed after posting | Accounting | Review permission and retention rules |
| 19 | Material Change Policy Beyond Amount Increase | Post-Go-Live / V0.6 | Medium | Business purpose can change without reapproval | Finance / Approvers | Strong control, but not first pilot blocker |

## Meeting Checklist

- Confirm whether each item is relevant for pilot.
- Assign one decision owner per item.
- Decide whether each item is blocker, V0.6, post-go-live, or not needed.
- Identify the minimum controls required for limited pilot.
- Document accepted pilot risks explicitly.

## Suggested Pilot Gate

Do not start broad V0.6 feature development until:

- Finance and accounting have reviewed this matrix.
- Go-live blockers are agreed.
- Pilot department is selected.
- Pilot support process is defined.
- Real pilot issues are logged and triaged.

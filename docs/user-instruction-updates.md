# User Instruction Updates

Last updated: 2026-05-11

This document records user-facing instruction changes needed because of the recent UI productization work.

## Navigation

The top navigation is no longer a long flat menu.

Users should now navigate by grouped menus:

- Dashboard
- Work
- Finance
- Setup
- Admin

Desktop users can either:

- Hover over a group such as Work, Finance, Setup, or Admin to open the dropdown.
- Click the group to open or close the dropdown.

Keyboard users can:

- Tab to a dropdown group.
- Press Enter or Space to open it.
- Press Escape to close open dropdowns.

Touch users should continue to use click/tap behavior.

## Purchase Request / Travel Request Detail Pages

Users should read the top of the detail page first.

The most important information is now near the top:

- Request status.
- Current owner / next action owner.
- Financial summary.
- Closeout checklist.
- Available actions.
- Open issues.

If an action is unavailable, users should look at the disabled action reason and the closeout checklist before asking MIS or accounting for help.

## Closeout Checklist

The Closeout Checklist explains why a request can or cannot be closed.

Common blockers:

- Request is not approved.
- Actual expense has not been recorded.
- Accounting Review Item is unresolved.
- Supplemental request is still open.
- Approval task is still open.
- Linked card transaction is not fully reconciled.

Users should resolve checklist blockers before trying to close the request.

## Accounting Review Queue

Accounting users should use the quick tabs first:

- All Pending
- Over-Budget
- Missing Receipt
- Amendment Required
- Duplicate Card
- Returned
- Resolved

Each row now shows:

- Source request or card transaction.
- Requester / department / project.
- Reason.
- Policy action.
- Aging.
- Severity.
- Required action.
- Status.

Accounting users should open the detail page for decisions rather than trying to resolve complicated items directly from the queue.

## Accounting Review Detail

The detail page is the main place to make review decisions.

Users should review:

- Issue Summary.
- Source Request / Card Transaction.
- Financial Impact.
- Policy Result.
- Receipt / Attachment Status.
- Decision History / Audit Context.

Requester self-review is still not allowed.

## Card Transaction Reconciliation

Accounting users should use the Card Transaction Detail page to reconcile company card transactions.

Important fields:

- Transaction Amount.
- Allocated Amount.
- Unallocated Amount.
- Match Status.
- Open Reviews.
- Duplicate Warning.

The Unallocated Amount is the most important number.

Mark Reviewed is only available when:

- The transaction is fully matched.
- No unresolved accounting review item exists.

If Mark Reviewed is disabled, users should read the disabled reason shown next to the button.

## Deployment Note For GoDaddy

After deploying CSS or JavaScript changes to GoDaddy:

1. Pull/update the repository in cPanel Git Version Control.
2. Deploy HEAD Commit.
3. Confirm `collectstatic` has run.
4. Restart the Python app if needed.
5. Hard-refresh the browser if old static files are cached.

If dropdown hover still does not work after deployment, first confirm the deployed `static/css/app.css` contains the `.nav-menu:hover .nav-dropdown` rule.

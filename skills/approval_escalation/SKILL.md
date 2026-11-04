---
name: approval_escalation
description: Procedural knowledge for evaluating when and how to escalate stalled expense approvals to backup approvers and corporate administrators.
trigger_conditions:
  - An expense report or access request exceeds its initial nudge SLA threshold.
  - The primary designated approver has not responded within the grace period.
  - The status is currently Nudged and requires high-priority follow-up.
when_not_to_trigger:
  - The expense report is still within its initial review SLA window (fresh).
  - The expense report is already marked Resolved.
  - A previous escalation was dispatched and is awaiting senior executive review.
---

# Approval Escalation Skill

## Purpose
This skill provides procedural knowledge and execution guidelines for identifying stalled enterprise approval workflows, dispatching reminders, and escalating unresponsive approvals to designated backup approvers or corporate administrators.

## When to Load
This skill should be loaded at runtime during autonomous engine ticks when an expense report or access request exceeds its initial review SLA window or when evaluating an escalation candidate (`status == NUDGED`).

## Required Context
Before executing an escalation procedure, the agent runtime must verify:
- Report ID, submitter identity, and original submission timestamp
- Current report status (`PENDING` or `NUDGED`)
- Primary approver email address
- Backup approver email address from the corporate directory
- Expense amount and currency for threshold classification

## Nudge Procedure
1. Check if submission age exceeds `nudge_threshold_seconds`.
2. Draft a polite notification reminder addressed to the primary approver.
3. Validate that recipient email matches the registered primary approver.
4. Transition report status from `PENDING` to `NUDGED` and set `last_nudged_at`.

## Escalation Procedure
1. Check if time since last nudge exceeds `escalation_threshold_seconds`.
2. Retrieve backup approver from the corporate registry.
3. If no backup approver is registered, fallback to `admin_fallback_email`.
4. Draft an urgent escalation notification detailing the stalled duration.
5. Validate recipient email against registry authority.
6. Transition report status from `NUDGED` to `ESCALATED` and set `escalated_at`.

## Progressive Disclosure References
For high-value expenses (>= $5,000 USD) or special corporate compliance reviews, load the Level-2 detailed reference:
- `references/escalation_policy.md`

## Safety Constraints & CRITICAL BOUNDARY
> **CRITICAL BOUNDARY**:
> The agent drafts notification language and identifies the escalation candidate based on rules; deterministic code verifies the recipient against the corporate registry and executes state changes.

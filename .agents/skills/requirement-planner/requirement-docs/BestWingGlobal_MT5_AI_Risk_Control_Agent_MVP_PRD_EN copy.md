# HKMBBestWingGlobal MT5 AI Risk Control Agent MVP

**PRD + Technical Implementation Plan**
**Telegram Bot Lightweight Workflow Edition**

> **Version:** 1.0
> **Date:** 2026-04-28
> **Prepared for:** BestWingGlobal Risk Control / Technology / Customer Service Teams

---

## Document Summary

This document defines an AI Risk Control Agent MVP solution for an MT5 broker. Using a Telegram Bot as a lightweight risk control workstation, it implements account trade scanning, abnormal behavior identification, risk case alerts, manual review, temporary risk control actions, customer email drafts, and customer service follow-up reminders.

The core value of the MVP is: **get the risk control feedback loop running first.** Through a rules engine, trade feature computation, and LLM text generation, the system helps the risk control team reduce manual screening time, improve evidence chain quality, and identify high-risk accounts before withdrawal.

---

## Table of Contents

1. [Product Positioning and Goals](#1-product-positioning-and-goals)
2. [MVP Scope and Out-of-Scope Items](#2-mvp-scope-and-out-of-scope-items)
3. [User Roles and Permissions](#3-user-roles-and-permissions)
4. [Core Business Workflow](#4-core-business-workflow)
5. [Scanning Strategy](#5-scanning-strategy)
6. [Risk Identification Model](#6-risk-identification-model)
7. [Telegram Bot Workstation Design](#7-telegram-bot-workstation-design)
8. [Risk Control Action Design](#8-risk-control-action-design)
9. [Email and Customer Service Follow-up Agent](#9-email-and-customer-service-follow-up-agent)
10. [System Architecture and Modules](#10-system-architecture-and-modules)
11. [Database Design](#11-database-design)
12. [APIs and Bot Commands](#12-apis-and-bot-commands)
13. [Agent Responsibilities](#13-agent-responsibilities)
14. [Case State Machine](#14-case-state-machine)
15. [Tech Stack and Deployment](#15-tech-stack-and-deployment)

---

## 1. Product Positioning and Goals

### 1.1 Product Name

- **English Name:** MT5 AI Risk Control Agent - Telegram MVP
- **Chinese Name:** MT5 AI 风控 Agent 轻量工作流系统

### 1.2 Product Positioning

This system is positioned as an internal risk control assistance system for the broker. The first version completes risk control alerts and review interaction through the Telegram Bot, while the backend is responsible for data collection, risk analysis, case logging, and action execution.

```
MT5 / CRM / Payment Data
         ↓
Risk Detection Backend
         ↓
Risk Case Generator
         ↓
Telegram Bot Review
         ↓
Risk Action / Email / CS Follow-up
```

### 1.3 Product Goals

- Automatically scan MT5 account trading behavior to identify suspected latency arbitrage, scalping violations, swap arbitrage, and bonus / credit abuse.
- Trigger risk control scans in real time at key events such as withdrawal applications, large profits, and high-frequency trading.
- Push risky accounts, risk scores, evidence summaries, and recommended actions to the Telegram risk control group.
- Risk control staff perform manual review and temporary risk control operations through Telegram buttons.
- Automatically generate customer email drafts and prompt customer service to follow up using unified messaging.
- Retain a complete case log to lay the foundation for subsequent dashboards, model training, and compliance retrospectives.

---

## 2. MVP Scope and Out-of-Scope Items

### 2.1 In Scope for MVP

| Module | Feature in This Phase | Notes |
| --- | --- | --- |
| Data Ingestion | Read MT5 account, order, trade, position, swap, and profit data. | Subject to broker-granted permissions, can use MT5 Python integration, Manager API, or a database replica. |
| Scheduled Scan | Scan active accounts every 6 hours. | Used for baseline behavior profiling and periodic risk discovery. |
| Event-Triggered Scan | Real-time triggers on withdrawal requests, large profits, and high-frequency trading. | Used to prevent risky accounts from completing withdrawals before being detected. |
| Risk Detection | Identify 4 categories of abnormal behavior. | latency arbitrage, scalping, swap arbitrage, bonus / credit abuse. |
| Telegram Workstation | Risk alerts, evidence viewing, button-based review. | |
| Risk Control Actions | Watch, pause withdrawal, restrict opening positions, draft trade suspension. | High-risk actions require manual confirmation. |
| Email / CS | Generate email drafts, create customer service follow-up reminders. | Avoid inconsistent messaging from customer service. |
| Case Archiving | Record AI detection, manual review, action execution, and final status. | Forms data for subsequent model optimization. |

### 2.2 Out of Scope for This Phase

- No full Dashboard or complex BI reports.
- No customer-facing front-end pages.
- No automatic profit confiscation, automatic permanent banning, or automatic account closure.
- No full machine learning training platform.
- AI does not directly make the final determination of violations.
- Do not display full KYC, ID card, bank card, address, or other sensitive information in Telegram.

---

## 3. User Roles and Permissions

| Role | Permission Scope | Restrictions |
| --- | --- | --- |
| **Risk Admin** | View all cases; approve high-risk actions; send formal emails; modify thresholds; view audit logs. | High-risk operations still require recorded confirmation reasons. |
| **Risk Officer** | View risk alerts; view evidence; add to watchlist; review withdrawal pauses; generate email drafts; mark false positives; escalate to compliance. | Restricting opening, suspending trading, and sending formal emails require secondary confirmation or supervisor approval. |
| **Customer Support** | Receive customer follow-up reminders; view permitted response scripts; mark as followed up. | May not view full algorithm details or internal risk scores; may not promise withdrawal approval. |
| **System Admin** | Deploy, maintain, and monitor the system; handle interface errors and logs. | Does not participate in risk control business judgment. |

---

## 4. Core Business Workflow

### 4.1 Main Workflow

```
1.  Backend reads data from MT5 / CRM / Payment systems
2.  Risk Feature Engine computes account trade features
3.  Risk Detection Engine generates risk score
4.  Case Management Service creates the risk case
5.  Telegram Bot pushes the risk alert
6.  Risk control staff review evidence and click buttons to handle
7.  Action Executor performs temporary risk control actions
8.  Email Draft Agent generates customer email draft
9.  CS Follow-up Agent creates customer service follow-up task
10. Audit Agent archives the case and operation records
```

### 4.2 Minimum Feedback Loop

The MVP minimum loop is not "AI auto-penalty," but **"AI detects risk + manual confirmation + system execution + unified record-keeping."**

| Stage | System Behavior | Human Role |
| --- | --- | --- |
| Detect | Automatically scan trading accounts and generate risk cases. | No human action required. |
| Alert | Telegram pushes risk summary, evidence, and recommended action. | Risk control staff receive alert. |
| Review | Bot provides View Evidence, Watch, Pause Withdrawal, etc. buttons. | Risk control staff confirm handling method. |
| Execute | Backend calls risk control action interface and writes log. | High-risk actions confirmed by supervisor. |
| Notify | Email Agent generates customer notification draft. | Sent after manual approval. |
| Follow-up | CS group receives follow-up task and unified messaging. | CS completes customer communication. |
| Archive | System records the final handling result. | Risk control team retrospective. |

---

## 5. Scanning Strategy

A hybrid strategy of **"deep scan every 6 hours + real-time scan on key events"** is recommended. Relying on 6-hour scans alone tends to result in after-the-fact discovery, especially during withdrawal applications, large profits, and news arbitrage windows.

### 5.1 Full-Account Scan Every 6 Hours

- Recommended scan times: 00:00, 06:00, 12:00, 18:00.
- Each scan covers: account history baselines for the past 6 hours, past 24 hours, past 7 days, and past 30 days.
- Suitable for identifying: scalping, swap arbitrage, bonus abuse, long-term account profiling, and abnormal deviations.

### 5.2 Real-Time Trigger Scans

| Trigger Event | Trigger Condition Examples | Recommended Action |
| --- | --- | --- |
| Withdrawal Request | Customer creates a withdrawal request. | Immediately scan trades from the past 7 / 30 days; if high-risk, pause withdrawal review and push to Telegram. |
| Short-term Abnormal Profit | 1-hour profit > 20% of balance; 6-hour profit > 50% of balance; 24-hour profit > 100% of balance. | Trigger `abnormal_profit_scan`. |
| Abnormal High-Frequency Trading | 15-min trades > 30; 1-hour trades > 100; 6-hour trades > 300. | Trigger `scalping / latency check`. |
| News Window Anomaly | High-frequency short-position profits within 5–15 minutes around major data releases. | Trigger `news_window_scan`. |
| Post-Bonus / Credit Anomaly | High-leverage, high-frequency, or hedging trades within 24 hours after receiving a bonus. | Trigger `bonus_abuse_check`. |

---

## 6. Risk Identification Model

The first MVP version will use a **rules engine + feature scoring + LLM evidence summarization.** Do not rely on complex machine learning models in the first version, as it would increase development cost and reduce explainability.

### 6.1 Risk Types

| Risk Type | Business Meaning | First-Version Detection Focus |
| --- | --- | --- |
| **Latency Arbitrage** | Customer profits by exploiting quote delays, server delays, or liquidity delays. | Extremely short positions, post-news price-jump window trading, abnormal positive slippage, profits concentrated during quote-anomaly periods. |
| **Scalping Violation** | Customer trades with extremely short positions, high frequency, small profits, and high win rate; whether it constitutes a violation depends on the customer agreement. | Short-position ratio, trading density, fixed pattern, repetition, instrument concentration. |
| **Swap Arbitrage** | Customer profits primarily from positive swap or rollover mechanisms rather than normal market movement. | Swap profit ratio, positions held across rollover, closing after swap is posted, low-risk hedging. |
| **Bonus / Credit Abuse** | Customer arbitrages using bonuses, credits, agent relationships, or multi-account hedging. | Same IP/device/wallet/IB, multi-account opposing trades, rapid trading after bonus, withdrawal after profit. |

### 6.2 Core Trade Features

| Feature Name | Meaning | Purpose |
| --- | --- | --- |
| `trade_count_6h` / `24h` | Number of trades in 6 hours / 24 hours. | Identify high-frequency trading and abnormal trade density. |
| `median_holding_time` | Median order holding time. | Identify short-position scalping / latency. |
| `short_holding_ratio` | Ratio of orders held below 30 or 60 seconds. | Core indicator of short-position pattern. |
| `win_rate` | Win rate. | Combined with small profits and high frequency to judge abnormal patterns. |
| `avg_profit_per_trade` | Average profit per trade. | Identify small-profit, high-win-rate patterns. |
| `positive_slippage_ratio` | Positive slippage ratio or multiple. | Identify possible latency trading. |
| `news_window_profit_ratio` | Share of profit from news windows. | Identify news arbitrage or quote-delay profit. |
| `swap_profit_ratio` | Share of swap income in total profit. | Identify swap arbitrage. |
| `bonus_usage_ratio` | Bonus / credit contribution to trade margin or profit. | Identify bonus abuse. |
| `linked_account_count` | Number of linked accounts. | Identify multi-account and group arbitrage. |

### 6.3 Rule Examples

**Latency Arbitrage Rule Example**

```
IF:
- trade_count_6h >= 30
- median_holding_time <= 30 seconds
- profitable trades within quote spike window >= 60%
- positive_slippage_ratio >= 3x peer average
THEN:
- risk_type = latency_arbitrage
- risk_score >= 85
```

**Scalping Rule Example**

```
IF:
- trade_count_24h >= 100
- short_holding_ratio_60s >= 70%
- win_rate >= 75%
- repeated lot size / TP / SL pattern = true
THEN:
- risk_type = suspected_scalping_pattern
- risk_score >= 75
```

**Swap Arbitrage Rule Example**

```
IF:
- swap_profit_ratio_30d >= 60%
- positions repeatedly opened before rollover
- positions closed after swap posting
- price movement PnL is low
THEN:
- risk_type = swap_arbitrage
- risk_score >= 80
```

**Bonus Abuse Rule Example**

```
IF:
- bonus_used = true
- high leverage / high frequency trading within 24h
- linked accounts share IP / device / wallet / IB
- opposite trades exist among linked accounts
- withdrawal requested soon after profit
THEN:
- risk_type = bonus_abuse
- risk_score >= 85
```

### 6.4 Risk Levels and Recommended Actions

| Score | Level | System-Recommended Action |
| --- | --- | --- |
| 0–39 | **Low** | Log only, do not push. |
| 40–59 | **Watch** | Add to watchlist; may skip notifying the risk control group. |
| 60–74 | **Medium** | Push to Telegram; manual review. |
| 75–89 | **High** | Recommend pausing withdrawal review / restricting opening; manual confirmation required. |
| 90–100 | **Critical** | Recommend immediately pausing withdrawal review + restricting opening + high-priority manual review. |

---

## 7. Telegram Bot Workstation Design

The Telegram Bot is the lightweight review entry point for the MVP phase. It does not perform analysis directly; it receives risk cases from the backend, pushes summaries to risk control staff, and accepts button operations.

### 7.1 Recommended Telegram Groups

| Group | Purpose | Visible Content |
| --- | --- | --- |
| **Risk Alerts Group** | High-risk account alerts and manual review entry point. | Account number, risk level, evidence summary, action buttons. |
| **Risk Action Log Group** | Records who took which action when. | Case id, account number, action, operator, time, result. |
| **CS Follow-up Group** | Customer service follow-up reminders. | Customer account, email status, CS messaging, prohibited statements. |

### 7.2 Risk Alert Message Template

```
Risk Alert: High-Risk Trading Pattern Detected

Case ID: RISK-20260428-0001
Account: 123456
Client Code: C-88912
Group: Standard
Risk Level: High
Risk Score: 87/100
Risk Type: Latency Arbitrage + Scalping Pattern

Trigger: 6-hour scheduled scan

Evidence:
- 86 trades in the past 6 hours
- 74% of orders held under 30 seconds
- Profitable orders concentrated 1–3 seconds after quote spikes
- Positive slippage ratio 4.2x higher than peer accounts in the same group
- Primary trading instrument: XAUUSD

Suggested Action: Restrict opening new positions and hold withdrawal review.

Actions: [View Evidence] [Watch Only] [Pause Withdrawal]
         [Restrict Opening] [Generate Email] [Escalate] [Ignore]
```

### 7.3 Button Functions

| Button | Function | Suggested Permission |
| --- | --- | --- |
| View Evidence | View detailed evidence. | Risk Officer / Admin |
| Watch Only | Add to watchlist; does not affect customer trading. | Risk Officer / Admin |
| Pause Withdrawal | Pause withdrawal review pending manual re-review. | Risk Officer / Admin |
| Restrict Opening | Restrict opening new positions; allow closing. | Admin or Officer with secondary confirmation |
| Full Suspend | Suspend trading. | Admin only |
| Generate Email | Generate customer email draft. | Risk Officer / Admin |
| Assign CS | Create customer service follow-up task. | Risk Officer / Admin |
| Ignore | Mark as false positive. | Risk Officer / Admin |
| Escalate | Escalate to compliance or supervisor. | Risk Officer / Admin |

### 7.4 Secondary Confirmation Mechanism

For high-impact actions such as restricting opening, suspending trading, and sending formal emails, the Telegram Bot **must** require secondary confirmation.

```
Confirm Action

Account: 123456
Action: Restrict opening new positions
Effect: Client cannot open new positions, but can close existing positions.

Please confirm: [Confirm Restrict Opening] [Cancel]
```

---

## 8. Risk Control Action Design

### 8.1 Actions Supported in MVP

| Action | Business Meaning | Auto-Executable? |
| --- | --- | --- |
| Watch Only | Account enters watchlist. | Can be automatic or manual. |
| Pause Withdrawal | Pause withdrawal request or move to manual review. | High-risk withdrawals can auto-enter manual review, but must be logged. |
| Restrict Opening | Prohibit opening new positions; allow closing. | Manual confirmation required. |
| Full Suspend | Suspend trading. | Supervisor approval only. |
| Generate Email Draft | Generate customer email draft. | Can be auto-generated, but manual confirmation required before sending. |
| Assign CS Follow-up | Create customer service follow-up task. | Can be auto-created. |
| Ignore / False Positive | Mark as false positive. | Manual confirmation. |

### 8.2 Execution Principles

- AI may identify risks, generate evidence summaries, recommend actions, and generate email drafts.
- AI should **not** directly make final penalty decisions.
- Actions such as restricting opening, suspending trading, formally sending customer emails, adjusting profits, and closing accounts must be manually confirmed.
- All actions must record the operator, time, reason, execution result, and failure reason.

---

## 9. Email and Customer Service Follow-up Agent

### 9.1 Email Generation Principles

During the initial review stage, emails should avoid conviction-style language. Recommended phrasing includes *"internal review,"* *"trading patterns detected,"* and *"temporary restriction pending review."* Do not write *"you violated our rules."*

### 9.2 MVP Email Templates

**Template 1 — Trading Activity Review Notice**

```
Subject: Account Trading Activity Review Notice

Dear Client,

We are writing to inform you that your trading account has been flagged for an internal
review due to certain trading patterns detected by our risk monitoring system.

During this review period, certain account functions may be temporarily restricted in
accordance with our trading terms and risk control procedures.

Please note that this review does not represent a final determination of violation. Our
risk control team will complete the review and notify you of the result.

Best regards,
Risk Control Department
BestWingGlobal
```

**Template 2 — Withdrawal Request Under Review**

```
Subject: Withdrawal Request Under Review

Dear Client,

Your withdrawal request is currently under internal review due to recent trading activity
on your account.

This review is part of our standard risk control procedure. We will notify you once the
review has been completed.

Best regards,
Risk Control Department
BestWingGlobal
```

### 9.3 Customer Service Follow-up Reminder Template

```
CS Follow-up Required

Case ID: RISK-20260428-0001
Account: 123456
Client Code: C-88912
Status: Risk review notice generated
Priority: High

Suggested Response:
Please inform the client that the account is under internal review.
Do not confirm any violation before the risk team completes the review.

Do Not Say:
- Do not say the client has violated rules.
- Do not promise withdrawal approval.
- Do not disclose detailed detection logic.
- Do not discuss internal risk score.

Actions: [Mark Followed Up] [Escalate to Risk]
```

---

## 10. System Architecture and Modules

### 10.1 MVP Architecture

```
        MT5 / CRM / Payment
                 ↓
        Data Collector Service
                 ↓
        Risk Feature Engine
                 ↓
        Risk Detection Engine
                 ↓
        Case Management Service
                 ↓
        Telegram Bot Service
        ↓        ↓        ↓
  Risk Group  Action Log  CS Group
                 ↓
        Action Executor
                 ↓
   Email / CRM / MT5 Adapter
```

### 10.2 Technical Modules

| Module | Responsibility | Notes |
| --- | --- | --- |
| **Data Collector** | Read MT5, CRM, Payment, login logs, bonus / credit records. | First confirm which APIs or database access the broker can provide. |
| **Risk Feature Engine** | Convert raw trade records into scoreable features. | Features must be traceable back to the original orders. |
| **Risk Detection Engine** | Execute rule scoring and generate risk type and risk level. | First version is rule-based. |
| **Risk Evidence Agent** | Convert complex data into risk-control-readable evidence. | LLM is used mainly for summarization, not final adjudication. |
| **Case Management Service** | Create, update, and close risk cases. | Subsequent dashboards can reuse this directly. |
| **Telegram Bot Service** | Send alerts, receive button presses, validate permissions, update status. | All callbacks are written to the log. |
| **Action Executor** | Call pause withdrawal, watchlist, restrict opening, etc. interfaces. | Use adapters to integrate with broker systems. |
| **Email Draft Agent** | Generate email drafts based on the case. | Manual confirmation required before sending. |
| **CS Follow-up Agent** | Generate CS tasks and messaging reminders. | Avoid CS misstatements. |

---

## 11. Database Design

The following is the minimum recommended database structure for the MVP. The technical team can adjust it based on the existing broker backend.

```sql
accounts (
  id, mt5_login, client_id, account_group, leverage,
  balance, equity, credit, country, ib_id,
  status, created_at, updated_at
)
```

```sql
trades (
  id, mt5_login, order_id, deal_id, symbol, side, volume,
  open_time, close_time, holding_seconds,
  open_price, close_price, profit, commission, swap, slippage,
  created_at
)
```

```sql
risk_cases (
  id, case_id, mt5_login, risk_type, risk_score, risk_level,
  trigger_type, evidence_json, suggested_action, status,
  reviewer_id, reviewer_action, created_at, updated_at
)
```

```sql
risk_actions (
  id, case_id, action_type, action_status, performed_by,
  performed_at, result_json, failure_reason
)
```

```sql
telegram_users (
  id, telegram_user_id, name, role, allowed_actions,
  status, created_at
)
```

```sql
email_logs (
  id, case_id, mt5_login, email_type, subject, body,
  status, approved_by, sent_at, created_at
)
```

---

## 12. APIs and Bot Commands

### 12.1 Internal API Examples

**Create Risk Case**

```http
POST /risk-cases
```

```json
{
  "mt5_login": "123456",
  "risk_type": "latency_arbitrage",
  "risk_score": 87,
  "risk_level": "high",
  "trigger_type": "scheduled_scan",
  "evidence": {
    "trade_count_6h": 86,
    "short_holding_ratio": 0.74,
    "positive_slippage_ratio": 4.2
  },
  "suggested_action": "restrict_opening_pause_withdrawal"
}
```

**Execute Action on a Case**

```http
POST /risk-cases/{case_id}/actions
```

```json
{
  "action_type": "pause_withdrawal",
  "requested_by": "telegram_user_id",
  "confirmed": true
}
```

**Generate Email Draft**

```http
POST /risk-cases/{case_id}/email-draft
```

```json
{
  "email_type": "trading_activity_review_notice",
  "language": "en"
}
```

### 12.2 Telegram Bot Commands

| Command | Purpose |
| --- | --- |
| `/status` | View system status. |
| `/today` | View number of risk cases today. |
| `/pending` | View pending cases. |
| `/case RISK-20260428-0001` | View a specific case. |
| `/account 123456` | View account risk summary. |
| `/help` | View command help. |

---

## 13. Agent Responsibilities

| Agent | Responsibility |
| --- | --- |
| **Scheduled Scan Agent** | Scans active accounts every 6 hours, extracts trade features, and calls the risk detection engine. |
| **Withdrawal Scan Agent** | Listens for withdrawal requests and immediately scans the account's trades from the past 7 / 30 days. |
| **Abnormal Profit Agent** | Monitors short-term profit anomalies and triggers single-account scans. |
| **High Frequency Agent** | Identifies large numbers of orders within a short time and abnormal high-frequency patterns. |
| **Risk Evidence Agent** | Organizes trade features and rule-hit results into evidence summaries. |
| **Telegram Review Agent** | Handles bot messages, button callbacks, permission validation, and status updates. |
| **Email Draft Agent** | Generates customer email drafts based on risk type. |
| **CS Follow-up Agent** | Generates CS follow-up reminders, suggested messaging, and prohibited statements. |
| **Audit & Learning Agent** | Archives cases, manual judgment results, and false positive data to prepare data for subsequent model optimization. |

---

## 14. Case State Machine

```
detected
   ↓
pushed_to_telegram
   ↓
under_review
   ↓
action_pending_confirmation
   ↓
action_executed
   ↓
email_drafted
   ↓
email_approved
   ↓
email_sent
   ↓
cs_follow_up_required
   ↓
cs_followed_up
   ↓
closed
```

**Exception branch states include:** `ignored_false_positive`, `escalated_to_compliance`, `manual_review_required`, `action_failed`, `email_rejected`.

---

## 15. Tech Stack and Deployment

| Layer | Recommended Technology | Notes |
| --- | --- | --- |
| **Backend** | Python + FastAPI | Suitable for rapid development of risk control APIs and services. |
| **Scheduler** | APScheduler / Celery Beat | Executes 6-hour scans and daily tasks. |
| **Queue** | Redis / RabbitMQ | Handles scanning, Telegram pushes, and email tasks asynchronously. |
| **Database** | PostgreSQL | Stores account snapshots, trade features, cases, and audit logs. |
| **Telegram Bot** | python-telegram-bot / aiogram | Implements inline keyboards and callbacks. |
| **LLM** | OpenAI / Azure OpenAI / local LLM | Used for evidence summaries, email drafts, and CS messaging. |
| **Deployment** | Docker + Linux Server | Convenient for internal deployment and scaling. |
| **Monitoring** | Sentry / Prometheus / Log service | Monitor task failures, API failures, and bot callback errors. |

---

*Confidential — Internal Proposal Draft*

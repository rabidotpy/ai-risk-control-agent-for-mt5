# BestWingGlobal MT5 AI Risk Control Agent MVP PRD

## Telegram Bot Lightweight Workflow Version

Version 1.0 | 2026-04-28

---

# Product Summary

An internal AI-assisted risk control system for an MT5 broker.

Uses a Telegram Bot as the operator console for:

- Trading account scanning
- Abnormal behavior detection
- Risk case alerts
- Manual review workflows
- Temporary risk actions
- Customer email drafts
- Customer support follow-up reminders

Core MVP goal:

> Close the risk-control loop quickly through AI detection + human approval + action execution + audit logs.

---

# Core Product Requirements

## 1. Data Integration

The system must connect to:

- MT5 accounts
- Orders / deals / positions
- CRM customer data
- Payment / withdrawal systems
- Login logs
- Bonus / credit records

---

## 2. Risk Scanning Engine

### Scheduled Scan

Run every 6 hours:

- 00:00
- 06:00
- 12:00
- 18:00

Analyze historical windows:

- Last 6 hours
- Last 24 hours
- Last 7 days
- Last 30 days

### Event Trigger Scan

Instant scan when:

- Withdrawal request submitted
- Abnormal short-term profit detected
- High-frequency trading detected
- News-event trading window triggered
- Suspicious bonus usage detected

---

## 3. Risk Detection Types

First MVP version must support:

1. Latency Arbitrage
2. Scalping Violation
3. Swap Arbitrage
4. Bonus / Credit Abuse

---

## 4. Risk Scoring System

Score range: **0–100**

| Score | Level |
|------|------|
| 0–39 | Low |
| 40–59 | Watch |
| 60–74 | Medium |
| 75–89 | High |
| 90–100 | Critical |

---

## 5. Telegram Bot Console

Push alert message should include:

- Case ID
- Account ID
- Risk score
- Risk level
- Risk type
- Evidence summary
- Suggested action

### Action Buttons

- View Evidence
- Watch Only
- Pause Withdrawal
- Restrict Opening
- Full Suspend
- Generate Email
- Assign CS
- Ignore
- Escalate

---

## 6. Manual Approval Rules

The following actions must require manual confirmation:

- Restrict opening new positions
- Suspend trading
- Send official emails
- Profit adjustment
- Close account

---

## 7. Email Agent

Generate compliant customer notices such as:

- Account trading activity under review
- Withdrawal request under review
- Temporary restrictions applied

Avoid direct accusation wording.

---

## 8. Customer Support Agent

Provide CS reminders with:

- Approved response script
- Forbidden statements
- Follow-up status tracking

---

## 9. Case Management Workflow

detected → pushed_to_telegram → under_review → action_executed → email_sent → cs_follow_up → closed

System must keep complete audit logs.

---

## 10. Recommended Tech Stack

| Layer | Recommended Tech |
|------|------------------|
| Backend | Python + FastAPI |
| Scheduler | APScheduler / Celery Beat |
| Queue | Redis / RabbitMQ |
| Database | PostgreSQL |
| Bot | python-telegram-bot / aiogram |
| LLM | OpenAI / Azure OpenAI / Local LLM |
| Deployment | Docker + Linux Server |
| Monitoring | Sentry / Prometheus |

---

# Final Conclusion

This PRD is practical, commercially valid, and executable for a broker risk-control MVP.

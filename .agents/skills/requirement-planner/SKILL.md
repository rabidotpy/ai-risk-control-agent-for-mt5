---
name: requirement-planner
description: Plan and manage project requirements. Use when asked to create, update, or review project requirements.
---

# About Requirement Planner Skill

This SKILL is about AI assisted risk control for a trading platform, specifically for MT5. The requirements involve detecting suspicious patterns, assessing risks, and taking appropriate actions based on the detected risks. The workflow involves both human and developer interactions, with the use of curl requests to analyze data and update the state of cases. The goal is to ensure that the risk control measures are effective in identifying and mitigating risks in the trading environment.
A developer named Alex will assist me in providing API's but for now they're unknown to us. We will have to make assumptions about the data and the API's based on the information provided in the requirement documents and the conversation with ChatGPT. The requirements also mention that this is not for AIO but for another unnamed product, which adds another layer of complexity to our planning. We will need to consider how the requirements fit into the overall product and how they will be implemented in a real-world trading system or CRM.

# Requirement Planner Skill

To plan requirements, you have to do the following steps:

1. Read the requirement-docs folder where you will find all the documents related to the requirements. These documents will give you an overview of the project and its requirements.
2. Read the conversation-with-chatgpt.md file where you will find a conversation between a human and ChatGPT. This conversation will give you insights into the requirements and the thought process behind them.
3. After reading the documents and the conversation, you will have a clear understanding of the requirements. You can then create a plan to manage these requirements effectively.
4. The files inside requirement-docs folder might not provide you with all the information you need, so you might have to do some additional research to fill in the gaps. This could involve looking into similar projects, understanding the trading platform (MT5), and researching risk control measures in trading environments.
5. Based on your understanding and research, create a detailed plan outlining the steps to implement the requirements, including any assumptions made and potential risks identified. Create files in side updated-plan folder where filename should be plan-<dd-mm-yyyy>.md and write down your plan in those files. Keep old plan files for reference, comparison and learning. The file must include a reason of why this new plan file is being created e.g. it could be created because of new information, change in requirements, or a need to clarify the existing plan. This will help you track the evolution of your plan and understand the rationale behind each version.
6. Regularly review and update your plan as you gather more information and as the project progresses.
7. I will have to communicate this plan with Alex and questions regarding API's and implementation details. Make sure to document these communications and any decisions made based on them in the updated-plan files for future reference.
8. Prepare a list of next steps and action items based on the plan, and assign them to either me or Alex as appropriate. This will help ensure that the plan is executed effectively and that all tasks are accounted for. Regularly review the progress of these action items and adjust the plan as necessary to keep the project on track. 

# Learning
1. Name of the product is "BestWing Global MT5 AI Risk Control Agent MVP". This product is focused on providing AI-assisted risk control for the MT5 trading platform. The product aims to detect suspicious patterns, assess risks, and take appropriate actions to mitigate those risks in a trading environment.
2. We also need to discover the parameters of risk creation. We need to list them all down under the section "Concrete Parameters of Risk Creation". This will help us understand the factors that contribute to risk in the trading environment and how we can detect and mitigate those risks effectively. Understanding these parameters will be crucial in designing the AI risk control agent and ensuring that it can accurately identify and respond to potential risks in the MT5 trading platform.
3. The purpose of every risk analysis in this system is to detect ACTIVITY PATTERNS, not financial impact. The same abuse pattern is the same abuse pattern whether the trader is on a $100 account or a $100,000 account. Detect by counts, ratios, fractions, holding times, repetitions, and timing. Do NOT use absolute dollar floors, trade size minimums, or profit magnitude thresholds as detection criteria. Ratios of two dollar quantities (which are scale-invariant) are fine. Absolute dollar amounts are not. This rule applies to every existing rule, every new rule, and every refinement. When in doubt, ask: "would this rule fire on a small account doing the same pattern?" If no, the rule is wrong.
4. The exception to learning 3 is the `profitable_client_pattern` risk type, which is operational (not compliance) and is specifically about extraction RATE in dollars per day. There, an absolute threshold ($100/day, equivalent to $1,000 over 10 days) is the actual signal because the broker's question is "how fast is this client costing me money?". Read the dedicated section in this skill before tweaking that rule.
5. Architecture decided 2026-05-17: rule TRUE/FALSE is deterministic Python in `app/rules/<risk>.py`. The LLM is called only for narrative (`summary`, `behavior_summary`, `evidence_description_list`). The LLM never decides whether a rule fires and never proposes a score. Same input always produces the same score. This was a structural fix after a real false-positive on client account 250030 where the LLM-evaluated rules tripped on a martingale grid trader.
6. There are 5 risk types in production as of 2026-06-01: `latency_arbitrage`, `scalping`, `swap_arbitrage`, `bonus_abuse`, and `profitable_client_pattern`. The first four are compliance signals (catch abusers). The fifth is an operational signal (route consistently profitable clients to A-book). Action ladders and downstream consumers may want to treat them differently.
7. Default alert thresholds are `callback_min_score=60` and `llm_narrate_min_score=60`. So Telegram only sees findings where at least one risk for an account scores 60+, and the LLM is only called for risks crossing the same bar. The two gates being equal keeps the system predictable.
8. The `bid_at_open` / `ask_at_open` fields on `Trade` are no longer used by any rule. They are still required by the Pydantic schema for backwards compatibility with Alex's existing payload. To be removed in a follow-up schema cleanup.



# Concrete Parameters of Risk Creation

This is the current, live picture. For per-sub-rule plain-English descriptions, see `research/Values_to_sub_rules_mapping.md`. For the data-status matrix (what's live, what's data-capped), see `research/data_requirements_matrix.md`.

## 5 risk types, 21 sub-rules

| Risk type | Purpose | Sub-rules | Status |
| --- | --- | --- | --- |
| `latency_arbitrage` | Detect trader exploiting a faster price feed | 4 | All LIVE |
| `scalping` | Detect short-hold high-frequency trading (contract-bound) | 4 | All LIVE |
| `swap_arbitrage` | Detect overnight-interest farming | 4 | All LIVE |
| `bonus_abuse` | Detect promo bonus extraction (often via linked accounts) | 5 | 3 LIVE, 2 DATA-CAPPED (linked-accounts feed pending) |
| `profitable_client_pattern` | Operational: flag profitable clients for A-book routing | 4 | All LIVE |

## Scoring and bands (shared across all 5 risks)

- Score = `round(100 / N × count_true)` where N is the number of sub-rules for that risk.
- For 4-sub-rule risks the possible scores are 0, 25, 50, 75, 100. Medium (60–74) is unreachable.
- For the 5-sub-rule bonus risk, possible scores are 0, 20, 40, 60, 80, 100.
- Bands: low (0–39), watch (40–59), medium (60–74), high (75–89), critical (90+).

## Per-trade data fields used by current rules

`id`, `login`, `group`, `symbol`, `volume`, `side`, `open_time`, `close_time`, `open_price`, `close_price`, `stop_loss`, `take_profit`, `swaps`, `commission`, `profit`, `comment`.

`bid_at_open` and `ask_at_open` are still required by the schema but no rule reads them.

## Data still missing from Alex

- **Linked-accounts feed** — blocks 2 of 5 bonus-abuse sub-rules.
- **Confirmation that `commission` and `swaps` are populated** for non-Islamic groups (currently zero on the only real account we have access to, which is on `real\group-islamic` and may legitimately have no swap or commission).

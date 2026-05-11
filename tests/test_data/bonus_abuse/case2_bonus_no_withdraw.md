# Bonus Abuse — Case 2: bonus + trading, but no withdrawal, no linked accounts

**Expected**: 2/5 TRUE → `risk_score = 40`, `risk_level = watch`.

| Sub-rule                                       | Expected | Why                                  |
| ---------------------------------------------- | -------- | ------------------------------------ |
| `bonus_received_in_window`                     | TRUE     | one bonus event                      |
| `trades_after_bonus_in_window >= 8`            | TRUE     | 8 trades after the bonus             |
| `linked_account_count >= 2`                    | FALSE    | no linked accounts reported          |
| `linked_with_opposing_trades >= 1`             | FALSE    | no linked accounts reported          |
| `withdrawal_after_bonus_in_window`             | FALSE    | no withdrawal in the window          |

A new client trading their bonus genuinely. Worth watching, not blocking.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80402,
      "trigger_type": "bonus_check",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "bonus": [
        {"id": 1, "login": 80402, "group": "real\\bonus", "time": "2026-05-08T00:30:00Z", "profit": 100.0}
      ],
      "trades": [
        {"id": 11, "login": 80402, "group": "real\\A", "symbol": "EURUSD", "volume": 0.5, "side": "buy",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T01:30:00Z",
         "open_price": 1.08500, "close_price": 1.08520,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 10.0}
      ],
      "deposits": [], "withdraws": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

> Replicate the trade row 8× to satisfy R2.

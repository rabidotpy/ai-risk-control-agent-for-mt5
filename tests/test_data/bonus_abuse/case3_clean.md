# Bonus Abuse — Case 3: clean (no bonus at all)

**Expected**: every rule FALSE → `risk_score = 0`, `risk_level = low`.

R2 and R5 hit the `insufficient_data: no bonus event in window` guard.

| Sub-rule                                       | Expected | Reason                                           |
| ---------------------------------------------- | -------- | ------------------------------------------------ |
| `bonus_received_in_window`                     | FALSE    | no bonus events                                  |
| `trades_after_bonus_in_window >= 8`            | FALSE    | insufficient_data: no bonus event in window      |
| `linked_account_count >= 2`                    | FALSE    | no linked accounts                               |
| `linked_with_opposing_trades >= 1`             | FALSE    | no linked accounts                               |
| `withdrawal_after_bonus_in_window`             | FALSE    | insufficient_data: no bonus event in window      |

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80403,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "trades": [
        {"id": 1, "login": 80403, "group": "real\\A", "symbol": "EURUSD", "volume": 0.10, "side": "buy",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T03:00:00Z",
         "open_price": 1.08500, "close_price": 1.08550,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 5.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

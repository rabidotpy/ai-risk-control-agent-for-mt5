# Bonus Abuse — Case 4: linked accounts only (no bonus)

**Expected**: 2/5 TRUE → `risk_score = 40`, `risk_level = watch`.

This case proves R3/R4 work independently of bonus. Two linked accounts
with opposing trades — looks like potential hedging without using a
bonus. Worth flagging at `watch` level.

| Sub-rule                                       | Expected | Why                                              |
| ---------------------------------------------- | -------- | ------------------------------------------------ |
| `bonus_received_in_window`                     | FALSE    | no bonus                                         |
| `trades_after_bonus_in_window >= 8`            | FALSE    | insufficient_data: no bonus event in window      |
| `linked_account_count >= 2`                    | TRUE     | 2 linked logins                                  |
| `linked_with_opposing_trades >= 1`             | TRUE     | one linked has opposing-side activity            |
| `withdrawal_after_bonus_in_window`             | FALSE    | insufficient_data: no bonus event in window      |

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80404,
      "trigger_type": "manual_run",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "trades": [
        {"id": 1, "login": 80404, "group": "real\\A", "symbol": "EURUSD", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T01:30:00Z",
         "open_price": 1.08500, "close_price": 1.08520,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 20.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [],
      "linked_accounts": [
        {"login": 80405, "link_reasons": ["same_ip"],     "opposing_trade_count": 3},
        {"login": 80406, "link_reasons": ["same_device"], "opposing_trade_count": 0}
      ]
    }
  ],
  "include_history": false
}
```

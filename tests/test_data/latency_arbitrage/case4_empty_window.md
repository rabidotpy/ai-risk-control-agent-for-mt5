# Latency Arbitrage — Case 4: empty window (insufficient_data)

**Expected**: every rule FALSE with `insufficient_data` reason → score 0,
level low. Exercises the "no trades in window" guard on R2/R3/R4.

| Sub-rule                                       | Expected | Reason                          |
| ---------------------------------------------- | -------- | ------------------------------- |
| `trade_count_in_window >= 30`                  | FALSE    | count = 0                       |
| `median_holding_time_seconds <= 30`            | FALSE    | insufficient_data: no trades    |
| `minority_side_ratio >= 0.2`                   | FALSE    | insufficient_data: no trades    |
| `win_rate >= 0.9 AND batch_close_ratio <= 0.2` | FALSE    | insufficient_data: fewer than 5 |

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80104,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time": "2026-05-08T05:59:59Z",
      "trades": [],
      "deposits": [],
      "withdraws": [],
      "bonus": [],
      "linked_accounts": []
    }
  ],
  "include_history": false
}
```

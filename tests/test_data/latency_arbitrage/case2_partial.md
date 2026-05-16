# Latency Arbitrage — Case 2: partial (R1 only — martingale grid false-positive)

**Expected**: 1/4 sub-rules TRUE → `risk_score = 25`, `risk_level = low`.

| Sub-rule                                       | Expected | Why                                           |
| ---------------------------------------------- | -------- | --------------------------------------------- |
| `trade_count_in_window >= 30`                  | TRUE     | 30+ trades                                    |
| `median_holding_time_seconds <= 30`            | FALSE    | median ~35 minutes (grid holds for the move)  |
| `minority_side_ratio >= 0.2`                   | FALSE    | one-sided (all shorts)                        |
| `win_rate >= 0.9 AND batch_close_ratio <= 0.2` | FALSE    | wins ~80%, closes in batches (grid signature) |

This is the account 250030 shape — a martingale grid on XAUUSD. The
high trade count is the only thing it shares with latency arbitrage; R2,
R3, R4 all reject the grid because it is one-sided, holds positions for
minutes, and closes everything together.

## Payload (representative trade — duplicate to ≥30, all `side: "sell"`)

```json
{
  "snapshots": [
    {
      "mt5_login": 80102,
      "trigger_type": "manual_run",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time": "2026-05-08T05:59:59Z",
      "trades": [
        {
          "id": 1,
          "login": 80102,
          "group": "real\\A",
          "symbol": "XAUUSD",
          "volume": 0.5,
          "side": "sell",
          "open_time": "2026-05-08T00:00:00Z",
          "time": "2026-05-08T00:35:00Z",
          "open_price": 2300.0,
          "close_price": 2299.4,
          "bid_at_open": 2299.95,
          "ask_at_open": 2300.05,
          "profit": 30.0
        }
      ],
      "deposits": [],
      "withdraws": [],
      "bonus": [],
      "linked_accounts": []
    }
  ],
  "include_history": false
}
```

> Construct ≥30 rows, all `side: "sell"`, holds ~35min each, and group
> the close times into a few clusters (e.g. 12 trades closing at the
> same `time`) so `batch_close_ratio` exceeds 0.2.

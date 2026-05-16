# Latency Arbitrage — Case 1: clear trigger (all 4 rules TRUE)

**Expected**: `risk_score = 100`, `risk_level = critical`.

| Sub-rule                                       | Expected | Why                                            |
| ---------------------------------------------- | -------- | ---------------------------------------------- |
| `trade_count_in_window >= 30`                  | TRUE     | 30 trades in window                            |
| `median_holding_time_seconds <= 30`            | TRUE     | every trade closed within 20s                  |
| `minority_side_ratio >= 0.2`                   | TRUE     | both buy and sell traded (≥ 20% minority)      |
| `win_rate >= 0.9 AND batch_close_ratio <= 0.2` | TRUE     | near-100% wins, closes scattered (not batched) |

```bash
curl -X POST http://127.0.0.1:5050/analyse_risk \
  -H 'content-type: application/json' \
  -d @case1_clear_trigger.json
```

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80101,
      "trigger_type": "high_frequency",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time": "2026-05-08T05:59:59Z",
      "trades": [
        {
          "id": 1,
          "login": 80101,
          "group": "real\\A",
          "symbol": "EURUSD",
          "volume": 1.0,
          "side": "buy",
          "open_time": "2026-05-08T00:01:00Z",
          "time": "2026-05-08T00:01:15Z",
          "open_price": 1.085,
          "close_price": 1.08512,
          "bid_at_open": 1.08498,
          "ask_at_open": 1.08503,
          "profit": 12.0
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

> **Note**: the array above shows one representative trade. To exercise
> R1 (`trade_count_in_window >= 30`) duplicate the trade 30 times with
> incrementing `id` and staggered `open_time` / `time` (e.g. +60s steps).
> Alternate `side` between "buy" and "sell" so R3 passes. Keep `profit`
>
> > 0 on at least 27 of 30 rows so R4's `win_rate >= 0.9` passes. Spread
> > close times so no single close-second is shared by 3+ trades — that
> > keeps `batch_close_ratio <= 0.2`.

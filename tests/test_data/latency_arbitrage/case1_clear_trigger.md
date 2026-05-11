# Latency Arbitrage — Case 1: clear trigger (all 4 rules TRUE)

**Expected**: `risk_score = 100`, `risk_level = critical`.

| Sub-rule                                 | Expected | Why                                |
| ---------------------------------------- | -------- | ---------------------------------- |
| `trade_count_6h >= 30`                   | TRUE     | 30 trades in window                |
| `median_holding_time_seconds <= 30`      | TRUE     | every trade closed within 20s      |
| `positive_slippage_ratio >= 0.5`         | TRUE     | every buy filled below ask         |
| `short_holding_ratio_30s >= 0.6`         | TRUE     | every trade <= 30s                 |

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
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1,  "login": 80101, "group": "real\\A", "symbol": "EURUSD", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-08T00:01:00Z", "time": "2026-05-08T00:01:15Z",
         "open_price": 1.08500, "close_price": 1.08512,
         "bid_at_open": 1.08498, "ask_at_open": 1.08503, "profit": 12.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

> **Note**: the array above shows one representative trade. To exercise
> R1 (`trade_count_6h >= 30`) duplicate the trade 30 times with
> incrementing `id` and staggered `open_time` / `time` (e.g. +30s steps).
> The other sub-rules already pass with that single shape repeated.

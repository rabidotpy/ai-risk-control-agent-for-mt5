# Latency Arbitrage — Case 3: clean account (all 4 rules FALSE)

**Expected**: 1/4 sub-rules TRUE (minority side trips on a tiny sample) → `risk_score = 25`, `risk_level = low`.

| Sub-rule                                       | Expected | Why                               |
| ---------------------------------------------- | -------- | --------------------------------- |
| `trade_count_in_window >= 30`                  | FALSE    | only 3 trades                     |
| `median_holding_time_seconds <= 30`            | FALSE    | each trade held ~2 hours          |
| `minority_side_ratio >= 0.2`                   | TRUE     | mixed buy and sell                |
| `win_rate >= 0.9 AND batch_close_ratio <= 0.2` | FALSE    | only 3 trades — insufficient_data |

A retail swing trader.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80103,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time": "2026-05-08T05:59:59Z",
      "trades": [
        {
          "id": 1,
          "login": 80103,
          "group": "real\\A",
          "symbol": "EURUSD",
          "volume": 0.1,
          "side": "buy",
          "open_time": "2026-05-08T00:00:00Z",
          "time": "2026-05-08T02:00:00Z",
          "open_price": 1.085,
          "close_price": 1.0862,
          "bid_at_open": 1.08498,
          "ask_at_open": 1.085,
          "profit": 12.0
        },
        {
          "id": 2,
          "login": 80103,
          "group": "real\\A",
          "symbol": "USDJPY",
          "volume": 0.1,
          "side": "sell",
          "open_time": "2026-05-08T01:00:00Z",
          "time": "2026-05-08T03:30:00Z",
          "open_price": 156.2,
          "close_price": 156.05,
          "bid_at_open": 156.2,
          "ask_at_open": 156.22,
          "profit": 9.0
        },
        {
          "id": 3,
          "login": 80103,
          "group": "real\\A",
          "symbol": "GBPUSD",
          "volume": 0.05,
          "side": "buy",
          "open_time": "2026-05-08T03:00:00Z",
          "time": "2026-05-08T05:00:00Z",
          "open_price": 1.26,
          "close_price": 1.2595,
          "bid_at_open": 1.25998,
          "ask_at_open": 1.26,
          "profit": -2.5
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

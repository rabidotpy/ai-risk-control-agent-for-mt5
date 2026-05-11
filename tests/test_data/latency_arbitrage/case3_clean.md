# Latency Arbitrage — Case 3: clean account (all 4 rules FALSE)

**Expected**: `risk_score = 0`, `risk_level = low`.

| Sub-rule                                 | Expected | Why                                |
| ---------------------------------------- | -------- | ---------------------------------- |
| `trade_count_6h >= 30`                   | FALSE    | only 3 trades                      |
| `median_holding_time_seconds <= 30`      | FALSE    | each trade held ~2 hours           |
| `positive_slippage_ratio >= 0.5`         | FALSE    | filled at the ask, neutral         |
| `short_holding_ratio_30s >= 0.6`         | FALSE    | none under 30s                     |

A retail swing trader.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80103,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1, "login": 80103, "group": "real\\A", "symbol": "EURUSD", "volume": 0.10, "side": "buy",
         "open_time": "2026-05-08T00:00:00Z", "time": "2026-05-08T02:00:00Z",
         "open_price": 1.08500, "close_price": 1.08620,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 12.0},
        {"id": 2, "login": 80103, "group": "real\\A", "symbol": "USDJPY", "volume": 0.10, "side": "sell",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T03:30:00Z",
         "open_price": 156.20, "close_price": 156.05,
         "bid_at_open": 156.20, "ask_at_open": 156.22, "profit": 9.0},
        {"id": 3, "login": 80103, "group": "real\\A", "symbol": "GBPUSD", "volume": 0.05, "side": "buy",
         "open_time": "2026-05-08T03:00:00Z", "time": "2026-05-08T05:00:00Z",
         "open_price": 1.26000, "close_price": 1.25950,
         "bid_at_open": 1.25998, "ask_at_open": 1.26000, "profit": -2.5}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

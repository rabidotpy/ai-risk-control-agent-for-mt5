# Swap Arbitrage — Case 2: partial (rollover + some swap, but price PnL dominates)

**Expected**: 2/4 TRUE → `risk_score = 50`, `risk_level = watch`.

| Sub-rule                               | Expected | Why                                            |
| -------------------------------------- | -------- | ---------------------------------------------- |
| `swap_profit_ratio >= 0.6`             | FALSE    | swap is only ~10% of total profit              |
| `positions_held_across_rollover >= 1`  | TRUE     | trade 1 spans two days                         |
| `swap_dominant_closed_positions >= 5`  | FALSE    | only 1 trade is swap-dominant                  |
| `average_price_movement_pnl_low`       | FALSE    | price PnL is large vs the small positive swap  |

A directional carry trader who actually got the move right.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80302,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-05T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "trades": [
        {"id": 1, "login": 80302, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-05T08:00:00Z", "time": "2026-05-06T08:00:00Z",
         "open_price": 100.00, "close_price": 100.80,
         "bid_at_open": 100.00, "ask_at_open": 100.01,
         "swaps": 18.0, "commission": -2.0, "profit": 96.0},
        {"id": 2, "login": 80302, "group": "real\\A", "symbol": "EURUSD", "volume": 0.5, "side": "buy",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T05:00:00Z",
         "open_price": 1.08500, "close_price": 1.08620,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500,
         "swaps": 0.0, "commission": -1.0, "profit": 60.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

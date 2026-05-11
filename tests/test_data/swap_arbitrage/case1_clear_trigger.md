# Swap Arbitrage — Case 1: clear trigger (all 4 rules TRUE)

**Expected**: `risk_score = 100`, `risk_level = critical`.

| Sub-rule                               | Expected | Why                                              |
| -------------------------------------- | -------- | ------------------------------------------------ |
| `swap_profit_ratio >= 0.6`             | TRUE     | swap is ~80% of total profit                     |
| `positions_held_across_rollover >= 1`  | TRUE     | every trade spans 2+ UTC dates                   |
| `swap_dominant_closed_positions >= 5`  | TRUE     | 6 trades with `swaps > 0` and tiny price PnL     |
| `average_price_movement_pnl_low`       | TRUE     | sum(price_pnl)/sum(swap) ≈ 0.05                  |

Carry trader on a high-positive-swap pair (e.g. AUDJPY long).

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80301,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-05T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "trades": [
        {"id": 1, "login": 80301, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-05T08:00:00Z", "time": "2026-05-06T08:00:00Z",
         "open_price": 100.00, "close_price": 100.02,
         "bid_at_open": 100.00, "ask_at_open": 100.01,
         "swaps": 18.0, "commission": -2.0, "profit": 18.0},
        {"id": 2, "login": 80301, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-06T08:00:00Z", "time": "2026-05-07T08:00:00Z",
         "open_price": 100.05, "close_price": 100.06,
         "bid_at_open": 100.05, "ask_at_open": 100.06,
         "swaps": 18.0, "commission": -2.0, "profit": 17.0},
        {"id": 3, "login": 80301, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-06T09:00:00Z", "time": "2026-05-07T09:00:00Z",
         "open_price": 100.10, "close_price": 100.11,
         "bid_at_open": 100.10, "ask_at_open": 100.11,
         "swaps": 18.0, "commission": -2.0, "profit": 17.5},
        {"id": 4, "login": 80301, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-06T10:00:00Z", "time": "2026-05-07T10:00:00Z",
         "open_price": 100.15, "close_price": 100.16,
         "bid_at_open": 100.15, "ask_at_open": 100.16,
         "swaps": 18.0, "commission": -2.0, "profit": 17.0},
        {"id": 5, "login": 80301, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-06T11:00:00Z", "time": "2026-05-07T11:00:00Z",
         "open_price": 100.20, "close_price": 100.21,
         "bid_at_open": 100.20, "ask_at_open": 100.21,
         "swaps": 18.0, "commission": -2.0, "profit": 17.5},
        {"id": 6, "login": 80301, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-06T12:00:00Z", "time": "2026-05-07T12:00:00Z",
         "open_price": 100.25, "close_price": 100.26,
         "bid_at_open": 100.25, "ask_at_open": 100.26,
         "swaps": 18.0, "commission": -2.0, "profit": 17.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

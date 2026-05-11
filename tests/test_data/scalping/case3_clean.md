# Scalping — Case 3: clean account (all 4 rules FALSE)

**Expected**: `risk_score = 0`, `risk_level = low`.

Position trader: low frequency, long holds, mixed P&L, no pattern.

| Sub-rule                                       | Expected |
| ---------------------------------------------- | -------- |
| `trade_count_in_window >= 25`                  | FALSE    |
| `short_holding_ratio_60s >= 0.7`               | FALSE    |
| `win_rate >= 0.75`                             | FALSE    |
| `repeated_lot_sl_tp_pattern_ratio >= 0.5`      | FALSE    |

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80203,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1, "login": 80203, "group": "real\\A", "symbol": "XAUUSD", "volume": 0.05, "side": "buy",
         "open_time": "2026-05-08T00:00:00Z", "time": "2026-05-08T03:30:00Z",
         "open_price": 2350.00, "close_price": 2358.50,
         "bid_at_open": 2349.80, "ask_at_open": 2350.00, "profit": 42.5},
        {"id": 2, "login": 80203, "group": "real\\A", "symbol": "EURUSD", "volume": 0.20, "side": "sell",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T05:00:00Z",
         "open_price": 1.08500, "close_price": 1.08620,
         "bid_at_open": 1.08500, "ask_at_open": 1.08502, "profit": -24.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

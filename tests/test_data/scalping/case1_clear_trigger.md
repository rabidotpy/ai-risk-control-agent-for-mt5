# Scalping — Case 1: clear trigger (all 4 rules TRUE)

**Expected**: `risk_score = 100`, `risk_level = critical`.

| Sub-rule                                       | Expected | Why                                         |
| ---------------------------------------------- | -------- | ------------------------------------------- |
| `trade_count_in_window >= 25`                  | TRUE     | 25+ trades                                  |
| `short_holding_ratio_60s >= 0.7`               | TRUE     | every trade closed within 30s               |
| `win_rate >= 0.75`                             | TRUE     | every trade profitable                      |
| `repeated_lot_sl_tp_pattern_ratio >= 0.5`      | TRUE     | identical (volume, SL, TP) on every trade   |

Looks like an EA: same lot, same SL/TP, all wins, sub-minute holds.

## Payload (representative — duplicate to >= 25 trades)

```json
{
  "snapshots": [
    {
      "mt5_login": 80201,
      "trigger_type": "high_frequency",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1, "login": 80201, "group": "real\\A", "symbol": "EURUSD", "volume": 0.50, "side": "buy",
         "open_time": "2026-05-08T00:00:00Z", "time": "2026-05-08T00:00:25Z",
         "open_price": 1.08500, "close_price": 1.08510,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500,
         "stop_loss": 1.08470, "take_profit": 1.08510, "profit": 5.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

> Replicate the trade 25 times keeping `volume`, `stop_loss`,
> `take_profit` identical and stagger times.

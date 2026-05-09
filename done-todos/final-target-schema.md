# Final Target Schema — Request to Alex

The wire shape we need from Alex's GET endpoint to fully execute every
rule across all four risk types. Everything in this schema is already
visible in MT5's Admin Deals view (screenshot in this folder); it's
just not all surfaced in Alex's current example envelope.

---

## Per-account pull (existing endpoint, augmented)

```jsonc
{
  "status": true,
  "start_time": "2026-05-08T00:00:00.000Z", // NEW (required)
  "end_time": "2026-05-08T05:59:59.999Z", // NEW (required)
  "data": {
    "deposits": [
      {
        "id": 897518, // order id
        "login": 200001,
        "group": "real\\group-d",
        "time": "2026-05-08T00:06:00.258Z",
        "profit": 200, // always > 0
      },
    ],
    "withdraws": [
      {
        "id": 897519,
        "login": 200001,
        "group": "real\\group-d",
        "time": "2026-05-08T00:06:00.258Z",
        "profit": -100, // always < 0
      },
    ],
    "bonus": [
      {
        "id": 897520,
        "login": 200001,
        "group": "real\\group-d",
        "time": "2026-05-08T00:06:00.258Z",
        "profit": 100, // always > 0
      },
    ],
    "trades": [
      {
        "id": 12345,
        "login": 200001,
        "group": "real\\group-d",
        "entry": 1, // MT5 enum (informational)
        "symbol": "XAUUSD",
        "volume": 0.01,
        "side": "buy", // NEW: "buy" | "sell"
        "open_time": "2026-05-08T00:06:00.258Z", // NEW (required)
        "time": "2026-05-08T00:06:42.901Z", // = close_time (kept name `time` for back-compat)
        "open_price": 2345.1,
        "close_price": 2345.42,
        "bid_at_open": 2345.05, // NEW: MT5 "Market Bid" column
        "ask_at_open": 2345.12, // NEW: MT5 "Market Ask" column
        "stop_loss": 0, // 0 = unset
        "take_profit": 0, // 0 = unset
        "swaps": 0, // total swap accrued over life of position
        "commission": -0.07, // NEW: MT5 "Commission" column
        "profit": 3.2, // realized PnL on close (NET of swap + commission)
      },
    ],
  },
}
```

### Field-by-field deltas from Alex's current example

| Field                                          | Status            | Why                                                                                                         |
| ---------------------------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------- |
| Envelope `start_time`, `end_time`              | **New, required** | Lock the window contract; the scheduler shouldn't have to guess                                             |
| `trades[].open_time`                           | **New, required** | All 5 holding-time / rollover rules need it                                                                 |
| `trades[].side`                                | **New, required** | latency-arb R3 (positive_slippage_ratio) — direction-dependent                                              |
| `trades[].bid_at_open`, `trades[].ask_at_open` | **New, required** | latency-arb R3                                                                                              |
| `trades[].commission`                          | **New, required** | swap-arb R3 / R4 use `price_pnl = profit − swaps − commission`                                              |
| `trades[].time`                                | **Repurpose**     | Treat as `close_time`. Codebase aliases it; no rename needed on the wire if Alex prefers the existing name. |

---

## Linked-accounts feed (separate endpoint)

This data lives in the CRM, not MT5, so a different endpoint is fine:

```jsonc
GET /linked_accounts?login=200001

{
  "status": true,
  "data": {
    "login": 200001,
    "linked_accounts": [
      {
        "login": 200002,
        "link_reasons": ["same_ip", "same_device"],
        "opposing_trade_count": 12              // pre-computed by the broker / a feature service
      },
      {
        "login": 200003,
        "link_reasons": ["same_wallet"],
        "opposing_trade_count": 0
      }
    ]
  }
}
```

The scheduler merges this into each `AccountSnapshot` via the
`linked_accounts_by_login` argument on
[`bucket_by_login`](app/schemas.py).

If Alex prefers, this can be folded into the main envelope under
`data.linked_accounts` — the codebase will accept either layout.

---

## Open questions for Alex

1. Are envelope `start_time` / `end_time` always exactly the requested
   6h window, or do they reflect the actual data range returned?
2. Confirm that `trades[].profit` is **net** of swap + commission. (If
   it's gross, the swap-arb `price_pnl` formula needs to flip sign on
   commission.)
3. Can `bonus[]` extend to a 30-day lookback (PRD §6.3 baseline) rather
   than only the in-window 6h? Today the bonus_abuse R1 rule is scoped
   to "received in window" — accurate but narrower than the PRD.
4. For linked-accounts: separate endpoint, or merged into the main
   envelope? Either works for us.

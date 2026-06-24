# How Burnwatch detection works

Burnwatch is not a black box. This document describes every rule that can fire, when it fires, and the exact evidence it attaches to an alert. The SDK in this repo decides what metadata leaves your process; this document describes what the backend does with it.

## Principles

- **Observe-only.** Rules raise alerts. They never block, delay, or reverse a payment. By the time a rule fires, the payment has already happened. Burnwatch tells you fast so you can react.
- **Per-agent baselines.** Each agent learns its own "normal" from its own history (default lookback: 30 days). What is abnormal for one agent is routine for another.
- **Warm-up.** A new agent is observed silently until it has roughly 20 payments of baseline. Until then, pattern-based rules hold their fire so you do not get noise on day one. Policy rules (caps, blocklists, allowlists) apply immediately.
- **Explainable evidence.** Every alert carries a JSON `evidence` object with the exact numbers and thresholds that tripped, so you can tell a real incident from noise at a glance.
- **Cooldown.** Duplicate alerts of the same type for the same agent are suppressed within a short window (default: 5 minutes) so one incident does not spam you.

All thresholds below are defaults. Operational thresholds live in the backend; caps, blocklists, and allowlists are set per agent in **Settings -> Spend policy**.

## The rules

### 1. Spend velocity (`spend_velocity`)
- **Catches:** the agent's burn rate spiking far above its baseline.
- **Fires when:** the spend rate over the recent window (default 5 min) exceeds 5x the baseline rate and is at least 0.50 per minute (so tiny baselines do not false-fire).
- **Severity:** critical if 20x or more above baseline, otherwise high.
```json
{
  "rule": "spend_velocity",
  "baseline_rate_per_min": 0.002017,
  "current_rate_per_min": 7.2,
  "ratio": 3569.2,
  "window_minutes": 5,
  "baseline_samples": 41
}
```

### 2. Drain burst (`drain_burst`)
- **Catches:** a rapid cluster of payments, the classic wallet-drain signature.
- **Fires when:** 5 or more payments, or 5.00 or more in total, occur within a short window (default 3 min).
- **Severity:** critical if both thresholds are met, otherwise high.
```json
{
  "rule": "drain_burst",
  "payment_count": 5,
  "total_amount": 12.4,
  "window_minutes": 3
}
```

### 3. Unknown counterparty (`unknown_counterparty`)
- **Catches:** a payment to a payee the agent never paid during baseline.
- **Fires when:** the normalized recipient is not in the agent's learned set of known counterparties.
- **Severity:** medium.
```json
{
  "rule": "unknown_counterparty",
  "recipient": "0xUNKNOWN-sink",
  "normalized_recipient": "0xunknown-sink",
  "amount": 1.42,
  "ts": "2026-06-23T15:55:04+00:00"
}
```

### 4. Off-pattern destination (`off_pattern_destination`)
- **Catches:** a new *kind* of destination, for example a raw wallet address when the agent has only ever paid API hosts.
- **Fires when:** the recipient's kind (api host, evm wallet, solana wallet, etc.) is not among the kinds seen in baseline.
- **Severity:** high for wallet destinations, otherwise medium.
```json
{
  "rule": "off_pattern_destination",
  "recipient": "0x9f2c...a1",
  "recipient_kind": "evm_wallet",
  "baseline_kinds": ["api_host"],
  "amount": 3.61,
  "ts": "2026-06-23T15:55:05+00:00"
}
```

### 5. Amount spike (`amount_spike`)
- **Catches:** a single payment far larger than the agent's usual size.
- **Fires when:** an amount is at least 8x the baseline p99 and median (and at least 1.00). Requires at least 5 baseline samples.
- **Severity:** critical if 3x over the threshold, otherwise high.
```json
{
  "rule": "amount_spike",
  "recipient": "wallet.drainer.x",
  "amount": 2.87,
  "threshold": 0.32,
  "baseline_median": 0.003,
  "baseline_p99": 0.04,
  "ts": "2026-06-23T15:55:04+00:00"
}
```

### 6. Off-hours spend (`off_hours_spend`)
- **Catches:** activity during hours the agent is normally quiet.
- **Fires when:** a payment lands in an hour (UTC) that holds less than 3% of the agent's baseline activity.
- **Severity:** medium.
```json
{
  "rule": "off_hours_spend",
  "hour_utc": 3,
  "active_hours_utc": [12, 13, 14, 15, 16, 23],
  "amount": 1.5,
  "recipient": "0xUNKNOWN-sink",
  "ts": "2026-06-23T03:00:00+00:00"
}
```

### 7. New rail (`new_rail`)
- **Catches:** a payment over a rail the agent has not used before.
- **Fires when:** the rail value is not in the agent's set of known rails.
- **Severity:** medium.
```json
{
  "rule": "new_rail",
  "rail": "agentkit",
  "known_rails": ["x402"],
  "amount": 4.2,
  "recipient": "relay.unknown.io",
  "ts": "2026-06-23T15:55:05+00:00"
}
```

### 8. Recipient concentration (`recipient_concentration`)
- **Catches:** one payee suddenly absorbing most of the agent's spend.
- **Fires when:** in a window (default 30 min) a single, not-previously-known payee accounts for 65% or more of total spend.
- **Severity:** high.
```json
{
  "rule": "recipient_concentration",
  "recipient": "0xUNKNOWN-sink",
  "share_pct": 88.0,
  "window_minutes": 30,
  "payment_count": 6,
  "total_amount": 13.9
}
```

### 9. Counterparty velocity (`counterparty_velocity`)
- **Catches:** rapid repeated payments to the same payee.
- **Fires when:** the same recipient receives 4 or more payments within a short window (default 5 min).
- **Severity:** high.
```json
{
  "rule": "counterparty_velocity",
  "recipient": "0xUNKNOWN-sink",
  "payment_count": 5,
  "window_minutes": 5
}
```

### 10. Asset anomaly (`asset_anomaly`)
- **Catches:** a payment in a token or asset the agent has not used before.
- **Fires when:** the asset is not in the agent's set of known assets.
- **Severity:** high.
```json
{
  "rule": "asset_anomaly",
  "asset": "ETH",
  "known_assets": ["USDC"],
  "amount": 3.61,
  "recipient": "0x9f2c...a1",
  "ts": "2026-06-23T15:55:05+00:00"
}
```

### 11. Daily budget exceeded (`daily_budget_exceeded`)
- **Catches:** cumulative spend for the day crossing a cap you set.
- **Fires when:** total spend since midnight (UTC) exceeds the agent's configured daily cap. Applies immediately, no warm-up.
- **Severity:** critical if 2x over the cap, otherwise high.
```json
{
  "rule": "daily_budget_exceeded",
  "daily_cap": 10.0,
  "spend_today": 24.5,
  "overage": 14.5,
  "overage_pct": 145.0,
  "day_utc": "2026-06-23"
}
```

### 12. Blocklist match (`blocklist_match`)
- **Catches:** a payment to a recipient you explicitly blocked.
- **Fires when:** a recipient matches an entry on the agent's blocklist. Applies immediately, no warm-up.
- **Severity:** critical.
```json
{
  "rule": "blocklist_match",
  "recipient": "0xbad.evil.example",
  "matched_entry": "evil.example",
  "amount": 5.1,
  "ts": "2026-06-23T15:55:06+00:00"
}
```

### 13. Allowlist violation (`allowlist_violation`)
- **Catches:** a payment to anyone outside an approved set, when strict mode is on.
- **Fires when:** strict allowlist is enabled and a recipient is not on the allowlist. Applies immediately, no warm-up.
- **Severity:** high.
```json
{
  "rule": "allowlist_violation",
  "recipient": "relay.unknown.io",
  "allowlist_size": 2,
  "amount": 4.2,
  "ts": "2026-06-23T15:55:05+00:00"
}
```

## A note on what this cannot do

Burnwatch is observe-only by design. It does not and cannot stop a payment, because it never sits in the payment path. That tradeoff is deliberate: a monitor that can block is a monitor that can break your agent, and one that can take custody is one more thing that can be compromised. Burnwatch's job is to see everything and tell you fast, with enough evidence to act. Hard controls (caps, allowlists) still surface here as alerts so you know the instant a boundary is crossed.

# x402 Shadownet Test Assets

Test tokens and swap contract for x402 composability testing on Tezos Shadownet.

## Overview

This repo contains the contracts and documentation needed to test x402 payment composability - specifically the scenario where an AI agent needs to acquire tokens via a swap before making a payment.

## Deployed Contracts

| Contract | Address | Purpose |
|----------|---------|---------|
| **TEST Token** | `KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T` | FA2 token for x402 payments |
| **WRONG Token** | `KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj` | FA2 token for multi-asset testing |
| **TEST_SWAP** | `KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt` | XTZ → TEST swap (rate: 1000) |
| **WRONG_SWAP** | `KT1TT7qrqBy3r7jSjNyLRAGFtihu6GZBRg1K` | XTZ → WRONG swap (rate: 500) |

**Network:** Shadownet
**Admin:** `tz1hUXcGHiNsR3TRyYTeAaXtDqMCfLUExaqn`

## Swap Details

| Swap | Rate | Cost for 100 tokens |
|------|------|---------------------|
| TEST_SWAP | 1 XTZ = 1000 TEST | 0.1 XTZ |
| WRONG_SWAP | 1 XTZ = 500 WRONG | 0.2 XTZ |

The different rates enable testing agent cost optimization when multiple payment options are accepted.

## Test Scenarios

**Core x402 Flows:**

```
1. ✅ Happy path: x402 requests TEST → wallet has TEST → pay → success
2. ❌ Wrong token: x402 requests TEST → pay with WRONG → rejected
3. 🔄 Swap flow: x402 requests TEST → no TEST → swap XTZ → pay → success
```

**Multi-Asset Agent Decisions:**

```
4. 💰 Existing balance: Agent has enough tokens → pay directly (no swap)
5. 📊 Cost optimization: Compare swap rates → choose cheaper option
6. 🔀 Fallback: Preferred swap paused → use alternative swap
7. 📈 Partial top-up: Compare cost to complete partial balances
```

## Usage

### Swap XTZ for TEST

```bash
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0.1 from <wallet> to KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt \
  --entrypoint swap --burn-cap 0.5
# Sends 0.1 XTZ, receives 100 TEST
```

### Swap XTZ for WRONG

```bash
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0.2 from <wallet> to KT1TT7qrqBy3r7jSjNyLRAGFtihu6GZBRg1K \
  --entrypoint swap --burn-cap 0.5
# Sends 0.2 XTZ, receives 100 WRONG (more expensive than TEST)
```

### Transfer TEST Tokens

```bash
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0 from <wallet> to KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T \
  --entrypoint transfer \
  --arg '{ Pair "<from_address>" { Pair "<to_address>" (Pair 0 <amount>) } }' \
  --burn-cap 1
```

### Mint TEST Tokens (Admin Only)

Only the admin (`tz1hUXcGHiNsR3TRyYTeAaXtDqMCfLUExaqn`) can mint tokens:

```bash
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0 from <admin_wallet> to KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T \
  --entrypoint mint_tokens \
  --arg '{ Pair "<recipient_address>" <amount> }' \
  --burn-cap 1
```

Example - mint 100,000 TEST to the swap contract:

```bash
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0 from soru_funder to KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T \
  --entrypoint mint_tokens \
  --arg '{ Pair "KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt" 100000 }' \
  --burn-cap 1
```

### Query Balance

Balances stored in big map **1278**. Query via RPC or indexer.

## Configuration

Contract addresses and configuration are available in `config/shadownet.json` for programmatic access.

## Contract Source

- `contracts/test_scenarios.py` - SmartPy test suite with FA2 token and swap contracts

## Running Tests

### SmartPy Tests (Contract Logic)

The test suite covers the three main x402 scenarios. Run with SmartPy CLI or the online IDE:

```bash
# Install SmartPy (requires Python virtual environment)
python3 -m venv ~/smartpy-venv
source ~/smartpy-venv/bin/activate
pip install smartpy-tezos

# Run all scenario tests
python contracts/test_scenarios.py
```

Test output will be generated in a directory alongside the script.

Or paste the contract code into the [SmartPy online IDE](https://smartpy.io/).

### Live Network Tests (Shadownet)

Test the deployed contracts directly:

```bash
# 1. Test swap (requires XTZ in wallet)
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0.1 from <wallet> to KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt \
  --entrypoint swap --burn-cap 0.5

# 2. Verify you received TEST tokens (check big map 1278)
# Use an indexer or RPC to query your balance

# 3. Test FA2 transfer
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0 from <wallet> to KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T \
  --entrypoint transfer \
  --arg '{ Pair "<your_tz_address>" { Pair "<recipient_address>" (Pair 0 100) } }' \
  --burn-cap 1
```

### Test Coverage (15 tests)

**Core Scenarios (3):**

- **Scenario 1**: Happy path - wallet has TEST, payment succeeds
- **Scenario 2**: Wrong token - payment with wrong token rejected
- **Scenario 3**: Swap flow - no TEST → swap XTZ → pay → success

**Additional Tests (2):**

- **Swap paused**: Verify paused swap rejects transactions
- **Insufficient liquidity**: Verify unfunded swap fails gracefully

**Edge Cases (6):**

- Zero amount swap/transfer handling
- Invalid token ID rejection
- Insufficient balance rejection
- Partial swap then payment (multiple swaps to accumulate)
- Unauthorized pause attempt rejection

**Multi-Asset Agent Decision Tests (4):**

- **Existing balance**: Pay with available tokens (no swap needed)
- **Cost optimization**: Choose cheaper swap when both available
- **Fallback**: Use alternative swap when preferred is paused
- **Partial top-up**: Compare cost to complete partial balances

## MCP Integration

See [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) for details on implementing the required MCP tools.

## License

MIT

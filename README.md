# x402 Shadownet Test Assets

Test tokens and swap contract for x402 composability testing on Tezos Shadownet.

## Overview

This repo contains the contracts and documentation needed to test x402 payment composability - specifically the scenario where an AI agent needs to acquire tokens via a swap before making a payment.

## Deployed Contracts

| Contract | Address | Purpose |
|----------|---------|---------|
| **TEST Token** | `KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T` | FA2 token for x402 payments |
| **WRONG Token** | `KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj` | FA2 token to test rejection |
| **TEST_SWAP** | `KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt` | XTZ → TEST swap |

**Network:** Shadownet
**Admin:** `tz1hUXcGHiNsR3TRyYTeAaXtDqMCfLUExaqn`

## Swap Details

- **Rate:** 1 XTZ = 1000 TEST (fixed)
- **Entrypoint:** `swap`
- **Liquidity:** ~100,000 TEST (mint more as needed)

## Test Scenarios

```
1. ✅ Happy path: x402 requests TEST → wallet has TEST → pay → success
2. ❌ Wrong token: x402 requests TEST → pay with WRONG → rejected
3. 🔄 Swap flow: x402 requests TEST → no TEST → swap XTZ → pay → success
```

## Usage

### Swap XTZ for TEST

```bash
octez-client --endpoint https://rpc.shadownet.teztnets.com \
  transfer 0.1 from <wallet> to KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt \
  --entrypoint swap --burn-cap 0.5
# Sends 0.1 XTZ, receives 100 TEST
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

## Contract Source

- `contracts/test_token_fa2.py` - SmartPy FA2 fungible token
- `contracts/test_swap.py` - SmartPy swap contract
- `contracts/test_swap.tz` - Compiled Michelson swap contract
- `contracts/test_scenarios.py` - SmartPy test suite

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

# Run individual contract tests
python contracts/test_swap.py
python contracts/test_token_fa2.py
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

### Test Coverage

- **Scenario 1**: Happy path - wallet has TEST, payment succeeds
- **Scenario 2**: Wrong token - payment with wrong token rejected
- **Scenario 3**: Swap flow - no TEST → swap XTZ → pay → success
- **Swap paused**: Verify paused swap rejects transactions
- **Insufficient liquidity**: Verify unfunded swap fails gracefully

## MCP Integration

See [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) for details on implementing the required MCP tools.

## License

MIT

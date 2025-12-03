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
- **Liquidity:** ~250,000 TEST

## Test Scenarios

```
1. ✅ Happy path: x402 requests TEST → wallet has TEST → pay → success
2. ❌ Wrong token: x402 requests TEST → pay with WRONG → rejected
3. 🔄 Swap flow: x402 requests TEST → no TEST → swap XTZ → pay → success
```

## Usage

### Swap XTZ for TEST

```bash
octez-client transfer 0.1 from <wallet> to KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt \
  --entrypoint swap --burn-cap 0.5
# Sends 0.1 XTZ, receives 100 TEST
```

### Transfer TEST Tokens

```bash
octez-client transfer 0 from <wallet> to KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T \
  --entrypoint transfer \
  --arg '{ Pair "<from_address>" { Pair "<to_address>" (Pair 0 <amount>) } }' \
  --burn-cap 1
```

### Query Balance

Balances stored in big map **1278**. Query via RPC or indexer.

## Contract Source

- `contracts/test_token_fa2.py` - SmartPy FA2 fungible token
- `contracts/test_swap.tz` - Michelson swap contract

## MCP Integration

See [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) for details on implementing the required MCP tools.

## License

MIT

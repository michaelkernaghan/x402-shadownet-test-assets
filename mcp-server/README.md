# x402 FA2 MCP Server

MCP server providing FA2 token tools for x402 payment flows on Tezos.

## Tools

| Tool | Description |
|------|-------------|
| `tezos_get_token_balance` | Query FA2 token balance for any address |
| `tezos_swap_xtz_to_token` | Swap XTZ for FA2 tokens via swap contracts |
| `tezos_transfer_fa2` | Transfer FA2 tokens to another address |

## Installation

```bash
cd mcp-server
npm install
npm run build
```

## Configuration

Add to your Claude Code MCP config (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "x402-fa2": {
      "command": "node",
      "args": ["C:/path/to/x402-shadownet-test-assets/mcp-server/dist/index.js"],
      "env": {
        "TEZOS_PRIVATE_KEY": "edsk...",
        "TEZOS_NETWORK": "shadownet"
      }
    }
  }
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TEZOS_PRIVATE_KEY` | Private key for signing transactions | Required |
| `TEZOS_NETWORK` | Network to connect to | `shadownet` |

Supported networks: `mainnet`, `ghostnet`, `shadownet`

## Shadownet Contract Addresses

### Tokens
- **TEST**: `KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T`
- **WRONG**: `KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj`

### Swap Contracts
- **TEST_SWAP**: `KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt` (1 XTZ = 1000 TEST)
- **WRONG_SWAP**: `KT1TT7qrqBy3r7jSjNyLRAGFtihu6GZBRg1K` (1 XTZ = 500 WRONG)

## Usage Examples

### Check TEST token balance
```
tezos_get_token_balance({
  tokenAddress: "KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T",
  tokenId: 0
})
```

### Swap 0.1 XTZ for TEST tokens
```
tezos_swap_xtz_to_token({
  swapContract: "KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt",
  xtzAmount: 0.1,
  expectedRate: 1000
})
```

### Transfer 100 TEST tokens
```
tezos_transfer_fa2({
  tokenAddress: "KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T",
  to: "tz1...",
  tokenId: 0,
  amount: 100
})
```

## x402 Payment Flow

When an x402 payment requires FA2 tokens:

1. **Check balance**: Use `tezos_get_token_balance` to see if you have enough tokens
2. **Swap if needed**: Use `tezos_swap_xtz_to_token` to acquire tokens
3. **Pay**: Use `tezos_transfer_fa2` to send tokens to the payment address

## License

MIT

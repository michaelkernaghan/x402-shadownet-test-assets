# MCP Integration Guide

How to integrate the x402 test assets with the Tezos MCP wallet.

## Required Tools

### 1. `tezos_get_token_balance`

Query FA2 token balance for an address.

```typescript
{
  name: "tezos_get_token_balance",
  description: "Get balance of an FA2 token",
  parameters: {
    token_address: string,  // FA2 contract address
    token_id: number,       // Token ID (0 for TEST)
    owner?: string          // Optional, defaults to wallet address
  }
}
```

**Implementation Notes:**
- TEST token ledger is in big map **1278**
- Key format: address bytes
- Query via RPC: `GET /chains/main/blocks/head/context/big_maps/1278/{key}`

**Example using Taquito:**
```typescript
async function getTokenBalance(
  tokenAddress: string,
  tokenId: number,
  owner: string
): Promise<number> {
  const contract = await Tezos.contract.at(tokenAddress);
  const storage = await contract.storage();

  // For this FA2, balance is in ledger big map
  const key = { owner, token_id: tokenId };
  const balance = await storage.ledger.get(key);

  return balance?.toNumber() || 0;
}
```

### 2. `tezos_swap_xtz_to_token`

Swap XTZ for TEST tokens using the swap contract.

```typescript
{
  name: "tezos_swap_xtz_to_token",
  description: "Swap XTZ for TEST tokens",
  parameters: {
    amount: number  // XTZ amount to swap
  }
}
```

**Implementation:**
```typescript
const SWAP_CONTRACT = "KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt";
const RATE = 1000; // 1 XTZ = 1000 TEST

async function swapXtzToToken(xtzAmount: number): Promise<string> {
  const contract = await Tezos.contract.at(SWAP_CONTRACT);

  const op = await contract.methods.swap().send({
    amount: xtzAmount,
    mutez: false
  });

  await op.confirmation();

  const testReceived = xtzAmount * RATE;
  return `Swapped ${xtzAmount} XTZ for ${testReceived} TEST. Op: ${op.hash}`;
}
```

### 3. `tezos_transfer_fa2`

Transfer FA2 tokens (for x402 payments).

```typescript
{
  name: "tezos_transfer_fa2",
  description: "Transfer FA2 tokens",
  parameters: {
    token_address: string,
    to: string,
    token_id: number,
    amount: number
  }
}
```

**Implementation:**
```typescript
async function transferFa2(
  tokenAddress: string,
  to: string,
  tokenId: number,
  amount: number
): Promise<string> {
  const contract = await Tezos.contract.at(tokenAddress);
  const from = await Tezos.signer.publicKeyHash();

  const transferParams = [
    {
      from_: from,
      txs: [{ to_: to, token_id: tokenId, amount: amount }]
    }
  ];

  const op = await contract.methods.transfer(transferParams).send();
  await op.confirmation();

  return `Transferred ${amount} tokens. Op: ${op.hash}`;
}
```

## x402 Payment Flow

When Claude receives a 402 response requesting TEST tokens:

```typescript
async function handleX402Payment(paymentReq: X402PaymentRequirement) {
  // 1. Check if we have the required token
  const balance = await getTokenBalance(
    paymentReq.tokenContract,
    0,  // token_id
    walletAddress
  );

  if (balance >= paymentReq.amount) {
    // 2a. We have tokens - pay directly
    return await transferFa2(
      paymentReq.tokenContract,
      paymentReq.payTo,
      0,
      paymentReq.amount
    );
  } else {
    // 2b. Need to swap first
    const needed = paymentReq.amount - balance;
    const xtzNeeded = Math.ceil(needed / 1000);  // rate: 1000 TEST per XTZ

    await swapXtzToToken(xtzNeeded);

    // 3. Now pay
    return await transferFa2(
      paymentReq.tokenContract,
      paymentReq.payTo,
      0,
      paymentReq.amount
    );
  }
}
```

## Contract Addresses

```typescript
const CONTRACTS = {
  TEST_TOKEN: "KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T",
  WRONG_TOKEN: "KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj",
  SWAP: "KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt"
};

const LEDGER_BIG_MAP_ID = 1278;
const SWAP_RATE = 1000;  // 1 XTZ = 1000 TEST
```

## FA2 Transfer Parameter Format

For direct RPC calls, the FA2 transfer parameter format is:

```michelson
{ Pair "from_address" { Pair "to_address" (Pair token_id amount) } }
```

Example:
```bash
octez-client transfer 0 from wallet to KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T \
  --entrypoint transfer \
  --arg '{ Pair "tz1ABC..." { Pair "tz1XYZ..." (Pair 0 1000) } }' \
  --burn-cap 1
```

## Testing Checklist

- [ ] Query TEST token balance
- [ ] Query WRONG token balance
- [ ] Swap XTZ → TEST
- [ ] Transfer TEST tokens
- [ ] Full x402 flow: check balance → swap if needed → pay
- [ ] Reject payment with wrong token

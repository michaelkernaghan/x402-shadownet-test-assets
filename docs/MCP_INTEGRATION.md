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

## FA2 balance_of Callback Pattern

The FA2 standard uses a callback pattern for `balance_of` queries. This is more complex than a simple view call.

### On-chain View (Simpler)

Our TEST token includes `OnchainviewBalanceOf`, which provides a simpler view:

```typescript
// Using Taquito's contract views
async function getBalanceViaView(
  tokenAddress: string,
  owner: string,
  tokenId: number
): Promise<number> {
  const contract = await Tezos.contract.at(tokenAddress);

  // Call the on-chain view
  const balance = await contract.contractViews
    .get_balance({ owner, token_id: tokenId })
    .executeView({ viewCaller: owner });

  return balance.toNumber();
}
```

### Callback Pattern (Standard FA2)

For FA2 contracts without on-chain views, you need to use the callback pattern:

```typescript
// This requires deploying a callback contract or using off-chain indexer
// The callback pattern works as follows:
// 1. Call balance_of with requests and a callback contract address
// 2. The FA2 contract calls your callback with the results

// For most use cases, query the ledger big map directly instead:
async function getBalanceFromBigMap(
  owner: string
): Promise<number> {
  const LEDGER_BIG_MAP_ID = 1278;
  const rpc = "https://rpc.shadownet.teztnets.com";

  // Pack the key (address for fungible token ledger)
  const packedKey = await Tezos.rpc.packData({
    data: { string: owner },
    type: { prim: "address" }
  });

  const keyHash = packedKey.packed;
  const url = `${rpc}/chains/main/blocks/head/context/big_maps/${LEDGER_BIG_MAP_ID}/${keyHash}`;

  try {
    const response = await fetch(url);
    const data = await response.json();
    return parseInt(data.int);
  } catch {
    return 0; // No balance
  }
}
```

## Complete Agent Flow Example

Here's a complete example showing how an agent handles an x402 payment requirement:

```typescript
import { TezosToolkit } from "@taquito/taquito";
import { InMemorySigner } from "@taquito/signer";

// Configuration (or load from config/shadownet.json)
const CONFIG = {
  rpc: "https://rpc.shadownet.teztnets.com",
  contracts: {
    TEST_TOKEN: "KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T",
    SWAP: "KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt"
  },
  swapRate: 1000,  // 1 XTZ = 1000 TEST
  gasBuffer: 0.1   // XTZ buffer for fees
};

interface X402PaymentRequirement {
  tokenContract: string;
  tokenId: number;
  amount: number;
  payTo: string;
}

class X402Agent {
  private tezos: TezosToolkit;
  private walletAddress: string;

  constructor(secretKey: string) {
    this.tezos = new TezosToolkit(CONFIG.rpc);
    this.tezos.setProvider({
      signer: new InMemorySigner(secretKey)
    });
  }

  async init() {
    this.walletAddress = await this.tezos.signer.publicKeyHash();
  }

  async getXtzBalance(): Promise<number> {
    const balance = await this.tezos.tz.getBalance(this.walletAddress);
    return balance.toNumber() / 1_000_000; // Convert mutez to XTZ
  }

  async getTokenBalance(tokenAddress: string, tokenId: number): Promise<number> {
    const contract = await this.tezos.contract.at(tokenAddress);
    const storage: any = await contract.storage();

    try {
      const balance = await storage.ledger.get({
        owner: this.walletAddress,
        token_id: tokenId
      });
      return balance?.toNumber() || 0;
    } catch {
      return 0;
    }
  }

  async swap(xtzAmount: number): Promise<string> {
    const contract = await this.tezos.contract.at(CONFIG.contracts.SWAP);

    const op = await contract.methods.swap().send({
      amount: xtzAmount,
      mutez: false
    });

    await op.confirmation();
    return op.hash;
  }

  async transferToken(
    tokenAddress: string,
    to: string,
    tokenId: number,
    amount: number
  ): Promise<string> {
    const contract = await this.tezos.contract.at(tokenAddress);

    const op = await contract.methods.transfer([{
      from_: this.walletAddress,
      txs: [{ to_: to, token_id: tokenId, amount: amount }]
    }]).send();

    await op.confirmation();
    return op.hash;
  }

  async handleX402(req: X402PaymentRequirement): Promise<{
    success: boolean;
    operations: string[];
    error?: string;
  }> {
    const operations: string[] = [];

    try {
      // Step 1: Check current token balance
      const currentBalance = await this.getTokenBalance(
        req.tokenContract,
        req.tokenId
      );
      console.log(`Current balance: ${currentBalance} TEST`);

      // Step 2: If insufficient, calculate swap needed
      if (currentBalance < req.amount) {
        const needed = req.amount - currentBalance;
        const xtzNeeded = Math.ceil(needed / CONFIG.swapRate);

        // Step 2a: Verify we have enough XTZ (including gas buffer)
        const xtzBalance = await this.getXtzBalance();
        if (xtzBalance < xtzNeeded + CONFIG.gasBuffer) {
          return {
            success: false,
            operations,
            error: `Insufficient XTZ. Need ${xtzNeeded + CONFIG.gasBuffer}, have ${xtzBalance}`
          };
        }

        // Step 2b: Execute swap
        console.log(`Swapping ${xtzNeeded} XTZ for ${xtzNeeded * CONFIG.swapRate} TEST`);
        const swapOp = await this.swap(xtzNeeded);
        operations.push(`swap: ${swapOp}`);

        // Step 2c: Verify swap succeeded
        const newBalance = await this.getTokenBalance(req.tokenContract, req.tokenId);
        if (newBalance < req.amount) {
          return {
            success: false,
            operations,
            error: `Swap completed but balance still insufficient: ${newBalance} < ${req.amount}`
          };
        }
      }

      // Step 3: Execute payment
      console.log(`Paying ${req.amount} TEST to ${req.payTo}`);
      const payOp = await this.transferToken(
        req.tokenContract,
        req.payTo,
        req.tokenId,
        req.amount
      );
      operations.push(`payment: ${payOp}`);

      return { success: true, operations };

    } catch (error) {
      return {
        success: false,
        operations,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }
}

// Usage example
async function main() {
  const agent = new X402Agent("edsk...");  // Your secret key
  await agent.init();

  // Simulate receiving a 402 payment requirement
  const paymentReq: X402PaymentRequirement = {
    tokenContract: CONFIG.contracts.TEST_TOKEN,
    tokenId: 0,
    amount: 100,
    payTo: "tz1SomePayeeAddress..."
  };

  const result = await agent.handleX402(paymentReq);

  if (result.success) {
    console.log("Payment successful!");
    console.log("Operations:", result.operations);
  } else {
    console.log("Payment failed:", result.error);
  }
}
```

## Error Handling

Common errors your agent should handle:

| Error | Cause | Agent Response |
|-------|-------|----------------|
| `FA2_TOKEN_UNDEFINED` | Token ID doesn't exist | Check token contract and ID |
| `FA2_INSUFFICIENT_BALANCE` | Not enough tokens | Swap more XTZ first |
| `FA2_NOT_OPERATOR` | Not authorized to transfer | Set operator or use own tokens |
| `Swap is paused` | Admin paused swap | Wait or use alternative |
| `Must send XTZ` | Swap called without XTZ | Include amount in transaction |
| Gas exhaustion | Not enough XTZ for fees | Maintain XTZ buffer |

## Testing Checklist

- [ ] Query TEST token balance
- [ ] Query WRONG token balance
- [ ] Swap XTZ → TEST
- [ ] Transfer TEST tokens
- [ ] Full x402 flow: check balance → swap if needed → pay
- [ ] Reject payment with wrong token
- [ ] Handle zero-amount edge cases
- [ ] Handle insufficient balance gracefully
- [ ] Handle swap failures (paused, no liquidity)

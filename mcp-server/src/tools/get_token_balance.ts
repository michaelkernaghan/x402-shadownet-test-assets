import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

/**
 * MCP tool for querying FA2 token balances.
 */

const inputSchema = z.object({
	tokenAddress: z.string().describe("The FA2 token contract address (KT1...)"),
	tokenId: z.number().default(0).describe("The token ID (default: 0 for fungible tokens)"),
	owner: z.string().optional().describe("Address to check balance for (default: wallet address)"),
});

type GetTokenBalanceParams = z.infer<typeof inputSchema>;

export const createGetTokenBalanceTool = (
	Tezos: TezosToolkit,
	walletAddress: string
) => ({
	name: "tezos_get_token_balance",
	config: {
		title: "Get FA2 Token Balance",
		description: `Query the balance of an FA2 token for a specific address.

Common Shadownet tokens:
- TEST: KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T (token_id: 0)
- WRONG: KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj (token_id: 0)`,
		inputSchema,
		annotations: {
			readOnlyHint: true,
			destructiveHint: false,
			idempotentHint: true,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as GetTokenBalanceParams;
		const { tokenAddress, tokenId, owner } = parsed;

		const ownerAddress = owner || walletAddress;

		// Validate addresses
		if (!tokenAddress.match(/^KT1[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid token contract address: ${tokenAddress}`);
		}
		if (!ownerAddress.match(/^(tz1|tz2|tz3|KT1)[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid owner address: ${ownerAddress}`);
		}

		try {
			const contract = await Tezos.contract.at(tokenAddress);
			const storage: any = await contract.storage();

			let balance = 0;

			// Try different ledger formats used by FA2 contracts
			if (storage.ledger) {
				// Try composite key format: { owner, token_id }
				try {
					const key = { owner: ownerAddress, token_id: tokenId };
					const result = await storage.ledger.get(key);
					if (result !== undefined) {
						balance = typeof result === "object" && result.toNumber
							? result.toNumber()
							: parseInt(result.toString(), 10);
					}
				} catch {
					// Try simple address key (fungible tokens)
					try {
						const result = await storage.ledger.get(ownerAddress);
						if (result !== undefined) {
							balance = typeof result === "object" && result.toNumber
								? result.toNumber()
								: parseInt(result.toString(), 10);
						}
					} catch {
						// Balance not found
					}
				}
			}

			// Try on-chain view if available
			if (balance === 0) {
				try {
					const views = contract.contractViews as any;
					if (views?.get_balance) {
						const viewResult = await views
							.get_balance({ owner: ownerAddress, token_id: tokenId })
							.executeView({ viewCaller: ownerAddress });
						balance = viewResult?.toNumber?.() || parseInt(viewResult?.toString() || "0", 10);
					}
				} catch {
					// View not available
				}
			}

			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						tokenAddress,
						tokenId,
						owner: ownerAddress,
						balance,
						message: `Balance: ${balance} tokens`,
					}, null, 2),
				}],
			};
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`Failed to get token balance: ${message}`);
		}
	},
});

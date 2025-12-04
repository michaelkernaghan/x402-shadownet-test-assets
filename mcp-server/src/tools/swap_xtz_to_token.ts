import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

/**
 * MCP tool for swapping XTZ to FA2 tokens via swap contracts.
 */

const MUTEZ_PER_TEZ = 1_000_000;
const CONFIRMATIONS_TO_WAIT = 3;

const inputSchema = z.object({
	swapContract: z.string().describe("The swap contract address (KT1...)"),
	xtzAmount: z.number().describe("Amount of XTZ to swap"),
	expectedRate: z.number().optional().describe("Expected tokens per XTZ (for info only)"),
});

type SwapXtzToTokenParams = z.infer<typeof inputSchema>;

const xtzToMutez = (xtz: number): number => Math.floor(xtz * MUTEZ_PER_TEZ);

export const createSwapXtzToTokenTool = (
	Tezos: TezosToolkit,
	walletAddress: string,
	tzktUrl: string
) => ({
	name: "tezos_swap_xtz_to_token",
	config: {
		title: "Swap XTZ for Tokens",
		description: `Swap XTZ for FA2 tokens using a swap contract.

Shadownet swap contracts:
- TEST_SWAP: KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt (1 XTZ = 1000 TEST)
- WRONG_SWAP: KT1TT7qrqBy3r7jSjNyLRAGFtihu6GZBRg1K (1 XTZ = 500 WRONG)

Example: Swap 0.1 XTZ for 100 TEST tokens`,
		inputSchema,
		annotations: {
			readOnlyHint: false,
			destructiveHint: true,
			idempotentHint: false,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as SwapXtzToTokenParams;
		const { swapContract, xtzAmount, expectedRate } = parsed;

		// Validate
		if (!swapContract.match(/^KT1[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid swap contract address: ${swapContract}`);
		}
		if (xtzAmount <= 0) {
			throw new Error("XTZ amount must be greater than 0");
		}

		const amountMutez = xtzToMutez(xtzAmount);

		// Check balance
		const balance = await Tezos.tz.getBalance(walletAddress);
		if (balance.toNumber() < amountMutez + 500000) {
			throw new Error(
				`Insufficient balance. Need ${xtzAmount} XTZ + fees, have ${balance.toNumber() / MUTEZ_PER_TEZ} XTZ`
			);
		}

		try {
			const swap = await Tezos.contract.at(swapContract);
			const contractCall = swap.methods.swap();

			let operation;
			try {
				operation = await contractCall.send({
					amount: xtzAmount,
					mutez: false,
				});
			} catch (err: unknown) {
				const message = err instanceof Error ? err.message : String(err);
				if (message.includes("paused")) {
					throw new Error("Swap contract is paused");
				}
				if (message.includes("FA2_INSUFFICIENT_BALANCE")) {
					throw new Error("Swap contract has insufficient token liquidity");
				}
				throw new Error(`Swap failed: ${message}`);
			}

			await operation.confirmation(CONFIRMATIONS_TO_WAIT);

			const opHash = operation.hash;
			const explorerUrl = `${tzktUrl}/${opHash}`;

			let expectedTokens: number | string = "Check balance to verify";
			if (expectedRate) {
				expectedTokens = Math.floor(xtzAmount * expectedRate);
			}

			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						success: true,
						message: `Swapped ${xtzAmount} XTZ`,
						swap: {
							xtzAmount,
							xtzMutez: amountMutez,
							swapContract,
							expectedTokens,
							opHash,
							explorerUrl,
						},
						note: "Use tezos_get_token_balance to verify tokens received",
					}, null, 2),
				}],
			};
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`Swap failed: ${message}`);
		}
	},
});

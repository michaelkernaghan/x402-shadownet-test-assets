import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

/**
 * MCP tool for transferring FA2 tokens.
 */

const CONFIRMATIONS_TO_WAIT = 3;

const inputSchema = z.object({
	tokenAddress: z.string().describe("The FA2 token contract address (KT1...)"),
	to: z.string().describe("Recipient address"),
	tokenId: z.number().default(0).describe("Token ID (default: 0)"),
	amount: z.number().describe("Amount of tokens to transfer"),
});

type TransferFa2Params = z.infer<typeof inputSchema>;

export const createTransferFa2Tool = (
	Tezos: TezosToolkit,
	walletAddress: string,
	tzktUrl: string
) => ({
	name: "tezos_transfer_fa2",
	config: {
		title: "Transfer FA2 Tokens",
		description: `Transfer FA2 tokens to another address.

Common Shadownet tokens:
- TEST: KT1WC1mypEpFzZCq6rJbc4XSjaz1Ym42Do2T
- WRONG: KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj

Used for x402 payments when paying with FA2 tokens.`,
		inputSchema,
		annotations: {
			readOnlyHint: false,
			destructiveHint: true,
			idempotentHint: false,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as TransferFa2Params;
		const { tokenAddress, to, tokenId, amount } = parsed;

		// Validate
		if (!tokenAddress.match(/^KT1[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid token contract address: ${tokenAddress}`);
		}
		if (!to.match(/^(tz1|tz2|tz3|KT1)[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid recipient address: ${to}`);
		}
		if (amount <= 0) {
			throw new Error("Amount must be greater than 0");
		}

		// Check XTZ for fees
		const balance = await Tezos.tz.getBalance(walletAddress);
		if (balance.toNumber() < 100000) {
			throw new Error("Insufficient XTZ for transaction fees");
		}

		try {
			const contract = await Tezos.contract.at(tokenAddress);

			// FA2 transfer parameter format
			const transferParams = [
				{
					from_: walletAddress,
					txs: [
						{
							to_: to,
							token_id: tokenId,
							amount: amount,
						},
					],
				},
			];

			let operation;
			try {
				operation = await contract.methods.transfer(transferParams).send();
			} catch (err: unknown) {
				const message = err instanceof Error ? err.message : String(err);
				if (message.includes("FA2_INSUFFICIENT_BALANCE")) {
					throw new Error(
						`Insufficient token balance. Use tezos_get_token_balance to check your balance.`
					);
				}
				if (message.includes("FA2_TOKEN_UNDEFINED")) {
					throw new Error(`Token ID ${tokenId} does not exist`);
				}
				if (message.includes("FA2_NOT_OPERATOR")) {
					throw new Error(`Not authorized to transfer tokens`);
				}
				throw new Error(`Transfer failed: ${message}`);
			}

			await operation.confirmation(CONFIRMATIONS_TO_WAIT);

			const opHash = operation.hash;
			const explorerUrl = `${tzktUrl}/${opHash}`;

			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						success: true,
						message: `Transferred ${amount} tokens`,
						transfer: {
							tokenAddress,
							tokenId,
							from: walletAddress,
							to,
							amount,
							opHash,
							explorerUrl,
						},
					}, null, 2),
				}],
			};
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`FA2 transfer failed: ${message}`);
		}
	},
});

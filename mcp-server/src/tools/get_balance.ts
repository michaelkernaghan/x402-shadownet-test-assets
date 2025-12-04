import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

const MUTEZ_PER_TEZ = 1_000_000;

const inputSchema = z.object({
	address: z.string().optional().describe("Address to check (default: wallet address)"),
});

type GetBalanceParams = z.infer<typeof inputSchema>;

export const createGetBalanceTool = (
	Tezos: TezosToolkit,
	walletAddress: string
) => ({
	name: "tezos_get_balance",
	config: {
		title: "Get XTZ Balance",
		description: "Returns the XTZ balance of an address (defaults to wallet address)",
		inputSchema,
		annotations: {
			readOnlyHint: true,
			destructiveHint: false,
			idempotentHint: true,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as GetBalanceParams;
		const address = parsed.address || walletAddress;

		// Validate address
		if (!address.match(/^(tz1|tz2|tz3|KT1)[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid address format: ${address}`);
		}

		try {
			const balanceMutez = await Tezos.tz.getBalance(address);
			const balanceXtz = balanceMutez.toNumber() / MUTEZ_PER_TEZ;

			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						address,
						balanceMutez: balanceMutez.toString(),
						balanceXtz: balanceXtz,
						message: `Balance: ${balanceXtz} XTZ (${balanceMutez.toString()} mutez)`,
					}, null, 2),
				}],
			};
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`Failed to get balance: ${message}`);
		}
	},
});

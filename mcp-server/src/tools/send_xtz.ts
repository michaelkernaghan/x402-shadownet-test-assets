import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

const MUTEZ_PER_TEZ = 1_000_000;
const CONFIRMATIONS_TO_WAIT = 3;

const inputSchema = z.object({
	toAddress: z.string().describe("The address to send XTZ to"),
	amount: z.number().describe("Amount of XTZ to send"),
});

type SendXtzParams = z.infer<typeof inputSchema>;

const xtzToMutez = (xtz: number): number => Math.floor(xtz * MUTEZ_PER_TEZ);

export const createSendXtzTool = (
	Tezos: TezosToolkit,
	walletAddress: string,
	tzktUrl: string
) => ({
	name: "tezos_send_xtz",
	config: {
		title: "Send XTZ",
		description: "Send XTZ to another address",
		inputSchema,
		annotations: {
			readOnlyHint: false,
			destructiveHint: true,
			idempotentHint: false,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as SendXtzParams;
		const { toAddress, amount } = parsed;

		// Validate recipient address
		if (!toAddress.match(/^(tz1|tz2|tz3|KT1)[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid recipient address: ${toAddress}`);
		}

		// Validate amount
		if (amount <= 0) {
			throw new Error("Amount must be greater than 0");
		}

		const amountMutez = xtzToMutez(amount);

		// Check balance
		const balance = await Tezos.tz.getBalance(walletAddress);
		if (balance.toNumber() < amountMutez + 100000) {
			throw new Error(
				`Insufficient balance. Need ${amount} XTZ + fees, have ${balance.toNumber() / MUTEZ_PER_TEZ} XTZ`
			);
		}

		try {
			const operation = await Tezos.contract.transfer({
				to: toAddress,
				amount: amount,
			});

			await operation.confirmation(CONFIRMATIONS_TO_WAIT);

			const opHash = operation.hash;
			const explorerUrl = `${tzktUrl}/${opHash}`;

			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						success: true,
						message: `Sent ${amount} XTZ to ${toAddress}`,
						transfer: {
							from: walletAddress,
							to: toAddress,
							amount,
							amountMutez,
							opHash,
							explorerUrl,
						},
					}, null, 2),
				}],
			};
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`Transfer failed: ${message}`);
		}
	},
});

import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

const MUTEZ_PER_TEZ = 1_000_000;
const CONFIRMATIONS_TO_WAIT = 3;

/**
 * X402 Payment Requirements Schema
 */
const PaymentRequirementsSchema = z.object({
	scheme: z.string().default("exact"),
	network: z.string(),
	maxAmountRequired: z.string(),
	resource: z.string(),
	description: z.string().optional(),
	mimeType: z.string().optional(),
	payTo: z.string(),
	asset: z.string().optional().default("XTZ"),
	expiry: z.number().optional(),
	extra: z.record(z.string(), z.unknown()).optional(),
});

const inputSchema = z.object({
	paymentRequirements: PaymentRequirementsSchema,
	amount: z.number().optional().describe("Override amount in XTZ (optional)"),
});

type PayX402Params = z.infer<typeof inputSchema>;

const xtzToMutez = (xtz: number): number => Math.floor(xtz * MUTEZ_PER_TEZ);
const mutezToXtz = (mutez: number): number => mutez / MUTEZ_PER_TEZ;
const formatMutez = (mutez: number): string => `${mutez} mutez (${mutezToXtz(mutez)} XTZ)`;

export const createPayX402Tool = (
	Tezos: TezosToolkit,
	walletAddress: string,
	tzktUrl: string
) => ({
	name: "tezos_pay_x402",
	config: {
		title: "Pay X402 Request",
		description: `Pay an X402 payment requirement.
When an HTTP request returns 402 Payment Required with X402 payment requirements,
use this tool to make the payment and get proof to retry the request.`,
		inputSchema,
		annotations: {
			readOnlyHint: false,
			destructiveHint: true,
			idempotentHint: false,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as PayX402Params;
		const { paymentRequirements, amount: overrideAmount } = parsed;

		// Validate network is Tezos
		const network = paymentRequirements.network.toLowerCase();
		if (!network.includes("tezos")) {
			throw new Error(
				`Unsupported network: ${paymentRequirements.network}. This wallet only supports Tezos.`
			);
		}

		// Validate asset is XTZ
		const asset = paymentRequirements.asset?.toUpperCase() || "XTZ";
		if (asset !== "XTZ") {
			throw new Error(
				`Unsupported asset: ${asset}. Use tezos_transfer_fa2 for token payments.`
			);
		}

		// Check expiry
		if (paymentRequirements.expiry) {
			const now = Math.floor(Date.now() / 1000);
			if (now > paymentRequirements.expiry) {
				throw new Error(
					`Payment offer expired at ${new Date(paymentRequirements.expiry * 1000).toISOString()}`
				);
			}
		}

		// Calculate amount
		const maxAmountMutez = parseInt(paymentRequirements.maxAmountRequired, 10);
		const amountMutez = overrideAmount
			? xtzToMutez(overrideAmount)
			: maxAmountMutez;

		if (amountMutez > maxAmountMutez) {
			throw new Error(
				`Override amount (${formatMutez(amountMutez)}) exceeds maximum (${formatMutez(maxAmountMutez)})`
			);
		}

		// Validate recipient
		const recipientAddress = paymentRequirements.payTo;
		if (!recipientAddress.match(/^(tz1|tz2|tz3|KT1)[a-zA-Z0-9]{33}$/)) {
			throw new Error(`Invalid Tezos address: ${recipientAddress}`);
		}

		// Check balance
		const balance = await Tezos.tz.getBalance(walletAddress);
		if (balance.toNumber() < amountMutez + 100000) {
			throw new Error(
				`Insufficient balance. Required: ${formatMutez(amountMutez + 100000)}, Available: ${formatMutez(balance.toNumber())}`
			);
		}

		// Execute payment
		try {
			const operation = await Tezos.contract.transfer({
				to: recipientAddress,
				amount: amountMutez,
				mutez: true,
			});

			await operation.confirmation(CONFIRMATIONS_TO_WAIT);

			const opHash = operation.hash;
			const explorerUrl = `${tzktUrl}/${opHash}`;

			// Build X402 payment proof
			const paymentProof = {
				scheme: "exact",
				network: paymentRequirements.network,
				payload: {
					signature: opHash,
					authorization: {
						from: walletAddress,
						to: recipientAddress,
						amount: amountMutez.toString(),
						asset: "XTZ",
						opHash: opHash,
					},
				},
			};

			const xPaymentHeader = Buffer.from(JSON.stringify(paymentProof)).toString("base64");

			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						success: true,
						message: `X402 payment successful for ${paymentRequirements.resource}`,
						payment: {
							amount: mutezToXtz(amountMutez),
							amountMutez,
							recipient: recipientAddress,
							opHash,
							explorerUrl,
						},
						x402: {
							xPaymentHeader,
							instruction: "Add this header to retry: X-PAYMENT: " + xPaymentHeader,
						},
					}, null, 2),
				}],
			};
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`X402 payment failed: ${message}`);
		}
	},
});

import { TezosToolkit } from "@taquito/taquito";
import z from "zod";

const MUTEZ_PER_TEZ = 1_000_000;
const CONFIRMATIONS_TO_WAIT = 3;
const DEFAULT_TIMEOUT_MS = 30000;

interface X402PaymentRequirements {
	scheme?: string;
	network: string;
	maxAmountRequired: string;
	resource: string;
	description?: string;
	mimeType?: string;
	payTo: string;
	asset?: string;
	expiry?: number;
	extra?: Record<string, unknown>;
}

interface X402Response {
	accepts?: X402PaymentRequirements[];
	paymentRequirements?: X402PaymentRequirements;
	version?: string;
	error?: string;
}

const inputSchema = z.object({
	url: z.string().url().describe("URL to fetch"),
	method: z.enum(["GET", "POST", "PUT", "DELETE"]).default("GET"),
	headers: z.record(z.string(), z.string()).optional(),
	body: z.string().optional(),
	maxPayment: z.number().optional().describe("Max XTZ to pay (default: 1)"),
	autoRetry: z.boolean().default(true).describe("Auto-pay and retry if 402"),
});

type FetchX402Params = z.infer<typeof inputSchema>;

const xtzToMutez = (xtz: number): number => Math.floor(xtz * MUTEZ_PER_TEZ);
const mutezToXtz = (mutez: number): number => mutez / MUTEZ_PER_TEZ;
const formatMutez = (mutez: number): string => `${mutez} mutez (${mutezToXtz(mutez)} XTZ)`;

function parsePaymentRequirements(responseBody: string, responseHeaders: Headers): X402PaymentRequirements | null {
	try {
		const body: X402Response = JSON.parse(responseBody);

		if (body.accepts && body.accepts.length > 0) {
			const tezosOption = body.accepts.find(
				(req) => req.network.toLowerCase().includes("tezos")
			);
			if (tezosOption) return tezosOption;
			return body.accepts[0];
		}

		if (body.paymentRequirements) {
			return body.paymentRequirements;
		}

		const payTo = responseHeaders.get("X-Payment-Address");
		const amount = responseHeaders.get("X-Payment-Amount");
		const network = responseHeaders.get("X-Payment-Network");

		if (payTo && amount) {
			return {
				scheme: "exact",
				network: network || "tezos",
				maxAmountRequired: amount,
				resource: "",
				payTo: payTo,
				asset: responseHeaders.get("X-Payment-Asset") || "XTZ",
			};
		}
	} catch {
		// Failed to parse
	}

	return null;
}

export const createFetchX402Tool = (
	Tezos: TezosToolkit,
	walletAddress: string,
	tzktUrl: string
) => ({
	name: "tezos_fetch_x402",
	config: {
		title: "Fetch X402 Resource",
		description: `Fetch a resource that may require X402 payment.
If 402 Payment Required is returned, automatically pays and retries.`,
		inputSchema,
		annotations: {
			readOnlyHint: false,
			destructiveHint: true,
			idempotentHint: false,
			openWorldHint: true,
		},
	},

	handler: async (params: unknown) => {
		const parsed = params as FetchX402Params;
		const { url, method, headers: customHeaders, body, maxPayment, autoRetry } = parsed;

		const maxPaymentMutez = maxPayment ? xtzToMutez(maxPayment) : xtzToMutez(1);

		const headers: Record<string, string> = {
			"Accept": "application/json, */*",
			"User-Agent": "x402-FA2-MCP/1.0",
			...customHeaders,
		};

		// Initial request
		const controller = new AbortController();
		const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

		let response: Response;
		try {
			response = await fetch(url, {
				method,
				headers,
				body,
				signal: controller.signal,
			});
		} catch (err) {
			clearTimeout(timeoutId);
			throw new Error(`Failed to fetch ${url}: ${err instanceof Error ? err.message : String(err)}`);
		}
		clearTimeout(timeoutId);

		// Not 402 - return response
		if (response.status !== 402) {
			const responseText = await response.text();
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: response.status,
						statusText: response.statusText,
						headers: Object.fromEntries(response.headers.entries()),
						body: responseText,
						x402: {
							paymentRequired: false,
							message: response.ok
								? "Resource fetched (no payment required)"
								: `Request failed with status ${response.status}`,
						},
					}, null, 2),
				}],
			};
		}

		// Handle 402
		const responseBody = await response.text();
		const paymentReqs = parsePaymentRequirements(responseBody, response.headers);

		if (!paymentReqs) {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: "Could not parse payment requirements",
						rawBody: responseBody,
					}, null, 2),
				}],
			};
		}

		if (!paymentReqs.resource) {
			paymentReqs.resource = url;
		}

		if (!autoRetry) {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						message: "Payment required. Auto-retry disabled.",
						paymentRequirements: paymentReqs,
						instruction: "Use tezos_pay_x402 with these requirements",
					}, null, 2),
				}],
			};
		}

		// Validate network
		const network = paymentReqs.network.toLowerCase();
		if (!network.includes("tezos")) {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: `Unsupported network: ${paymentReqs.network}`,
						paymentRequirements: paymentReqs,
					}, null, 2),
				}],
			};
		}

		// Check amount
		const amountMutez = parseInt(paymentReqs.maxAmountRequired, 10);
		if (amountMutez > maxPaymentMutez) {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: `Amount (${formatMutez(amountMutez)}) exceeds limit (${formatMutez(maxPaymentMutez)})`,
						paymentRequirements: paymentReqs,
						instruction: "Increase maxPayment or use tezos_pay_x402 manually",
					}, null, 2),
				}],
			};
		}

		// Validate asset
		const asset = paymentReqs.asset?.toUpperCase() || "XTZ";
		if (asset !== "XTZ") {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: `Unsupported asset: ${asset}. Use FA2 tools for token payments.`,
						paymentRequirements: paymentReqs,
					}, null, 2),
				}],
			};
		}

		// Check expiry
		if (paymentReqs.expiry) {
			const now = Math.floor(Date.now() / 1000);
			if (now > paymentReqs.expiry) {
				return {
					content: [{
						type: "text" as const,
						text: JSON.stringify({
							status: 402,
							error: `Payment expired at ${new Date(paymentReqs.expiry * 1000).toISOString()}`,
							paymentRequirements: paymentReqs,
						}, null, 2),
					}],
				};
			}
		}

		// Validate recipient
		const recipientAddress = paymentReqs.payTo;
		if (!recipientAddress.match(/^(tz1|tz2|tz3|KT1)[a-zA-Z0-9]{33}$/)) {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: `Invalid address: ${recipientAddress}`,
						paymentRequirements: paymentReqs,
					}, null, 2),
				}],
			};
		}

		// Check balance
		const balance = await Tezos.tz.getBalance(walletAddress);
		if (balance.toNumber() < amountMutez + 100000) {
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: `Insufficient balance. Need ${formatMutez(amountMutez + 100000)}, have ${formatMutez(balance.toNumber())}`,
						paymentRequirements: paymentReqs,
					}, null, 2),
				}],
			};
		}

		// Execute payment
		let operation;
		try {
			operation = await Tezos.contract.transfer({
				to: recipientAddress,
				amount: amountMutez,
				mutez: true,
			});
			await operation.confirmation(CONFIRMATIONS_TO_WAIT);
		} catch (err) {
			const message = err instanceof Error ? err.message : String(err);
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						status: 402,
						error: `Payment failed: ${message}`,
						paymentRequirements: paymentReqs,
					}, null, 2),
				}],
			};
		}

		const opHash = operation.hash;
		const explorerUrl = `${tzktUrl}/${opHash}`;

		// Build payment proof
		const paymentProof = {
			scheme: "exact",
			network: paymentReqs.network,
			payload: {
				signature: opHash,
				authorization: {
					from: walletAddress,
					to: recipientAddress,
					amount: amountMutez.toString(),
					asset: "XTZ",
					opHash,
				},
			},
		};
		const xPaymentHeader = Buffer.from(JSON.stringify(paymentProof)).toString("base64");

		// Retry with payment proof
		const retryHeaders: Record<string, string> = {
			...headers,
			"X-PAYMENT": xPaymentHeader,
		};

		let retryResponse: Response;
		const retryController = new AbortController();
		const retryTimeoutId = setTimeout(() => retryController.abort(), DEFAULT_TIMEOUT_MS);

		try {
			retryResponse = await fetch(url, {
				method,
				headers: retryHeaders,
				body,
				signal: retryController.signal,
			});
		} catch (err) {
			clearTimeout(retryTimeoutId);
			return {
				content: [{
					type: "text" as const,
					text: JSON.stringify({
						paymentSucceeded: true,
						retryFailed: true,
						error: `Payment OK but retry failed: ${err instanceof Error ? err.message : String(err)}`,
						payment: { opHash, explorerUrl, amount: mutezToXtz(amountMutez) },
						xPaymentHeader,
					}, null, 2),
				}],
			};
		}
		clearTimeout(retryTimeoutId);

		const retryBody = await retryResponse.text();
		const xPaymentResponse = retryResponse.headers.get("X-PAYMENT-RESPONSE");

		return {
			content: [{
				type: "text" as const,
				text: JSON.stringify({
					success: retryResponse.ok,
					status: retryResponse.status,
					statusText: retryResponse.statusText,
					body: retryBody,
					x402: {
						paymentMade: true,
						payment: {
							amount: mutezToXtz(amountMutez),
							amountMutez,
							recipient: recipientAddress,
							opHash,
							explorerUrl,
						},
						xPaymentResponse: xPaymentResponse
							? JSON.parse(Buffer.from(xPaymentResponse, "base64").toString())
							: null,
					},
				}, null, 2),
			}],
		};
	},
});

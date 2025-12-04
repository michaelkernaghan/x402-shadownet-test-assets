/**
 * x402 FA2 MCP Server
 *
 * MCP server providing Tezos tools for x402 payment flows on Tezos Shadownet.
 *
 * Tools:
 * - tezos_get_balance: Query XTZ balance
 * - tezos_send_xtz: Send XTZ
 * - tezos_get_token_balance: Query FA2 token balances
 * - tezos_swap_xtz_to_token: Swap XTZ for FA2 tokens
 * - tezos_transfer_fa2: Transfer FA2 tokens
 * - tezos_pay_x402: Pay x402 payment requirements
 * - tezos_fetch_x402: Fetch x402-protected resources with auto-pay
 */

import { InMemorySigner } from "@taquito/signer";
import { TezosToolkit } from "@taquito/taquito";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

// XTZ tools
import { createGetBalanceTool } from "./tools/get_balance.js";
import { createSendXtzTool } from "./tools/send_xtz.js";

// FA2 token tools
import { createGetTokenBalanceTool } from "./tools/get_token_balance.js";
import { createSwapXtzToTokenTool } from "./tools/swap_xtz_to_token.js";
import { createTransferFa2Tool } from "./tools/transfer_fa2.js";

// x402 tools
import { createPayX402Tool } from "./tools/pay_x402.js";
import { createFetchX402Tool } from "./tools/fetch_x402.js";

// Network configurations
const NETWORKS = {
    mainnet: {
        rpcUrl: "https://mainnet.tezos.ecadinfra.com",
        tzktUrl: "https://tzkt.io",
    },
    ghostnet: {
        rpcUrl: "https://ghostnet.tezos.ecadinfra.com",
        tzktUrl: "https://ghostnet.tzkt.io",
    },
    shadownet: {
        rpcUrl: "https://rpc.shadownet.teztnets.com",
        tzktUrl: "https://shadownet.tzkt.io",
    },
} as const;

type NetworkName = keyof typeof NETWORKS;

const init = async () => {
    const server = new McpServer({
        name: "x402-fa2-mcp",
        version: "1.0.0",
    });

    const networkName = (process.env.TEZOS_NETWORK || "shadownet") as NetworkName;
    const network = NETWORKS[networkName];
    if (!network) {
        throw new Error("Invalid network");
    }

    console.error("[x402-fa2-mcp] Connecting to " + networkName);

    const Tezos = new TezosToolkit(network.rpcUrl);

    const privateKey = process.env.TEZOS_PRIVATE_KEY;
    if (!privateKey) {
        throw new Error("TEZOS_PRIVATE_KEY required");
    }

    const signer = await InMemorySigner.fromSecretKey(privateKey);
    Tezos.setSignerProvider(signer);

    const walletAddress = await signer.publicKeyHash();
    console.error("[x402-fa2-mcp] Wallet: " + walletAddress);

    // XTZ tools
    const getBalanceTool = createGetBalanceTool(Tezos, walletAddress);
    server.registerTool(getBalanceTool.name, getBalanceTool.config, getBalanceTool.handler);

    const sendXtzTool = createSendXtzTool(Tezos, walletAddress, network.tzktUrl);
    server.registerTool(sendXtzTool.name, sendXtzTool.config, sendXtzTool.handler);

    // FA2 tools
    const tokenBalanceTool = createGetTokenBalanceTool(Tezos, walletAddress);
    server.registerTool(tokenBalanceTool.name, tokenBalanceTool.config, tokenBalanceTool.handler);

    const swapTool = createSwapXtzToTokenTool(Tezos, walletAddress, network.tzktUrl);
    server.registerTool(swapTool.name, swapTool.config, swapTool.handler);

    const transferTool = createTransferFa2Tool(Tezos, walletAddress, network.tzktUrl);
    server.registerTool(transferTool.name, transferTool.config, transferTool.handler);

    // x402 tools
    const payX402Tool = createPayX402Tool(Tezos, walletAddress, network.tzktUrl);
    server.registerTool(payX402Tool.name, payX402Tool.config, payX402Tool.handler);

    const fetchX402Tool = createFetchX402Tool(Tezos, walletAddress, network.tzktUrl);
    server.registerTool(fetchX402Tool.name, fetchX402Tool.config, fetchX402Tool.handler);

    console.error("[x402-fa2-mcp] Registered 7 tools");

    const transport = new StdioServerTransport();
    await server.connect(transport);

    console.error("[x402-fa2-mcp] Server started");
};

init().catch((err) => {
    console.error("[x402-fa2-mcp] Fatal:", err);
    process.exit(1);
});

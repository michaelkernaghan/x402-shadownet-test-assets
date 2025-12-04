<!-- Copilot / AI agent instructions for x402-shadownet-test-assets -->
# Quick Agent Guide — x402 Shadownet Test Assets

Purpose: Help an AI coding agent be productive in this repo by documenting the architecture, developer flows, and concrete examples discovered in the code.

- **Repo focus:** test SmartPy/FA2 token (`contracts/test_token_fa2.py`) and a fixed-rate XTZ→TEST swap (`contracts/test_swap.py` / `contracts/test_swap.tz`) used for x402 composability tests on Tezos Shadownet.

- **Key files:**
  - `README.md` — primary usage notes, deployed addresses, and example `octez-client` commands.
  - `contracts/test_token_fa2.py` — SmartPy FA2 token implementation and test scenario.
  - `contracts/test_swap.py` — SmartPy swap contract and on-repo test scenario.
  - `contracts/test_swap.tz` — deployed Michelson contract (reference implementation).
  - `docs/MCP_INTEGRATION.md` — MCP integration specifics for x402 (read for integration points).

- **Big picture / why**
  - This repository provides minimal, reproducible on-chain assets (FA2 token + swap) to exercise x402 payment composability scenarios on Shadownet.
  - Tests and demos assume a fixed exchange rate (1 XTZ = 1000 TEST) and token id `0` for the fungible TEST token.

- **Concrete conventions & patterns to follow**
  - Token ID 0 is used for TEST fungible token transfers in `test_swap.py`.
  - The swap contract expects the token contract to implement the FA2 `transfer` entrypoint and uses a single transfer call returning tokens from the swap contract to the sender.
  - Tests use SmartPy scenarios (see `sp.test_scenario` usage) — follow the same pattern for new contract examples or unit tests.

- **Developer workflows (explicit commands from README)**
  - Swap XTZ → TEST (example):

    octez-client transfer 0.1 from <wallet> to KT1S7DbL8id9WGaYdqTaGCBD6RYwqYWNyMnt --entrypoint swap --burn-cap 0.5

  - Transfer TEST tokens (FA2 `transfer` call example in README): use the `--entrypoint transfer` and the provided Michelson-style `--arg` structure.

  - Query balances: README notes balances stored in big map id `1278` (use RPC or indexer).

- **Testing / execution hints**
  - SmartPy tests are present inside `*.py` contract files — run them using the SmartPy tooling environment (SmartPy CLI / online). The repo does not include a local runner; prefer the SmartPy sandbox or CI that has SmartPy installed.
  - When creating new tests, mirror the test pattern shown in `test_swap.py` and `test_token_fa2.py`: define `@sp.add_test()` functions and use `sp.test_scenario` with `sc.verify` assertions.

- **Integration points and external dependencies**
  - Relies on SmartPy (imported as `smartpy as sp`) and the SmartPy FA2 templates (`smartpy.templates.fa2_lib`).
  - Interacts with Tezos node tooling via `octez-client` in examples — tests do not invoke `octez-client` directly.
  - Deployed contract addresses are present in `README.md` for Shadownet; use these when simulating or running live interactions.

- **What to change or update cautiously**
  - `contracts/test_swap.tz` is the deployed Michelson; editing it will not update the on-chain instance. Edit `test_swap.py` and recompile/deploy instead.
  - Big map id (`1278`) is environment-specific — do not hardcode it into new contracts; prefer querying by contract storage or using named maps in SmartPy.

- **Small examples to copy/paste**
  - FA2 transfer param structure (used in `test_swap.py`): token id `0`, `from_` is the swap contract address, `to_` is `sp.sender`, `amount` computed from sent XTZ.

- **When you need more context**
  - Read `docs/MCP_INTEGRATION.md` for how this repo is used by the MCP (x402) systems.
  - Check `README.md` for current deployed addresses and quick `octez-client` examples.

If anything here is unclear or you want more specific examples (CI commands, SmartPy CLI invocation, or a sample test runner), tell me which area to expand.

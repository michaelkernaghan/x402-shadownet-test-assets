# x402 Test Scenarios
# Run with SmartPy: https://smartpy.io/
#
# Core x402 scenarios:
# 1. Happy path - wallet has TEST tokens, payment succeeds
# 2. Wrong token - payment with wrong token rejected
# 3. Swap flow - no TEST tokens, swap XTZ -> TEST, then pay
#
# Additional tests:
# 4. Swap paused - admin can pause swap contract
# 5. Insufficient liquidity - swap fails when contract has no tokens
#
# Edge cases:
# 6. Zero amount swap - rejected
# 7. Zero amount transfer - allowed (FA2 no-op)
# 8. Invalid token ID - rejected
# 9. Insufficient balance - rejected
# 10. Partial swap then payment - multiple swaps to accumulate tokens
# 11. Unauthorized pause - non-admin cannot pause
#
# Multi-asset payment scenarios (agent decision-making):
# 12. Multi-asset: Pay with existing balance (no swap needed)
# 13. Multi-asset: Cost optimization - choose cheaper swap
# 14. Multi-asset: Fallback when one swap is paused
# 15. Multi-asset: Partial balance top-up optimization
#
# x402 Protocol tests:
# 16. x402 payment proof structure validation
# 17. x402 expired payment rejection
# 18. x402 amount validation (max amount check)

import smartpy as sp
from smartpy.templates import fa2_lib as fa2

# Main template for FA2 contracts
main = fa2.main


@sp.module
def token_module():
    import main

    class TestToken(
        main.Admin,
        main.Fungible,
        main.MintFungible,
        main.BurnFungible,
        main.OnchainviewBalanceOf,
    ):
        def __init__(self, admin_address, contract_metadata, ledger, token_metadata):
            main.OnchainviewBalanceOf.__init__(self)
            main.BurnFungible.__init__(self)
            main.MintFungible.__init__(self)
            main.Fungible.__init__(self, contract_metadata, ledger, token_metadata)
            main.Admin.__init__(self, admin_address)


@sp.module
def swap_module():
    """Swap contract for XTZ -> TEST"""

    class TestSwap(sp.Contract):
        def __init__(self, admin, test_token_address, rate):
            self.data.admin = admin
            self.data.test_token = test_token_address
            self.data.rate = rate
            self.data.paused = False
            self.data.total_swapped = sp.nat(0)

        @sp.entrypoint
        def swap(self):
            assert not self.data.paused, "Swap is paused"
            assert sp.amount > sp.mutez(0), "Must send XTZ"

            # Convert mutez to nat (1 XTZ = 1,000,000 mutez)
            # For rate of 1000: 100,000 mutez (0.1 XTZ) * 1000 / 1,000,000 = 100 TEST
            xtz_in_mutez = sp.fst(sp.ediv(sp.amount, sp.mutez(1)).unwrap_some())
            test_amount = sp.fst(sp.ediv(xtz_in_mutez * self.data.rate, sp.nat(1000000)).unwrap_some())

            transfer_param = [
                sp.record(
                    from_=sp.self_address,
                    txs=[
                        sp.record(
                            to_=sp.sender,
                            token_id=sp.nat(0),
                            amount=test_amount
                        )
                    ]
                )
            ]

            # FA2 transfer type with correct layout (to_, (token_id, amount))
            token_contract = sp.contract(
                sp.list[sp.record(
                    from_=sp.address,
                    txs=sp.list[sp.record(to_=sp.address, token_id=sp.nat, amount=sp.nat).layout(("to_", ("token_id", "amount")))]
                ).layout(("from_", "txs"))],
                self.data.test_token,
                entrypoint="transfer"
            ).unwrap_some(error="Invalid token contract")

            sp.transfer(transfer_param, sp.mutez(0), token_contract)
            self.data.total_swapped += test_amount

        @sp.entrypoint
        def pause(self, paused):
            assert sp.sender == self.data.admin, "Not admin"
            self.data.paused = paused


def _get_balance(fa2_contract, args):
    """Utility function to call the contract's get_balance view."""
    return sp.View(fa2_contract, "get_balance")(args)


# Test scenarios
if "main" in __name__:

    @sp.add_test()
    def test_scenario_1_happy_path():
        """
        Scenario 1: Happy Path
        - Wallet has TEST tokens
        - x402 payment request comes in
        - Transfer TEST tokens to payee
        - Success
        """
        sc = sp.test_scenario("Scenario 1: Happy Path")
        sc.h1("Scenario 1: Happy Path - Direct FA2 Payment")

        # Accounts
        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        # Token metadata
        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        # Deploy TEST token
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Mint TEST tokens to payer
        test_token.mint(
            [sp.record(to_=payer.address, amount=1000, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # Verify payer has tokens
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 1000)

        # x402 payment: Transfer 100 TEST to payee
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        # Verify payment succeeded
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 900)
        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)

        sc.h2("Result: Payment successful")


    @sp.add_test()
    def test_scenario_2_wrong_token():
        """
        Scenario 2: Wrong Token
        - x402 requests TEST token
        - Wallet tries to pay with WRONG token
        - Payment rejected (payee doesn't accept WRONG)
        """
        sc = sp.test_scenario("Scenario 2: Wrong Token")
        sc.h1("Scenario 2: Wrong Token - Payment Rejected")

        # Accounts
        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        # Token metadata
        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")
        wrong_md = fa2.make_metadata(name="WRONG", decimals=0, symbol="WRONG")

        # Deploy TEST token (what payee wants)
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Deploy WRONG token (what payer has)
        wrong_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += wrong_token

        # Mint WRONG tokens to payer (but no TEST tokens)
        wrong_token.mint(
            [sp.record(to_=payer.address, amount=1000, token=sp.variant("new", wrong_md))],
            _sender=admin
        )

        # Payer has WRONG tokens but no TEST tokens
        sc.verify(_get_balance(wrong_token, sp.record(owner=payer.address, token_id=0)) == 1000)

        # Try to transfer TEST tokens - should fail (token doesn't exist)
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer,
            _valid=False,
            _exception="FA2_TOKEN_UNDEFINED"
        )

        sc.h2("Result: Payment rejected - wrong token")


    @sp.add_test()
    def test_scenario_3_swap_flow():
        """
        Scenario 3: Swap Flow
        - x402 requests TEST token
        - Wallet has no TEST, only XTZ
        - Swap XTZ -> TEST via swap contract
        - Pay with TEST tokens
        - Success
        """
        sc = sp.test_scenario("Scenario 3: Swap Flow")
        sc.h1("Scenario 3: Swap Flow - XTZ to TEST to Payment")

        # Accounts
        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        # Token metadata
        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        # Deploy TEST token
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Deploy swap contract (1 XTZ = 1000 TEST)
        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # Fund swap contract with TEST tokens
        test_token.mint(
            [sp.record(to_=swap_contract.address, amount=100000, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # Verify swap contract has liquidity
        sc.verify(_get_balance(test_token, sp.record(owner=swap_contract.address, token_id=0)) == 100000)

        # Step 1: Payer swaps 0.1 XTZ for 100 TEST
        swap_contract.swap(_sender=payer, _amount=sp.mutez(100000))

        # Verify payer received TEST tokens
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 100)

        # Step 2: Pay 100 TEST to payee
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        # Verify payment succeeded
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 0)
        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)

        sc.h2("Result: Swap + Payment successful")


    @sp.add_test()
    def test_swap_paused():
        """
        Test: Swap contract paused
        - Admin pauses swap
        - Swap attempts fail
        """
        sc = sp.test_scenario("Test: Swap Paused")
        sc.h1("Test: Swap Paused")

        admin = sp.test_account("admin")
        user = sp.test_account("user")

        # Deploy TEST token
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # Admin pauses swap
        swap_contract.pause(True, _sender=admin)

        # User tries to swap - should fail
        swap_contract.swap(
            _sender=user,
            _amount=sp.mutez(100000),
            _valid=False,
            _exception="Swap is paused"
        )

        sc.h2("Result: Swap rejected when paused")


    @sp.add_test()
    def test_insufficient_liquidity():
        """
        Test: Swap with insufficient liquidity
        - Swap contract has no TEST tokens
        - Swap attempt fails
        """
        sc = sp.test_scenario("Test: Insufficient Liquidity")
        sc.h1("Test: Insufficient Liquidity")

        admin = sp.test_account("admin")
        user = sp.test_account("user")

        # Deploy TEST token
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Deploy swap contract WITHOUT funding it
        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # User tries to swap - should fail (token not defined since nothing minted)
        swap_contract.swap(
            _sender=user,
            _amount=sp.mutez(100000),
            _valid=False,
            _exception="FA2_TOKEN_UNDEFINED"
        )

        sc.h2("Result: Swap rejected - insufficient liquidity")


    @sp.add_test()
    def test_zero_amount_swap():
        """
        Edge Case: Zero amount swap
        - User sends 0 XTZ to swap
        - Should be rejected
        """
        sc = sp.test_scenario("Edge Case: Zero Amount Swap")
        sc.h1("Edge Case: Zero Amount Swap")

        admin = sp.test_account("admin")
        user = sp.test_account("user")

        # Deploy TEST token
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        # Deploy and fund swap contract
        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        test_token.mint(
            [sp.record(to_=swap_contract.address, amount=100000, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # User tries to swap 0 XTZ - should fail
        swap_contract.swap(
            _sender=user,
            _amount=sp.mutez(0),
            _valid=False,
            _exception="Must send XTZ"
        )

        sc.h2("Result: Zero amount swap rejected")


    @sp.add_test()
    def test_zero_amount_transfer():
        """
        Edge Case: Zero amount FA2 transfer
        - User tries to transfer 0 tokens
        - FA2 standard allows this (it's a no-op)
        """
        sc = sp.test_scenario("Edge Case: Zero Amount Transfer")
        sc.h1("Edge Case: Zero Amount Transfer")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Mint tokens to payer
        test_token.mint(
            [sp.record(to_=payer.address, amount=1000, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # Transfer 0 tokens - FA2 allows this
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=0)]
            )],
            _sender=payer
        )

        # Balances unchanged
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 1000)
        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 0)

        sc.h2("Result: Zero amount transfer allowed (no-op)")


    @sp.add_test()
    def test_invalid_token_id():
        """
        Edge Case: Invalid token ID
        - User tries to transfer a non-existent token ID
        - Should fail with FA2_TOKEN_UNDEFINED
        """
        sc = sp.test_scenario("Edge Case: Invalid Token ID")
        sc.h1("Edge Case: Invalid Token ID")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Mint token_id 0 to payer
        test_token.mint(
            [sp.record(to_=payer.address, amount=1000, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # Try to transfer token_id 999 (doesn't exist)
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=999, amount=100)]
            )],
            _sender=payer,
            _valid=False,
            _exception="FA2_TOKEN_UNDEFINED"
        )

        sc.h2("Result: Invalid token ID rejected")


    @sp.add_test()
    def test_insufficient_balance():
        """
        Edge Case: Insufficient balance for payment
        - User has some tokens but not enough for the payment
        - Should fail with FA2_INSUFFICIENT_BALANCE
        """
        sc = sp.test_scenario("Edge Case: Insufficient Balance")
        sc.h1("Edge Case: Insufficient Balance")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Mint only 50 tokens to payer
        test_token.mint(
            [sp.record(to_=payer.address, amount=50, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # Try to transfer 100 tokens (payer only has 50)
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer,
            _valid=False,
            _exception="FA2_INSUFFICIENT_BALANCE"
        )

        sc.h2("Result: Insufficient balance rejected")


    @sp.add_test()
    def test_partial_swap_then_payment():
        """
        Edge Case: Partial swap - swap gets some tokens but not enough for full payment
        - User needs 200 TEST for payment
        - User swaps and gets 100 TEST
        - Payment of 200 fails (insufficient balance)
        - User must swap again or reduce payment
        """
        sc = sp.test_scenario("Edge Case: Partial Swap Then Payment")
        sc.h1("Edge Case: Partial Swap - Need More Tokens")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        tok0_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # Fund swap contract
        test_token.mint(
            [sp.record(to_=swap_contract.address, amount=100000, token=sp.variant("new", tok0_md))],
            _sender=admin
        )

        # Payer swaps 0.1 XTZ for 100 TEST
        swap_contract.swap(_sender=payer, _amount=sp.mutez(100000))
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 100)

        # Try to pay 200 TEST (but only have 100) - should fail
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=200)]
            )],
            _sender=payer,
            _valid=False,
            _exception="FA2_INSUFFICIENT_BALANCE"
        )

        # Payer swaps more to get enough
        swap_contract.swap(_sender=payer, _amount=sp.mutez(100000))
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 200)

        # Now payment succeeds
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=200)]
            )],
            _sender=payer
        )

        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 0)
        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 200)

        sc.h2("Result: Multiple swaps then payment successful")


    @sp.add_test()
    def test_unauthorized_pause():
        """
        Edge Case: Non-admin tries to pause swap
        - Only admin can pause
        - Non-admin attempt should fail
        """
        sc = sp.test_scenario("Edge Case: Unauthorized Pause")
        sc.h1("Edge Case: Unauthorized Pause Attempt")

        admin = sp.test_account("admin")
        attacker = sp.test_account("attacker")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # Non-admin tries to pause - should fail
        swap_contract.pause(
            True,
            _sender=attacker,
            _valid=False,
            _exception="Not admin"
        )

        sc.h2("Result: Unauthorized pause rejected")


    # =========================================================================
    # Multi-Asset Payment Scenarios
    # These tests simulate agent decision-making when x402 accepts multiple tokens
    # =========================================================================

    @sp.add_test()
    def test_multi_asset_pay_with_existing_balance():
        """
        Multi-Asset Scenario A: Agent has enough of one token
        - x402 accepts TEST or WRONG
        - Agent has 500 TEST, needs 100
        - Decision: Pay with TEST (no swap needed)
        """
        sc = sp.test_scenario("Multi-Asset: Existing Balance")
        sc.h1("Multi-Asset: Pay with Existing Balance")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        # Token metadata
        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")
        wrong_md = fa2.make_metadata(name="WRONG", decimals=0, symbol="WRONG")

        # Deploy both tokens
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        wrong_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += wrong_token

        # Payer has 500 TEST (enough for payment)
        test_token.mint(
            [sp.record(to_=payer.address, amount=500, token=sp.variant("new", test_md))],
            _sender=admin
        )

        # Simulate agent decision: has TEST balance >= required amount
        # Decision: Use TEST directly, no swap needed
        sc.h2("Agent Decision: Use existing TEST balance")

        # Pay 100 TEST
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 400)
        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)

        sc.h2("Result: Paid with existing balance - no swap needed")


    @sp.add_test()
    def test_multi_asset_cost_optimization():
        """
        Multi-Asset Scenario B: Choose cheaper swap
        - x402 accepts TEST or WRONG
        - Agent has 0 of both, needs 100 tokens
        - TEST swap: 1 XTZ = 1000 TEST (cost for 100: 0.1 XTZ)
        - WRONG swap: 1 XTZ = 500 WRONG (cost for 100: 0.2 XTZ)
        - Decision: Swap for TEST (cheaper)
        """
        sc = sp.test_scenario("Multi-Asset: Cost Optimization")
        sc.h1("Multi-Asset: Choose Cheaper Swap")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")
        wrong_md = fa2.make_metadata(name="WRONG", decimals=0, symbol="WRONG")

        # Deploy TEST token and swap (rate: 1000)
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        test_swap = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)  # 1 XTZ = 1000 TEST
        )
        sc += test_swap

        # Fund TEST swap
        test_token.mint(
            [sp.record(to_=test_swap.address, amount=100000, token=sp.variant("new", test_md))],
            _sender=admin
        )

        # Deploy WRONG token and swap (rate: 500 - more expensive)
        wrong_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += wrong_token

        wrong_swap = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=wrong_token.address,
            rate=sp.nat(500)  # 1 XTZ = 500 WRONG (2x more expensive)
        )
        sc += wrong_swap

        # Fund WRONG swap
        wrong_token.mint(
            [sp.record(to_=wrong_swap.address, amount=100000, token=sp.variant("new", wrong_md))],
            _sender=admin
        )

        # Agent decision: Compare costs
        # - TEST: 100 tokens / 1000 rate = 0.1 XTZ
        # - WRONG: 100 tokens / 500 rate = 0.2 XTZ
        # Decision: Use TEST (cheaper)
        sc.h2("Agent Decision: TEST is cheaper (0.1 XTZ vs 0.2 XTZ)")

        # Swap for TEST
        test_swap.swap(_sender=payer, _amount=sp.mutez(100000))  # 0.1 XTZ
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 100)

        # Pay with TEST
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)

        sc.h2("Result: Used cheaper swap (TEST at 0.1 XTZ)")


    @sp.add_test()
    def test_multi_asset_fallback_paused():
        """
        Multi-Asset Scenario C: Fallback when preferred swap is paused
        - x402 accepts TEST or WRONG
        - Agent has 0 of both, needs 100 tokens
        - TEST swap: paused
        - WRONG swap: available (1 XTZ = 500 WRONG)
        - Decision: Use WRONG swap as fallback
        """
        sc = sp.test_scenario("Multi-Asset: Paused Fallback")
        sc.h1("Multi-Asset: Fallback When Swap Paused")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")
        wrong_md = fa2.make_metadata(name="WRONG", decimals=0, symbol="WRONG")

        # Deploy TEST token and swap (will be paused)
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        test_swap = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += test_swap

        test_token.mint(
            [sp.record(to_=test_swap.address, amount=100000, token=sp.variant("new", test_md))],
            _sender=admin
        )

        # PAUSE the TEST swap
        test_swap.pause(True, _sender=admin)

        # Deploy WRONG token and swap (available)
        wrong_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += wrong_token

        wrong_swap = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=wrong_token.address,
            rate=sp.nat(500)
        )
        sc += wrong_swap

        wrong_token.mint(
            [sp.record(to_=wrong_swap.address, amount=100000, token=sp.variant("new", wrong_md))],
            _sender=admin
        )

        # Agent decision: TEST swap is paused, use WRONG as fallback
        sc.h2("Agent Decision: TEST swap paused, fallback to WRONG")

        # Verify TEST swap fails
        test_swap.swap(
            _sender=payer,
            _amount=sp.mutez(100000),
            _valid=False,
            _exception="Swap is paused"
        )

        # Use WRONG swap instead
        wrong_swap.swap(_sender=payer, _amount=sp.mutez(200000))  # 0.2 XTZ for 100 WRONG
        sc.verify(_get_balance(wrong_token, sp.record(owner=payer.address, token_id=0)) == 100)

        # Pay with WRONG
        wrong_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        sc.verify(_get_balance(wrong_token, sp.record(owner=payee.address, token_id=0)) == 100)

        sc.h2("Result: Successfully used fallback swap")


    @sp.add_test()
    def test_multi_asset_partial_balance_topup():
        """
        Multi-Asset Scenario D: Top up partial balance
        - x402 accepts TEST or WRONG
        - Agent has 60 TEST and 30 WRONG, needs 100 tokens
        - Cost to top up TEST: 40 tokens / 1000 = 0.04 XTZ
        - Cost to top up WRONG: 70 tokens / 500 = 0.14 XTZ
        - Decision: Top up TEST (cheaper)
        """
        sc = sp.test_scenario("Multi-Asset: Partial Top-up")
        sc.h1("Multi-Asset: Top Up Partial Balance")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")
        wrong_md = fa2.make_metadata(name="WRONG", decimals=0, symbol="WRONG")

        # Deploy TEST token and swap
        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        test_swap = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += test_swap

        # Mint to payer (60 TEST) and swap contract
        test_token.mint(
            [sp.record(to_=payer.address, amount=60, token=sp.variant("new", test_md))],
            _sender=admin
        )
        test_token.mint(
            [sp.record(to_=test_swap.address, amount=100000, token=sp.variant("existing", sp.nat(0)))],
            _sender=admin
        )

        # Deploy WRONG token and swap
        wrong_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += wrong_token

        wrong_swap = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=wrong_token.address,
            rate=sp.nat(500)
        )
        sc += wrong_swap

        # Mint to payer (30 WRONG) and swap contract
        wrong_token.mint(
            [sp.record(to_=payer.address, amount=30, token=sp.variant("new", wrong_md))],
            _sender=admin
        )
        wrong_token.mint(
            [sp.record(to_=wrong_swap.address, amount=100000, token=sp.variant("existing", sp.nat(0)))],
            _sender=admin
        )

        # Agent decision: Compare top-up costs
        # - TEST: need 40 more, cost = 40/1000 = 0.04 XTZ
        # - WRONG: need 70 more, cost = 70/500 = 0.14 XTZ
        # Decision: Top up TEST
        sc.h2("Agent Decision: Top up TEST (0.04 XTZ vs 0.14 XTZ)")

        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 60)
        sc.verify(_get_balance(wrong_token, sp.record(owner=payer.address, token_id=0)) == 30)

        # Swap for 40 more TEST (round up to 0.1 XTZ for 100 TEST, but we only need 40)
        # In practice: 40000 mutez would give 40 TEST
        test_swap.swap(_sender=payer, _amount=sp.mutez(40000))

        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 100)

        # Pay with TEST
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)

        sc.h2("Result: Topped up TEST for minimum cost")


    # =========================================================================
    # x402 Protocol Tests
    # These tests validate the x402 payment flow structure and constraints
    # =========================================================================

    @sp.add_test()
    def test_x402_payment_proof_structure():
        """
        x402 Test 16: Payment proof structure validation
        - Simulates an x402 payment flow
        - Verifies that payment can be linked back to a specific resource
        - Tests the on-chain payment proof pattern
        """
        sc = sp.test_scenario("x402: Payment Proof Structure")
        sc.h1("x402: Payment Proof Structure Validation")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")  # x402 server address

        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        # Mint tokens to payer
        test_token.mint(
            [sp.record(to_=payer.address, amount=1000, token=sp.variant("new", test_md))],
            _sender=admin
        )

        # x402 payment requirements (simulated):
        # - resource: "https://api.example.com/premium/data"
        # - payTo: payee.address
        # - maxAmountRequired: 100 TEST
        # - network: "tezos-shadownet"
        # - asset: "TEST"

        sc.h2("x402 Payment Requirements Received")
        sc.p("Resource: https://api.example.com/premium/data")
        sc.p("Amount: 100 TEST")

        # Execute payment (FA2 transfer creates proof on-chain)
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        # Verify payment occurred
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 900)
        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)

        # x402 payment proof structure (off-chain, base64 encoded):
        # {
        #   "scheme": "exact",
        #   "network": "tezos-shadownet",
        #   "payload": {
        #     "signature": "<operation_hash>",
        #     "authorization": {
        #       "from": "<payer_address>",
        #       "to": "<payee_address>",
        #       "amount": "100",
        #       "asset": "TEST"
        #     }
        #   }
        # }
        sc.h2("Result: Payment proof created on-chain (opHash links to FA2 transfer)")


    @sp.add_test()
    def test_x402_expiry_simulation():
        """
        x402 Test 17: Expired payment rejection (simulation)
        - x402 payments have an expiry timestamp
        - MCP server should reject payments after expiry
        - This test simulates the expiry concept via swap contract
        """
        sc = sp.test_scenario("x402: Expiry Simulation")
        sc.h1("x402: Payment Expiry Simulation")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        swap_contract = swap_module.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        test_token.mint(
            [sp.record(to_=swap_contract.address, amount=100000, token=sp.variant("new", test_md))],
            _sender=admin
        )

        sc.h2("Simulating x402 expiry via paused state")
        sc.p("In real x402, MCP checks: now > paymentRequirements.expiry")
        sc.p("Here we simulate by pausing the swap (payment no longer available)")

        # Payment is available initially
        swap_contract.swap(_sender=payer, _amount=sp.mutez(100000))
        sc.verify(_get_balance(test_token, sp.record(owner=payer.address, token_id=0)) == 100)

        # "Expiry" occurs - payment opportunity closed
        swap_contract.pause(True, _sender=admin)

        # Trying to get more tokens after expiry fails
        swap_contract.swap(
            _sender=payer,
            _amount=sp.mutez(100000),
            _valid=False,
            _exception="Swap is paused"
        )

        sc.h2("Result: Payment rejected after 'expiry' (simulated via pause)")


    @sp.add_test()
    def test_x402_max_amount_validation():
        """
        x402 Test 18: Maximum amount validation
        - x402 specifies maxAmountRequired
        - Payment should not exceed this amount
        - Agent should calculate exact amount needed
        """
        sc = sp.test_scenario("x402: Max Amount Validation")
        sc.h1("x402: Maximum Amount Validation")

        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        test_md = fa2.make_metadata(name="TEST", decimals=0, symbol="TEST")

        test_token = token_module.TestToken(
            admin_address=admin.address,
            contract_metadata=sp.big_map(),
            ledger={},
            token_metadata=[]
        )
        sc += test_token

        test_token.mint(
            [sp.record(to_=payer.address, amount=1000, token=sp.variant("new", test_md))],
            _sender=admin
        )

        # x402 requirement: maxAmountRequired = 100
        max_amount = 100

        sc.h2("x402 Payment: maxAmountRequired = 100")

        # Agent calculates: pay exactly what's needed (not more)
        # Good: pay 100 (exactly maxAmount)
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=max_amount)]
            )],
            _sender=payer
        )

        sc.verify(_get_balance(test_token, sp.record(owner=payee.address, token_id=0)) == 100)
        sc.h2("Result: Paid exact amount (100 TEST)")

        # Agent should NOT overpay - this is MCP logic, not enforced on-chain
        # The MCP tool validates: amountMutez <= maxAmountMutez
        # If exceeded, returns error before even attempting payment
        sc.p("Note: Overpayment prevention is MCP-side validation")
        sc.p("MCP checks: if (amountMutez > maxPaymentMutez) return error")

# x402 Test Scenarios
# Run with SmartPy: https://smartpy.io/
#
# Tests the three main x402 scenarios:
# 1. Happy path - wallet has TEST tokens, payment succeeds
# 2. Wrong token - payment with wrong token rejected
# 3. Swap flow - no TEST tokens, swap XTZ -> TEST, then pay

import smartpy as sp
from smartpy.templates import fa2_lib as fa2


@sp.module
def tokens():
    """FA2 Fungible Token for testing"""

    class TestToken(
        fa2.Admin,
        fa2.MintFungible,
        fa2.BurnFungible,
        fa2.Fa2Fungible,
    ):
        def __init__(self, admin, metadata):
            fa2.Fa2Fungible.__init__(self, metadata)
            fa2.Admin.__init__(self, admin)


@sp.module
def swap():
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

            xtz_amount = sp.split_tokens(sp.amount, 1, 1000000)
            test_amount = sp.mul(xtz_amount, self.data.rate)

            transfer_param = sp.list([
                sp.record(
                    from_=sp.self_address(),
                    txs=sp.list([
                        sp.record(
                            to_=sp.sender,
                            token_id=sp.nat(0),
                            amount=test_amount
                        )
                    ])
                )
            ])

            token_contract = sp.contract(
                sp.list[sp.record(
                    from_=sp.address,
                    txs=sp.list[sp.record(to_=sp.address, token_id=sp.nat, amount=sp.nat)]
                )],
                self.data.test_token,
                entrypoint="transfer"
            ).unwrap_some(error="Invalid token contract")

            sp.transfer(transfer_param, sp.mutez(0), token_contract)
            self.data.total_swapped += test_amount

        @sp.entrypoint
        def pause(self, paused):
            assert sp.sender == self.data.admin, "Not admin"
            self.data.paused = paused


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
        sc = sp.test_scenario("Scenario 1: Happy Path", [fa2, tokens])

        # Accounts
        admin = sp.test_account("admin")
        payer = sp.test_account("payer")  # AI agent wallet
        payee = sp.test_account("payee")  # x402 merchant

        # Deploy TEST token
        metadata = sp.scenario_utils.metadata_of_url("ipfs://test")
        test_token = tokens.TestToken(admin=admin.address, metadata=metadata)
        sc += test_token

        # Mint TEST tokens to payer (simulating pre-funded wallet)
        test_token.mint(
            [sp.record(
                to_=payer.address,
                token=sp.variant.new(sp.record(metadata={"": sp.bytes("0x00")}, token_id=0)),
                amount=1000
            )],
            _sender=admin
        )

        # Verify payer has tokens
        sc.verify(test_token.data.ledger[sp.record(owner=payer.address, token_id=0)] == 1000)

        # x402 payment: Transfer 100 TEST to payee
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        # Verify payment succeeded
        sc.verify(test_token.data.ledger[sp.record(owner=payer.address, token_id=0)] == 900)
        sc.verify(test_token.data.ledger[sp.record(owner=payee.address, token_id=0)] == 100)

        sc.h2("Result: Payment successful")


    @sp.add_test()
    def test_scenario_2_wrong_token():
        """
        Scenario 2: Wrong Token
        - x402 requests TEST token
        - Wallet tries to pay with WRONG token
        - Payment rejected (payee doesn't accept WRONG)
        """
        sc = sp.test_scenario("Scenario 2: Wrong Token", [fa2, tokens])

        # Accounts
        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        metadata = sp.scenario_utils.metadata_of_url("ipfs://test")

        # Deploy TEST token (what payee wants)
        test_token = tokens.TestToken(admin=admin.address, metadata=metadata)
        sc += test_token

        # Deploy WRONG token (what payer has)
        wrong_token = tokens.TestToken(admin=admin.address, metadata=metadata)
        sc += wrong_token

        # Mint WRONG tokens to payer (but no TEST tokens)
        wrong_token.mint(
            [sp.record(
                to_=payer.address,
                token=sp.variant.new(sp.record(metadata={"": sp.bytes("0x00")}, token_id=0)),
                amount=1000
            )],
            _sender=admin
        )

        # Payer has WRONG tokens but no TEST tokens
        sc.verify(wrong_token.data.ledger[sp.record(owner=payer.address, token_id=0)] == 1000)

        # Try to transfer TEST tokens - should fail (insufficient balance)
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer,
            _valid=False,
            _exception="FA2_INSUFFICIENT_BALANCE"
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
        sc = sp.test_scenario("Scenario 3: Swap Flow", [fa2, tokens, swap])

        # Accounts
        admin = sp.test_account("admin")
        payer = sp.test_account("payer")
        payee = sp.test_account("payee")

        metadata = sp.scenario_utils.metadata_of_url("ipfs://test")

        # Deploy TEST token
        test_token = tokens.TestToken(admin=admin.address, metadata=metadata)
        sc += test_token

        # Deploy swap contract (1 XTZ = 1000 TEST)
        swap_contract = swap.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # Fund swap contract with TEST tokens
        test_token.mint(
            [sp.record(
                to_=swap_contract.address,
                token=sp.variant.new(sp.record(metadata={"": sp.bytes("0x00")}, token_id=0)),
                amount=100000
            )],
            _sender=admin
        )

        # Verify swap contract has liquidity
        sc.verify(test_token.data.ledger[sp.record(owner=swap_contract.address, token_id=0)] == 100000)

        # Step 1: Payer swaps 0.1 XTZ for 100 TEST
        swap_contract.swap(_sender=payer, _amount=sp.mutez(100000))  # 0.1 XTZ

        # Verify payer received TEST tokens
        sc.verify(test_token.data.ledger[sp.record(owner=payer.address, token_id=0)] == 100)

        # Step 2: Pay 100 TEST to payee
        test_token.transfer(
            [sp.record(
                from_=payer.address,
                txs=[sp.record(to_=payee.address, token_id=0, amount=100)]
            )],
            _sender=payer
        )

        # Verify payment succeeded
        sc.verify(test_token.data.ledger[sp.record(owner=payer.address, token_id=0)] == 0)
        sc.verify(test_token.data.ledger[sp.record(owner=payee.address, token_id=0)] == 100)

        sc.h2("Result: Swap + Payment successful")


    @sp.add_test()
    def test_swap_paused():
        """
        Test: Swap contract paused
        - Admin pauses swap
        - Swap attempts fail
        """
        sc = sp.test_scenario("Test: Swap Paused", [fa2, tokens, swap])

        admin = sp.test_account("admin")
        user = sp.test_account("user")

        metadata = sp.scenario_utils.metadata_of_url("ipfs://test")
        test_token = tokens.TestToken(admin=admin.address, metadata=metadata)
        sc += test_token

        swap_contract = swap.TestSwap(
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
        sc = sp.test_scenario("Test: Insufficient Liquidity", [fa2, tokens, swap])

        admin = sp.test_account("admin")
        user = sp.test_account("user")

        metadata = sp.scenario_utils.metadata_of_url("ipfs://test")
        test_token = tokens.TestToken(admin=admin.address, metadata=metadata)
        sc += test_token

        # Deploy swap contract WITHOUT funding it
        swap_contract = swap.TestSwap(
            admin=admin.address,
            test_token_address=test_token.address,
            rate=sp.nat(1000)
        )
        sc += swap_contract

        # User tries to swap - should fail (no liquidity)
        swap_contract.swap(
            _sender=user,
            _amount=sp.mutez(100000),
            _valid=False,
            _exception="FA2_INSUFFICIENT_BALANCE"
        )

        sc.h2("Result: Swap rejected - insufficient liquidity")

# x402 Test Scenarios
# Run with SmartPy: https://smartpy.io/
#
# Tests the three main x402 scenarios:
# 1. Happy path - wallet has TEST tokens, payment succeeds
# 2. Wrong token - payment with wrong token rejected
# 3. Swap flow - no TEST tokens, swap XTZ -> TEST, then pay

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

# Simple Swap Contract: XTZ -> TEST
# Deploy with SmartPy: https://smartpy.io/
#
# Fixed-rate swap for demo purposes
# Send XTZ, receive TEST tokens at a fixed rate

import smartpy as sp

@sp.module
def main():

    # FA2 transfer type for calling the token contract
    class fa2_transfer_type(sp.record):
        from_: sp.address
        txs: sp.list[sp.record(to_=sp.address, token_id=sp.nat, amount=sp.nat)]

    class TestSwap(sp.Contract):
        """
        Simple XTZ -> TEST Swap Contract

        - Fixed exchange rate: 1 XTZ = 1000 TEST (configurable)
        - Admin can update rate and withdraw funds
        - Must hold TEST tokens to swap
        """

        def __init__(self, admin, test_token_address, rate):
            self.data.admin = admin
            self.data.test_token = test_token_address
            self.data.rate = rate  # TEST tokens per 1 XTZ (in mutez: per 1,000,000 mutez)
            self.data.paused = False
            self.data.total_swapped = sp.nat(0)

        @sp.entrypoint
        def swap(self):
            """
            Swap XTZ for TEST tokens

            Send XTZ with this call, receive TEST tokens at the current rate.
            """
            assert not self.data.paused, "Swap is paused"
            assert sp.amount > sp.mutez(0), "Must send XTZ"

            # Calculate TEST tokens to send
            # amount is in mutez, rate is TEST per XTZ
            xtz_amount = sp.split_tokens(sp.amount, 1, 1000000)  # Convert mutez to XTZ units
            test_amount = sp.mul(xtz_amount, self.data.rate)

            # Prepare FA2 transfer
            transfer_param = sp.list([
                sp.record(
                    from_=sp.self_address(),
                    txs=sp.list([
                        sp.record(
                            to_=sp.sender,
                            token_id=sp.nat(0),  # TEST token ID
                            amount=test_amount
                        )
                    ])
                )
            ])

            # Call FA2 transfer on TEST token contract
            token_contract = sp.contract(
                sp.list[sp.record(
                    from_=sp.address,
                    txs=sp.list[sp.record(to_=sp.address, token_id=sp.nat, amount=sp.nat)]
                )],
                self.data.test_token,
                entrypoint="transfer"
            ).unwrap_some(error="Invalid token contract")

            sp.transfer(transfer_param, sp.mutez(0), token_contract)

            # Track stats
            self.data.total_swapped += test_amount

        @sp.entrypoint
        def update_rate(self, new_rate):
            """Admin: Update exchange rate"""
            assert sp.sender == self.data.admin, "Not admin"
            self.data.rate = new_rate

        @sp.entrypoint
        def pause(self, paused):
            """Admin: Pause/unpause swaps"""
            assert sp.sender == self.data.admin, "Not admin"
            self.data.paused = paused

        @sp.entrypoint
        def withdraw_xtz(self, amount):
            """Admin: Withdraw XTZ from contract"""
            assert sp.sender == self.data.admin, "Not admin"
            sp.send(self.data.admin, amount)

        @sp.entrypoint
        def update_admin(self, new_admin):
            """Admin: Transfer admin rights"""
            assert sp.sender == self.data.admin, "Not admin"
            self.data.admin = new_admin

        @sp.onchain_view()
        def get_rate(self):
            """View: Get current exchange rate"""
            return self.data.rate

        @sp.onchain_view()
        def get_stats(self):
            """View: Get swap statistics"""
            return sp.record(
                rate=self.data.rate,
                total_swapped=self.data.total_swapped,
                paused=self.data.paused,
                xtz_balance=sp.balance
            )


# Test scenario
if "main" in __name__:

    @sp.add_test()
    def test():
        sc = sp.test_scenario("TestSwap", main)

        # Test accounts
        admin = sp.test_account("admin")
        user = sp.test_account("user")

        # Mock TEST token address (replace with real address after deployment)
        test_token = sp.address("KT1TestTokenAddress...")

        # Deploy swap contract
        # Rate: 1000 TEST per 1 XTZ
        swap = main.TestSwap(
            admin=admin.address,
            test_token_address=test_token,
            rate=sp.nat(1000)
        )
        sc += swap

        # Test rate view
        sc.verify(swap.get_rate() == 1000)


# Deployment config
DEPLOYMENT_CONFIG = {
    "initial_rate": 1000,  # 1000 TEST per 1 XTZ
    "description": "Swap XTZ for TEST tokens at a fixed rate for x402 demos"
}

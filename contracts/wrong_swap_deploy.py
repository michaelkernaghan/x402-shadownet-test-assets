# WRONG_SWAP deployment script
# Deploy a swap contract for XTZ -> WRONG tokens
# Rate: 1 XTZ = 500 WRONG (more expensive than TEST swap which is 1 XTZ = 1000 TEST)
# This allows testing agent cost optimization decisions

import smartpy as sp

@sp.module
def wrong_swap_module():
    """Swap contract for XTZ -> WRONG tokens"""

    class WrongSwap(sp.Contract):
        def __init__(self, admin, wrong_token_address, rate):
            self.data.admin = admin
            self.data.wrong_token = wrong_token_address
            self.data.rate = rate  # 500 = 1 XTZ gives 500 WRONG
            self.data.paused = False
            self.data.total_swapped = sp.nat(0)

        @sp.entrypoint
        def swap(self):
            assert not self.data.paused, "Swap is paused"
            assert sp.amount > sp.mutez(0), "Must send XTZ"

            # Convert mutez to nat (1 XTZ = 1,000,000 mutez)
            # For rate of 500: 100,000 mutez (0.1 XTZ) * 500 / 1,000,000 = 50 WRONG
            xtz_in_mutez = sp.fst(sp.ediv(sp.amount, sp.mutez(1)).unwrap_some())
            wrong_amount = sp.fst(sp.ediv(xtz_in_mutez * self.data.rate, sp.nat(1000000)).unwrap_some())

            transfer_param = [
                sp.record(
                    from_=sp.self_address,
                    txs=[
                        sp.record(
                            to_=sp.sender,
                            token_id=sp.nat(0),
                            amount=wrong_amount
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
                self.data.wrong_token,
                entrypoint="transfer"
            ).unwrap_some(error="Invalid token contract")

            sp.transfer(transfer_param, sp.mutez(0), token_contract)
            self.data.total_swapped += wrong_amount

        @sp.entrypoint
        def pause(self, paused):
            assert sp.sender == self.data.admin, "Not admin"
            self.data.paused = paused


# Compilation for deployment
if "main" in __name__:
    # Configuration for Shadownet deployment
    ADMIN_ADDRESS = sp.address("tz1hUXcGHiNsR3TRyYTeAaXtDqMCfLUExaqn")
    WRONG_TOKEN_ADDRESS = sp.address("KT1Sr4yixp2Z9q4xDGz2UaV4zdjhjL1eTpkj")
    RATE = sp.nat(500)  # 1 XTZ = 500 WRONG (more expensive than TEST)

    @sp.add_test()
    def test_wrong_swap():
        """Test the WRONG swap contract"""
        sc = sp.test_scenario("WRONG Swap Test")
        sc.h1("WRONG Swap Contract Test")

        # Deploy with test addresses for scenario
        admin = sp.test_account("admin")
        wrong_token = sp.test_account("wrong_token")  # Placeholder

        swap = wrong_swap_module.WrongSwap(
            admin=admin.address,
            wrong_token_address=wrong_token.address,
            rate=sp.nat(500)
        )
        sc += swap

        sc.h2("Contract deployed successfully")

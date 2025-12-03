# FA2 Test Token Contract for Shadownet
# Deploy with SmartPy: https://smartpy.io/
#
# This creates a simple FA2 token called "TEST" that can be used for x402 demos

import smartpy as sp

# FA2 standard interface
from smartpy.templates import fa2_lib as fa2

# Main token contract
@sp.module
def main():

    class TestToken(
        fa2.Admin,
        fa2.MintNft,
        fa2.BurnNft,
        fa2.Fa2Nft,
    ):
        """
        TEST Token - FA2 Fungible Token for x402 demos on Shadownet

        Features:
        - Admin can mint/burn tokens
        - Standard FA2 transfers
        - Metadata support
        """

        def __init__(self, admin, metadata):
            fa2.Fa2Nft.__init__(self, metadata)
            fa2.Admin.__init__(self, admin)


# For a simpler fungible token approach, use this:
@sp.module
def fungible():

    class TestTokenFungible(
        fa2.Admin,
        fa2.MintFungible,
        fa2.BurnFungible,
        fa2.Fa2Fungible,
    ):
        """
        TEST Token - FA2 Fungible Token

        Token ID 0 = TEST token
        """

        def __init__(self, admin, metadata):
            fa2.Fa2Fungible.__init__(self, metadata)
            fa2.Admin.__init__(self, admin)


# Test/deployment script
if "main" in __name__:

    @sp.add_test()
    def test():
        # Test scenario
        sc = sp.test_scenario("TestToken", [fa2, fungible])

        # Admin address (replace with your address)
        admin = sp.test_account("admin")

        # Token metadata
        metadata = sp.scenario_utils.metadata_of_url(
            "ipfs://QmTest..."  # Replace with actual metadata URI
        )

        # Deploy fungible token
        token = fungible.TestTokenFungible(
            admin=admin.address,
            metadata=metadata
        )
        sc += token

        # Mint some TEST tokens to admin
        token.mint(
            [
                sp.record(
                    to_=admin.address,
                    token=sp.variant.new(
                        sp.record(
                            metadata={"": sp.bytes("0x00")},
                            token_id=0
                        )
                    ),
                    amount=1000000  # 1 million TEST tokens
                )
            ],
            _sender=admin
        )

        # Verify balance
        sc.verify(token.data.ledger[sp.record(owner=admin.address, token_id=0)] == 1000000)


# Deployment metadata (TZIP-16)
TOKEN_METADATA = {
    "name": "Test Token",
    "symbol": "TEST",
    "decimals": "6",
    "description": "Test token for x402 payment demos on Shadownet",
    "interfaces": ["TZIP-012", "TZIP-016"],
}

from web3 import Web3
from decimal import Decimal
import json

class PancakePriceFetcher:
    def __init__(self, rpc_url, token, stable, v2_pool, v3_pool, v3_abi_path):
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))

        self.token = Web3.to_checksum_address(token)
        self.stable = Web3.to_checksum_address(stable)
        self.v2_pool = Web3.to_checksum_address(v2_pool)
        self.v3_pool = Web3.to_checksum_address(v3_pool)

        # Load ABIs
        self.erc20_abi = [{
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        }]

        self.pair_abi = [
            {
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
                    {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
                    {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token0",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token1",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]

        with open(v3_abi_path, "r") as f:
            self.v3_pool_abi = json.load(f)

    # -----------------------------
    # Utility
    # -----------------------------

    def get_decimals(self, token_addr):
        return self.web3.eth.contract(address=token_addr, abi=self.erc20_abi).functions.decimals().call()

    # -----------------------------
    # V2 price + liquidity
    # -----------------------------

    def get_price_v2(self):
        pair = self.web3.eth.contract(address=self.v2_pool, abi=self.pair_abi)

        r0, r1, _ = pair.functions.getReserves().call()
        t0 = pair.functions.token0().call()
        t1 = pair.functions.token1().call()

        d0 = self.get_decimals(t0)
        d1 = self.get_decimals(t1)

        if t0.lower() == self.token.lower():
            price = (r1 / 10**d1) / (r0 / 10**d0)
        else:
            price = (r0 / 10**d0) / (r1 / 10**d1)

        # Liquidity = smaller side of the pool
        liq = min(r0 / 10**d0, r1 / 10**d1)

        return price, liq

    # -----------------------------
    # V3 price + liquidity
    # -----------------------------

    def get_price_v3(self):
        pool = self.web3.eth.contract(address=self.v3_pool, abi=self.v3_pool_abi)

        slot0 = pool.functions.slot0().call()
        sqrtPriceX96 = slot0[0]

        t0 = pool.functions.token0().call()
        t1 = pool.functions.token1().call()

        d0 = self.get_decimals(t0)
        d1 = self.get_decimals(t1)

        price = (Decimal(sqrtPriceX96) / (2**96)) ** 2
        price = price * (10 ** (d0 - d1))

        if t0.lower() == self.token.lower():
            price = float(price)
        else:
            price = float(1 / price)

        # V3 liquidity from contract
        liquidity = pool.functions.liquidity().call()

        return price, liquidity

    # -----------------------------
    # Weighted price
    # -----------------------------

    def get_weighted_price(self):
        v2_price, v2_liq = self.get_price_v2()
        v3_price, v3_liq = self.get_price_v3()

        total_liq = v2_liq + v3_liq
        if total_liq == 0:
            return None

        weighted = (v2_price * v2_liq + v3_price * v3_liq) / total_liq
        return weighted

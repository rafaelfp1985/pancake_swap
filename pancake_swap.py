from web3 import Web3
import requests
import time
import json

# Setup Web3 and wallet
web3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
wallet_address = 'YOUR_WALLET_ADDRESS'
private_key = 'YOUR_PRIVATE_KEY'

# PancakeSwap Router v2
router_address = Web3.to_checksum_address('0x10ED43C718714eb63d5aA57B78B54704E256024E')
#router_abi = [...]  # Insert PancakeSwap Router ABI here
# Load ABI from abi.json
with open('abi.json', 'r') as abi_file:
    router_abi = json.load(abi_file)

# Token addresses
usdt_address = Web3.to_checksum_address('0x55d398326f99059fF775485246999027B3197955')  # USDT
usda_address = Web3.to_checksum_address('0x17EAfd08994305D8AcE37EfB82F1523177eC70EE')  # Replace with actual USDA token address

# Swap parameters
amount_in = web3.to_wei(100, 'ether')  # 100 USDT
deadline = int(time.time()) + 60 * 20  # 20 minutes from now

# Contract instance
router_contract = web3.eth.contract(address=router_address, abi=router_abi)

# Function to get USDA price
def get_usda_price():
    url = 'https://api.pancakeswap.info/api/v2/tokens/{usda_address}'
    response = requests.get(url)
    data = response.json()
    return float(data['data']['price'])

# Function to execute swap
def swap_tokens():
    nonce = web3.eth.get_transaction_count(wallet_address)
    tx = router_contract.functions.swapExactTokensForTokens(
        amount_in,
        0,
        [usdt_address, usda_address],
        wallet_address,
        deadline
    ).build_transaction({
        'from': wallet_address,
        'gas': 200000,
        'nonce': nonce
    })

    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f'Swap executed. Tx hash: {web3.to_hex(tx_hash)}')

# Monitor price and swap
while True:
    try:
        price = get_usda_price()
        print(f'Current USDA price: {price}')
        if price < 0.96:
            print('Price condition met. Executing swap...')
            #swap_tokens()
            break
        else:
            print('Price too high. Waiting...')
        time.sleep(60)
    except Exception as e:
        print(f'Error: {e}')
        time.sleep(60)

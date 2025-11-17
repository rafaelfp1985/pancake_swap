from web3 import Web3
from web3.middleware import geth_poa_middleware
from google.cloud import secretmanager

import requests
import time
import datetime
import json
import sys

wallet_address = ""
private_key = ""

def access_secret_payload(secret_id, version):
    """Accesses the payload of the secret and returns it as a string."""
    
    # Your project ID and the name of the secret
    PROJECT_ID = "478915354588"
    SECRET_ID = secret_id #"CoinmarketCap_APIKey"

    # The full resource name of the secret version.
    # Using 'latest' is okay for simplicity here, but use a specific version (e.g., :2) in production.
    SECRET_VERSION_NAME = f"projects/{PROJECT_ID}/secrets/{SECRET_ID}/versions/{version}"

    # 1. Instantiate the Secret Manager client.
    # The client automatically handles authentication using the Service Account
    # attached to the Cloud Run instance, VM, or local environment.
    client = secretmanager.SecretManagerServiceClient()

    try:
        # 2. Call the API to get the secret version.
        response = client.access_secret_version(name=SECRET_VERSION_NAME)
        
        # 3. Decode the secret payload (which is returned as bytes).
        secret_payload = response.payload.data.decode("UTF-8")
        
        return secret_payload

    except Exception as e:
        print(f"Error accessing secret: {e}")
        # In a real application, you might raise an exception or handle this failure
        return None

#Get token balance
def get_token_balance(web3, token_address: str, abi: list, wallet_address: str) -> float:
    # Create contract object
    token_address = web3.to_checksum_address(token_address)
    wallet_address = web3.to_checksum_address(wallet_address)
    contract = web3.eth.contract(address=token_address, abi=abi)

    # Get raw balance and decimals
    balance = contract.functions.balanceOf(wallet_address).call()
    decimals = contract.functions.decimals().call()

    # Convert to human-readable
    readable_balance = balance / (10 ** decimals)
    return readable_balance
    
# Price fetcher
def get_usda_price():
    print("Looking for the USDA price...")
    #Pancakeswap API doesn't work. Let's move to Coinmarketcap API
    #url = f'https://api.pancakeswap.info/api/v2/tokens/{usda_address}'
    #st.write(f'Calling URL: {url}')
    #response = requests.get(url)
    #data = response.json()
    #return float(data['data']['price'])
    token_price = get_latest_price_by_id(37721)
    return token_price

# Swap function
def swap_tokens(web3, wallet_address, private_key, amount_in, amount_out_min, router_contract, usdt_address, usda_address):
    print("Starting wallet...")
    checksum_address = Web3.to_checksum_address(wallet_address)
    #nonce = web3.eth.get_transaction_count(wallet_address)
    nonce = web3.eth.get_transaction_count(checksum_address)
    print("Start swapping...")
    deadline = int(time.time()) + 60 * 20
    tx = router_contract.functions.swapExactTokensForTokens(
        amount_in,
        amount_out_min,
        [usdt_address, usda_address],
        checksum_address,
        deadline
    ).build_transaction({
        'from': checksum_address,
        'gas': 200000,
        'nonce': nonce
    })

    print("Getting TX...")
    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    return web3.to_hex(tx_hash)

def get_latest_price_by_id(api_id):
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    api_key = access_secret_payload("CoinmarketCap_APIKey") #st.secrets["COINMARKET_API_KEY"]# Replace with your actual API key

    headers = {
        "X-CMC_PRO_API_KEY": api_key,
        "Accept": "application/json"
    }

    params = {
        "id": api_id
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()  # Raises an error for bad responses

    data = response.json()
    #Show JSON content if in debug mode
    #st.json(data)
    token_price = data["data"][str(api_id)]["quote"]["USD"]["price"]

    return token_price

def main_loop():
    
    wallet_address = access_secret_payload("wallet_address", "1") #st.secrets['wallet_address']
    private_key = access_secret_payload("wallet_private_key","1") #st.secrets['private_key']

    # Title
    print(f"🦊 PancakeSwap Monitor - {wallet_address}")

    # Setup Web3
    print("Starting Web3 Component...")
    print("🕒 Timestamp: ", datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    web3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    #st.write(wallet_address)
    #st.write(private_key)

    # Load ABI
    print("Loading ABI file...")
    with open('abi.json', 'r') as abi_file:
        router_abi = json.load(abi_file)
    token_abi = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
    ]


    # Contract setup
    print("Setting up contracts...")
    router_address = Web3.to_checksum_address('0x10ED43C718714eb63d5aA57B78B54704E256024E')
    router_contract = web3.eth.contract(address=router_address, abi=router_abi)

    # Tokens
    print("Setting up Tokens...")
    usdt_address = Web3.to_checksum_address('0x55d398326f99059fF775485246999027B3197955')
    usda_address = Web3.to_checksum_address('0x17EAfd08994305D8AcE37EfB82F1523177eC70EE')

    # Parameters
    print("Setting up parameters...")
    amount_in = 100 * 10**18            #web3.to_wei(100, 'ether')
    slippage_tolerance = 0.005          # 0.5%
    amount_out_min = int(amount_in * (1 - slippage_tolerance))

    #Checking Tokens balance
    bnb_balance = web3.eth.get_balance(Web3.to_checksum_address(wallet_address))
    bnb_balance = web3.from_wei(bnb_balance, 'ether')
    print("BNB balance", f"{bnb_balance:.6f}")
    usdt_balance = get_token_balance(web3, usdt_address, token_abi, wallet_address)
    print("USDT balance", f"${usdt_balance:.4f}")
    usda_balance = get_token_balance(web3, usda_address, token_abi, wallet_address)
    print("USDA balance", f"${usda_balance:.4f}")

    # UI
    try:
        while True:
            print("Request USDA price...")
            price = get_usda_price()
            print("Current USDA Price", f"${price:.4f}")

            #Check if minimum price is reached. If yes, buy it
            if price < 1.96:
                print("✅ Price condition met! Ready to swap.")
                tx_hash = swap_tokens(web3=web3, wallet_address=wallet_address, private_key=private_key, amount_in=amount_in, amount_out_min=amount_out_min, router_contract=router_contract,usdt_address=usdt_address,usda_address=usda_address)
                print(f"Swap executed. Tx hash: `{tx_hash}`")
            else:
                print("⏳ Price too high. Waiting for drop below $0.96.")
            
            # Sleep for a period
            time.sleep(300) # Sleeps for 300 seconds (5 minute)

    except Exception as e:
        print(f"Error: {e}")
    
if __name__ == "__main__":
    try:
        main_loop()

    except KeyboardInterrupt:
        print("Worker shutting down...")
        sys.exit(0)
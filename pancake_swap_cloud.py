from re import A
from web3 import Web3
from web3.middleware import geth_poa_middleware
from google.cloud import secretmanager

import requests
import time
import datetime
import json
import sys
import os

wallet_address = ""
private_key = ""
price_oracle_api_key = ""

def access_secret_payload(secret_id, version):
    """Accesses the payload of the secret and returns it as a string."""
    
    # Your project ID and the name of the secret
    PROJECT_ID = "478915354588"
    SECRET_ID = secret_id 

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
    #print("Looking for the USDA price...")
    #Use Coinmarketcap API
    #token_price = coinmarketcap_get_latest_price_by_id(37721)
    #Use Bitquery API. The prices here are closer to the ones on Pancakewap
    #token_price = bitquery_get_latest_price_by_USDT()
    #User Coingecko API
    token_price = coingecko_get_latest_price_by_address("bsc","0x17eafd08994305d8ace37efb82f1523177ec70ee")

    return token_price

# Approve token
def check_and_approve_token_allowance(web3, wallet_address, private_key, amount_allowed, router_address, token_contract):
    #print("Approving token for swap...")
    checksum_address = Web3.to_checksum_address(wallet_address)

    target_allowance = Web3.to_wei(amount_allowed, 'ether') #(10 ** decimals)
    current_allowance = token_contract.functions.allowance(checksum_address, router_address).call()

    if current_allowance < target_allowance:
        print("Allowance too low, sending approve transaction...")
        nonce = web3.eth.get_transaction_count(checksum_address, 'pending')
        txn = token_contract.functions.approve(
            router_address,
            target_allowance
        ).build_transaction({
            'from': checksum_address,
            'nonce': nonce,
            'gas': 100000,
            'gasPrice': web3.to_wei(5, 'gwei')
        })

        print("Getting TX for approval...")
        signed_txn = web3.eth.account.sign_transaction(txn, private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        print("Token approval TX:", tx_hash)
    else:
        tx_hash = 0
        print(f"Already approved for at least {amount_allowed}. Current allowance: {Web3.from_wei(current_allowance,'ether'):.2f}")

    return tx_hash

# Swap function
def swap_tokens(web3, wallet_address, private_key, amount_in, amount_out_min, router_contract, source_token_address, destination_token_address):
    
    checksum_address = Web3.to_checksum_address(wallet_address)
    #nonce = web3.eth.get_transaction_count(wallet_address)
    nonce = web3.eth.get_transaction_count(checksum_address)
    print("Start swapping...")
    
    #Convert from human number to uint256
    uint_amount_in = int( amount_in * 10**18 )
    #Use again the amount_out_min. This should be determined outside this function
    uint_amount_out_min = int( amount_out_min * 10**18 )

    deadline = int(time.time()) + 60 * 20
    #tx = router_contract.functions.swapExactTokensForTokens(
    tx = router_contract.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
        uint_amount_in,
        uint_amount_out_min,
        [source_token_address, destination_token_address],
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

def bitquery_get_latest_price_by_USDT():
    # API endpoint
    url = "https://streaming.bitquery.io/graphql"
    
    # Headers with your access token
    api_key = access_secret_payload("Bitquery_APIKey","1") 
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {api_key}"  # Replace with your actual token
    }
    
    # GraphQL query
    query = """
    query LatestTokenPrice {
      EVM(network: bsc) {
        DEXTradeByTokens(
          orderBy: {descending: Block_Time}
          limit: {count: 1}
          where: {
            Trade: {
              Currency: {SmartContract: {is: "0x17EAfd08994305D8AcE37EfB82F1523177eC70EE"}}
              Side: {Currency: {SmartContract: {is: "0x55d398326f99059ff775485246999027b3197955"}}}
              Price: {gt: 0}
              Dex: {ProtocolName: {in: ["pancake_swap_v3", "pancake_swap_v2"]}}
            }
          }
        ) {
          Block {
            Number
            Time
          }
          Trade {
            Currency {
              Symbol
              Name
              SmartContract
            }
            Price
            PriceInUSD
            Amount
            Side {
              Currency {
                Symbol
                Name
                SmartContract
              }
              Amount
            }
            Dex {
              ProtocolName
              ProtocolFamily
            }
          }
        }
      }
    }
    """
    
    # Create payload
    payload = json.dumps({'query': query})
    
    try:
        # Make the request
        response = requests.post(url, headers=headers, data=payload)
        
        # Check if request was successful
        if response.status_code == 200:
            data = response.json()
            
            # Extract the trade data
            trades = data['data']['EVM']['DEXTradeByTokens']
            
            if trades:
                trade = trades[0]  # Get the latest trade
                
                #print("=== Latest Token Price ===")
                #print(f"Block Number: {trade['Block']['Number']}")
                #print(f"Block Time: {trade['Block']['Time']}")
                #print(f"Token: {trade['Trade']['Currency']['Symbol']} ({trade['Trade']['Currency']['Name']})")
                #print(f"Price in USDT: {trade['Trade']['Price']}")
                #print(f"Price in USD: ${trade['Trade']['PriceInUSD']}")
                #print(f"DEX: {trade['Trade']['Dex']['ProtocolName']}")
                
                result = {
                    'block_number': trade['Block']['Number'],
                    'block_time': trade['Block']['Time'],
                    'token_symbol': trade['Trade']['Currency']['Symbol'],
                    'price_usdt': float(trade['Trade']['Price']),
                    'price_usd': float(trade['Trade']['PriceInUSD']),
                    'dex': trade['Trade']['Dex']['ProtocolName']
                }
                print("Oracle information: ", result) #Log

                usdt_price = float(trade['Trade']['Price'])
                return usdt_price 
            else:
                print("Bitquery - No trades found for this token pair")
                return None
                
        else:
            print(f"Bitquery - Request failed with status code: {response.status_code}")
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"Bitquery - An error occurred: {str(e)}")
        return None

def coinmarketcap_get_latest_price_by_id(api_id):
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

    #Possibility to use global variable. Make easier for testing on different environment.
    if price_oracle_api_key == '':
        api_key = access_secret_payload("CoinmarketCap_APIKey","1") #st.secrets["COINMARKET_API_KEY"]# Replace with your actual API key
    else:
        api_key = price_oracle_api_key

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

def coingecko_get_latest_price_by_address(network, address):

    url = f"https://api.coingecko.com/api/v3/onchain/simple/networks/{network}/token_price/{address}"

    #Possibility to use global variable. Make easier for testing on different environment.
    if price_oracle_api_key == '':
        api_key = access_secret_payload("CoinGecko_APIKey","1") 
    else:
        api_key = price_oracle_api_key

    headers = {"x-cg-demo-api-key": api_key}

    response = requests.get(url, headers=headers)

    data = response.json() # Convert JSON string → Python dict 
    price_str = data["data"]["attributes"]["token_prices"][address] 
    token_price = float(price_str)

    return token_price

def calculate_target_amount(amount_in, target_price, slippage_tolerance):
    
    target_amount = 0
    if target_price >= 0:
        target_amount = ( amount_in / target_price ) * (1 - slippage_tolerance)

    return target_amount

def get_buy_target():
    #Start with hardcoded value
    target_price_buy = 0.9800
    #Check if Environment variable is set
    if "TARGET_PRICE_BUY" in os.environ:
        try:
            env_value = float(os.environ["TARGET_PRICE_BUY"])
            target_price_buy = env_value
            #print(f"Using TARGET_PRICE_BUY from environment: {target_price_buy}")
        except ValueError:
            #print("Invalid TARGET_PRICE_BUY environment variable. Using default value.")
            target_price_buy = target_price_buy
    return target_price_buy

def get_sell_target():
    target_price_sell = 0.9980
    #Check if Environment variable is set
    if "TARGET_PRICE_SELL" in os.environ:
        try:
            env_value = float(os.environ["TARGET_PRICE_SELL"])
            target_price_sell = env_value
            #print(f"Using TARGET_PRICE_BUY from environment: {target_price_buy}")
        except ValueError:
            #print("Invalid TARGET_PRICE_BUY environment variable. Using default value.")
            target_price_sell = target_price_sell
    return target_price_sell

def get_buy_amount():
    buy_amount = 10
    #Check if Environment variable is set
    if "BUY_AMOUNT" in os.environ:
        try:
            env_value = float(os.environ["BUY_AMOUNT"])
            buy_amount = env_value
            #print(f"Using BUY_AMOUNT from environment: {buy_amount}")
        except ValueError:
            #print("Invalid BUY_AMOUNT environment variable. Using default value.")
            buy_amount = buy_amount
    return buy_amount

def main_loop():
    
    #Possibility to use global variable. Make easier for testing on different environments.
    global wallet_address, private_key
    if wallet_address == '':
        wallet_address = access_secret_payload("wallet_address", "2") #st.secrets['wallet_address']
    if private_key == '':
        private_key = access_secret_payload("wallet_private_key","2") #st.secrets['private_key']

    #Version (for control in the Cloud)
    print("Version 1.0.5")

    # Title
    print(f"🦊 PancakeSwap Monitor - {wallet_address} - 🕒 Timestamp: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    # Setup Web3
    #print("Starting Web3 Component...")
    #print("🕒 Timestamp: ", datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    web3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Load ABI
    print("Loading ABI files...")
    with open('pancake_abi.json', 'r') as abi_file:
        router_abi = json.load(abi_file)
    with open('erc20_abi.json', 'r') as abi_file:
        token_abi = json.load(abi_file)

    # Contract setup
    #print("Setting up contracts...")
    router_address = Web3.to_checksum_address('0x10ED43C718714eb63d5aA57B78B54704E256024E') #Pancakeswap router
    router_contract = web3.eth.contract(address=router_address, abi=router_abi)

    # Tokens
    #print("Setting up Tokens...")
    usdt_address = Web3.to_checksum_address('0x55d398326f99059fF775485246999027B3197955')
    usdt_contract = web3.eth.contract(address=usdt_address, abi=token_abi)
    usda_address = Web3.to_checksum_address('0x17EAfd08994305D8AcE37EfB82F1523177eC70EE')
    usda_contract = web3.eth.contract(address=usda_address, abi=token_abi)

    # Parameters
    #print("Setting up parameters...")
    target_price_buy = get_buy_target()
    #print(f"Target buy price: ${target_price_buy:.4f}")
    target_price_sell = get_sell_target()
    #print(f"Target sell price: ${target_price_sell:.4f}")
    #amount_in = 10           #web3.to_wei(100, 'ether')
    amount_in = get_buy_amount()
    slippage_tolerance = 0.005          # 0.5%
    amount_out_min = calculate_target_amount(amount_in, target_price_buy, slippage_tolerance)
    #print(f"Amount to buy: {amount_in:.2f} USDT")
    #print(f"Expected USDA quantity: {amount_out_min:.4f}")
    parameters = {
        "BuyPrice": round(float(target_price_buy), 4), 
        "SellPrice": round(float(target_price_sell), 4),
        "BuyAmount": round(float(amount_in), 2),
        "Slippage": round(float(slippage_tolerance), 4),
        "AmountMininum": round(float(amount_out_min), 4)
    }
    print("Trade parameters:", json.dumps(parameters))

    #Check if token quantity needs to be approved
    amount_allowed = 1000
    print(f"Checking token approval...")
    #print(f"Checking if USDT is approved...")
    check_and_approve_token_allowance(web3, wallet_address, private_key, amount_allowed, router_address, usdt_contract)
    #print(f"Checking if USDA is approved...")
    check_and_approve_token_allowance(web3, wallet_address, private_key, amount_allowed, router_address, usda_contract)

    # UI
    try:
        #while True:
        #Checking Tokens balance
        #print("Checking Wallet balances...")
        bnb_balance = web3.eth.get_balance(Web3.to_checksum_address(wallet_address))
        bnb_balance = web3.from_wei(bnb_balance, 'ether')
        usdt_balance = get_token_balance(web3, usdt_address, token_abi, wallet_address)
        usda_balance = get_token_balance(web3, usda_address, token_abi, wallet_address)
        #print("BNB balance", f"{bnb_balance:.6f}")
        #print("USDT balance", f"${usdt_balance:.4f}")
        #print("USDA balance", f"${usda_balance:.4f}")
        # Merge into dictionary
        balances = {
            "BNB": round(float(bnb_balance), 6),
            "USDT": round(float(usdt_balance), 4),
            "USDA": round(float(usda_balance), 4)
        }
        # Print JSON for logging
        print("Wallet balances: ", json.dumps(balances))

        #print("Request USDA price...")
        usda_price = get_usda_price()
        print("💵 Current USDA Price", f"${usda_price:.4f}")

        #Check if minimum price is reached. If yes, buy it
        #if price < 1.96: #This is only for test
        #Price reach. Spend USDT
        if usda_price < target_price_buy:
            if usdt_balance > amount_in:
                print("🤑 Buying price condition met! Ready to swap!")
                #Provide human readable numbers here. The convertion to uint will happen inside the swap transaction
                #For buying, take the risk and use the amount_out_min as the same as amount_in
                amount_out_min = amount_in
                tx_hash = swap_tokens(web3=web3, wallet_address=wallet_address, private_key=private_key, amount_in=amount_in, amount_out_min=amount_out_min, router_contract=router_contract,source_token_address=usdt_address,destination_token_address=usda_address)
                print(f"Swap executed. Tx hash: `{tx_hash}`")
                # Wait for the transaction receipt
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                # Check status
                if receipt["status"] == 1:
                    print("✅ Transaction succeeded!")
                    #Check the effective price
                    new_usda_balance = get_token_balance(web3, usda_address, token_abi, wallet_address)
                    purchase_amount = new_usda_balance - usda_balance
                    if purchase_amount == 0:
                        effective_price = 0 #Wrong, but gives a hint that something is wrong
                    else:
                        effective_price = amount_in / purchase_amount
                    print(f"Effective USDA buy price: ${effective_price:.4f}")
                    #Difference to target price
                    price_diff = usda_price - effective_price #A positive number indicates a good trade. Negative, a bad one 
                    print(f"Difference to target buy price: ${price_diff:.4f}")
                else:
                    print("❌ Transaction failed.")
            else: #Not enough money
                print("❌ Not enough USDT to buy!")
        else:
            print(f"⏳ Price too high. Waiting for drop below ${target_price_buy:.4f}.")
        
        #If if price to sell is reached
        #Price reach. Spend USDA
        if usda_price > target_price_sell:
            if usda_balance > amount_in:
                #For USDA, the amount_out needs to be adjusted, as it will be less, depending on the price
                #The target price for sell should be enough for this calculation, as we expect at least this price
                amount_out_min = amount_in * target_price_sell
                print("🤑 Selling price condition met! Ready to swap.")
                tx_hash = swap_tokens(web3=web3, wallet_address=wallet_address, private_key=private_key, amount_in=amount_in, amount_out_min=amount_out_min, router_contract=router_contract,source_token_address=usda_address,destination_token_address=usdt_address)
                print(f"Swap executed. Tx hash: `{tx_hash}`")
                # Wait for the transaction receipt
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                # Check status
                if receipt["status"] == 1:
                    print("✅ Transaction succeeded!")
                    #Check the effective price
                    new_usdt_balance = get_token_balance(web3, usdt_address, token_abi, wallet_address)
                    purchase_amount = new_usdt_balance - usdt_balance
                    if purchase_amount == 0:
                        effective_price = 0 #Wrong, but gives a hint that something is wrong
                    else:
                        effective_price = purchase_amount/ amount_in
                    print(f"Effective USDA sell price: ${effective_price:.4f}")
                    #Difference to target price
                    price_diff = effective_price - usda_price #A positive number indicates a good trade. Negative, a bad one 
                    print(f"Difference to target sell price: ${price_diff:.4f}")
                else:
                    print("❌ Transaction failed.")
            else:
                print("❌ Not enough USDA to sell!")

            # Sleep for a period
            #time.sleep(900) # Sleeps for 900 seconds (15 minute)

    except Exception as e:
        print(f"Error: {e}")
    
if __name__ == "__main__":
    try:
        main_loop()

    except KeyboardInterrupt:
        print("Worker shutting down...")
        sys.exit(0)
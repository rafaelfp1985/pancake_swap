from web3 import Web3
from web3.middleware import geth_poa_middleware

import requests
import time
import json
import streamlit as st

# Title
st.title("🦊 PancakeSwap Monitor")

# Setup Web3
st.write("Starting Web3 Component...")
web3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)
wallet_address = st.secrets['wallet_address']
private_key = st.secrets['private_key']
#st.write(wallet_address)
#st.write(private_key)

# Load ABI
st.write("Loading ABI file...")
with open('abi.json', 'r') as abi_file:
    router_abi = json.load(abi_file)

# Contract setup
st.write("Setting up contracts...")
router_address = Web3.to_checksum_address('0x10ED43C718714eb63d5aA57B78B54704E256024E')
router_contract = web3.eth.contract(address=router_address, abi=router_abi)

# Tokens
st.write("Setting up Tokens...")
usdt_address = Web3.to_checksum_address('0x55d398326f99059fF775485246999027B3197955')
usda_address = Web3.to_checksum_address('0x17EAfd08994305D8AcE37EfB82F1523177eC70EE')

# Parameters
st.write("Setting up parameters...")
amount_in = web3.to_wei(100, 'ether')
deadline = int(time.time()) + 60 * 20

# Price fetcher
def get_usda_price():
    st.write("Looking for the USDA price...")
    #Pancakeswap API doesn't work. Let's move to Coinmarketcap API
    #url = f'https://api.pancakeswap.info/api/v2/tokens/{usda_address}'
    #st.write(f'Calling URL: {url}')
    #response = requests.get(url)
    #data = response.json()
    #return float(data['data']['price'])
    token_price = get_latest_price_by_id(37721)
    return token_price

# Swap function
def swap_tokens():
    st.write("Starting wallet...")
    checksum_address = Web3.to_checksum_address(wallet_address)
    #nonce = web3.eth.get_transaction_count(wallet_address)
    nonce = web3.eth.get_transaction_count(checksum_address)
    st.write("Start swapping...")
    tx = router_contract.functions.swapExactTokensForTokens(
        amount_in,
        0,
        [usdt_address, usda_address],
        checksum_address,
        deadline
    ).build_transaction({
        'from': checksum_address,
        'gas': 200000,
        'nonce': nonce
    })

    st.write("Getting TX...")
    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    return web3.to_hex(tx_hash)

def get_latest_price_by_id(api_id):
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    api_key = st.secrets["COINMARKET_API_KEY"]# Replace with your actual API key

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

# Auto-refresh every 5 minutes
#st.markdown("""
#    <script>
#        setTimeout(function() {
#            window.location.reload();
#        }, 300000);
#    </script>
#""", unsafe_allow_html=True)

# UI
try:
    st.write("Request USDA price...")
    price = get_usda_price()
    st.write("Current USDA Price", f"${price:.4f}")

    if price < 1.96:
        st.success("✅ Price condition met! Ready to swap.")
        tx_hash = swap_tokens()
        st.write(f"Swap executed. Tx hash: `{tx_hash}`")
    else:
        st.warning("⏳ Price too high. Waiting for drop below $0.96.")

except Exception as e:
    st.error(f"Error: {e}")

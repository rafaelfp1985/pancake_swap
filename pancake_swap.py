from web3 import Web3
import requests
import time
import json
import streamlit as st

# Title
st.title("🦊 PancakeSwap Monitor")

# Load secrets
#api_key = st.secrets["MY_API_KEY"]

# Setup Web3
st.write("Starting Web3 Component...")
web3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
wallet_address = 'YOUR_WALLET_ADDRESS'
private_key = 'YOUR_PRIVATE_KEY'

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
    url = f'https://api.pancakeswap.info/api/v2/tokens/{usda_address}'
    st.write("Calling URL: {url}")
    response = requests.get(url)
    data = response.json()
    return float(data['data']['price'])

# Swap function
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
    return web3.to_hex(tx_hash)

# Auto-refresh every 5 minutes
st.markdown("""
    <script>
        setTimeout(function() {
            window.location.reload();
        }, 300000);
    </script>
""", unsafe_allow_html=True)

# UI
try:
    st.write("Request USDA price...")
    price = get_usda_price()
    st.write("Current USDA Price", f"${price:.4f}")

    if price < 0.96:
        st.success("✅ Price condition met! Ready to swap.")
        #tx_hash = swap_tokens()
        #st.write(f"Swap executed. Tx hash: `{tx_hash}`")
    else:
        st.warning("⏳ Price too high. Waiting for drop below $0.96.")

except Exception as e:
    st.error(f"Error: {e}")

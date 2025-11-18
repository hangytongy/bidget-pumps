import requests
import time
import dotenv
import os

dotenv.load_dotenv()

MARKET_LIMIT = int(os.getenv('MARKET_LIMIT'))
OB_LIMIT = int(os.getenv('OB_LIMIT'))
BID_WALL_THRESHOLD = int(os.getenv('BID_WALL_THRESHOLD'))
IMBALANCE_PERCENT = float(os.getenv('IMBALANCE_PERCENT')) # 0 - 1
OB_IMBAL_THRESHOLD= float(os.getenv('OB_IMBAL_THRESHOLD'))
PRICE_DIFF_THRESHOLD = float(os.getenv('PRICE_DIFF_THRESHOLD')) #in terms of % 0 - 100

### -----------------------------
### STEP 1: GET BITGET PERP MARKETS
### -----------------------------
def get_bitget_perp_symbols():
    url = "https://api.bitget.com/api/mix/v1/market/contracts?productType=umcbl"
    r = requests.get(url)
    data = r.json().get("data", [])

    symbols = []
    for item in data:
        inst = item["symbol"]  # e.g. "BTCUSDT_UMCBL"
        if inst.endswith("USDT_UMCBL"):
            token = inst.replace("USDT_UMCBL", "")
            symbols.append(token.lower())

    return list(set(symbols))


### -----------------------------
### STEP 2: GET COINGECKO TOKEN LIST
### -----------------------------
def get_coingecko_list():
    url = "https://api.coingecko.com/api/v3/coins/list"
    r = requests.get(url)
    return r.json()


def build_symbol_to_id_map(cg_list):
    mapping = {}
    for item in cg_list:
        mapping.setdefault(item["symbol"].lower(), []).append(item["id"])
    return mapping


### -----------------------------
### STEP 3: FETCH FDV
### -----------------------------
def fetch_fdv(cg_id):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": cg_id,
        "order": "market_cap_desc",
        "per_page": 1,
        "page": 1,
        "sparkline": False,
    }

    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(r.status_code)
        return None

    data = r.json()
    if not data:
        return None

    item = data[0]

    return {
        "id": cg_id,
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "price": item.get("current_price"),
        "market_cap": item.get("market_cap"),
        "fdv": item.get("fully_diluted_valuation"),
    }


### -----------------------------
### STEP 4: ORDERBOOK FETCHER
### -----------------------------
#imbalance_pct -> 0 - 1, calculates how much % from the mid point price you want to calculate your OB imbalance
def get_bitget_orderbook(symbol, limit=OB_LIMIT, imbalance_pct=IMBALANCE_PERCENT, bid_wall_threshold=BID_WALL_THRESHOLD, imbal_threshold = OB_IMBAL_THRESHOLD):
    """
    Fetch Bitget USDT perpetual orderbook for a symbol and compute:
      1. Orderbook imbalance (bid/ask ratio in a small % range around last price)
      2. Check for large bid wall > bid_wall_threshold
    """
    symbol_pair = f"{symbol.upper()}USDT_UMCBL"
    
    # --- Fetch orderbook ---
    url = "https://api.bitget.com/api/mix/v1/market/depth"
    params = {"symbol": symbol_pair, "limit": limit}
    r = requests.get(url, params=params)
    
    if r.status_code != 200:
        print(f"⚠️ Orderbook fetch failed for {symbol}: {r.status_code}")
        return None
    
    data = r.json().get("data", {})
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    timestamp = data.get("ts")

    # --- Compute last price ---
    if not bids or not asks:
        return None
    last_price = (float(bids[0][0]) + float(asks[0][0])) / 2

    # --- Compute orderbook imbalance ---
    pct = imbalance_pct
    min_bid = last_price * (1 - pct)
    max_ask = last_price * (1 + pct)

    bid_depth = sum(float(bid[1]) for bid in bids if min_bid <= float(bid[0]) <= last_price)
    ask_depth = sum(float(ask[1]) for ask in asks if last_price <= float(ask[0]) <= max_ask)
    orderbook_imbalance = round(bid_depth / ask_depth, 2) if ask_depth != 0 else None

    if orderbook_imbalance and orderbook_imbalance < OB_IMBAL_THRESHOLD:
        ob_imbal_signal = False
    else:
        ob_imbal_signal = True

    # --- Check for large bid wall ---
    bid_wall_signal = False
    bid_wall_price = None
    bid_wall_amt = None
    for price, size in bids:
        #USD = size * price
        if float(size) * float(price) >= bid_wall_threshold:
            bid_wall_signal = True
            bid_wall_price = float(price)
            bid_wall_amt = float(size) * float(price)
            break

    return {
        "asks": asks,
        "bids": bids,
        "timestamp": timestamp,
        "last_price": last_price,
        "orderbook_imbalance": orderbook_imbalance,
        "orderbook_imbalance_signal" : ob_imbal_signal,
        "bid_wall_signal": bid_wall_signal,
        "bid_wall_price" : bid_wall_price,
        "bid_wall_amount" : bid_wall_amt
    }

import requests

def fetch_hyperliquid_symbols():
    url = "https://api.hyperliquid.xyz/info"

    headers = {
        "Content_Type" : "application/json"
    }
    payload = {
        "type": "meta",
        "dex": ""  # empty means default (Hyperliquid main perp dex)
    }
    resp = requests.post(url, json=payload, headers= headers)
    resp.raise_for_status()
    data = resp.json()['universe']
    symbols = [s['name'] for s in data]
    print(symbols)

    return symbols

def fetch_binance_usdt_perps():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()

    symbols = []
    for s in data['symbols']:
        # Check if it's USDT-margined perpetual
        if s['contractType'] == 'PERPETUAL' and s['quoteAsset'] == 'USDT':
            symbol = s['symbol'].replace("USDT","")
            symbols.append(symbol)

    return symbols

def get_binance_perp_price(symbol: str):
    """
    Get the current price of a USDT-margined perpetual contract.
    :param symbol: e.g. "BTCUSDT", "ETHUSDT"
    """
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    symbol = symbol + "USDT"
    params = {"symbol": symbol.upper()}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"⚠️ Failed to fetch price for {symbol}: {response.status_code}")
        return None
    data = response.json()
    return float(data['price'])

def get_all_fdv(cg_symbols):

    data = []
    ids = ",".join(cg_symbols)

    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}"
    response = requests.get(url)

    print(response.status_code)

    response = response.json()

    for token in response:
        ea_token = {
            'symbol' : token['symbol'],
            'cg_symbol' : token['id'],
            'market_cap' : token['market_cap'],
            'fdv' : token.get('fully_diluted_valuation')
        }

        data.append(ea_token)

    return data

def chunk_list(lst, size=100):
    """Yield successive chunks of size."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def get_all_fdv_batched(cg_symbols):
    final_results = []

    # Loop through batches of 100
    for batch in chunk_list(cg_symbols, size=100):
        print(f"Fetching FDV for {len(batch)} tokens...")

        result = get_all_fdv(batch)
        if result:
            final_results.extend(result)   # concat to final list
        
        time.sleep(1)

    return final_results

def process_token(token,hl_symbols,binance_symbols):
    sym = token["bitget_symbol"]
    ob_data = get_bitget_orderbook(sym)

    if not ob_data:
        return None

    # The same logic you had inside the loop:
    if ob_data['bid_wall_signal'] and ob_data['orderbook_imbalance_signal']:
        in_hl = sym.upper() in hl_symbols
        in_binance = sym.upper() in binance_symbols

        price_diff_pct = None
        if in_binance:
            nance_price = get_binance_perp_price(sym)
            bitget_price = float(ob_data['last_price'])

        if (not in_hl) and in_binance> PRICE_DIFF_THRESHOLD:
            return {
                'symbol': sym,
                'is_in_HL': in_hl,
                'is_in_Binance': in_binance,
                'bid_wall_price': ob_data['bid_wall_price'],
                'bid_wall_amt' : ob_data['bid_wall_amount'],
                'orderbook_imbalance': ob_data['orderbook_imbalance'],
                'binance_price': nance_price,
                'bitget_price' : bitget_price
            }

    return None

def format_ob_list(ob_list):
    msg = "📊 *ALERT BITGET MANIPULATION*\n\n"
    for item in ob_list:
        msg += (
            f"🔹 *{item['symbol'].upper()}*\n"
            f"• In HL: `{item['is_in_HL']}`\n"
            f"• In Binance: `{item['is_in_Binance']}`\n"
            f"• Bid Wall Price: `{item['bid_wall_price']}`\n"
            f"• Bid Wall Amount: `{item['bid_wall_amt']}`\n"
            f"• OB Imbalance: `{item['orderbook_imbalance']}`\n"
            f"• Binance Price: `{item['binance_price']}`\n"
            f"• Bitget Price: `{item['bitget_price']}`\n"
            f"\n"
        )
    return msg
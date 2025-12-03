from utils import *
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import dotenv
import os
from send_telegram_messge import send_telegram_message

dotenv.load_dotenv()

MARKET_LIMIT = int(os.getenv('MARKET_LIMIT'))
OB_LIMIT = int(os.getenv('OB_LIMIT'))
BID_WALL_THRESHOLD = int(os.getenv('BID_WALL_THRESHOLD'))
IMBALANCE_PERCENT = float(os.getenv('IMBALANCE_PERCENT')) # 0 - 1
OB_IMBAL_THRESHOLD= float(os.getenv('OB_IMBAL_THRESHOLD'))
PRICE_DIFF_THRESHOLD = float(os.getenv('PRICE_DIFF_THRESHOLD')) #in terms of % 0 - 100


### -----------------------------
### STEP 5: MAIN FLOW
### -----------------------------
def main():

    print("Fetching Hyperlquid Tokens....")
    hl_symbols = fetch_hyperliquid_symbols()
    print(hl_symbols)

    print("Fetching Binance Tokens.....")
    binance_symbols = fetch_binance_usdt_perps()
    print(binance_symbols)

    print("Fetching Bitget perp markets...")
    bitget_symbols = get_bitget_perp_symbols()
    bitget_symbols = bitget_symbols
    print(f"total bitget symbols = {len(bitget_symbols)}")

    print("Fetching CoinGecko list...")
    cg_list = get_coingecko_list()
    symbol_map = build_symbol_to_id_map(cg_list)

    ### Fetch FDV for all Bitget symbols
    all_avail_symbols = [sym for sym in bitget_symbols if sym in symbol_map]

    print(f"all symbols with mcap in coingecko = {len(all_avail_symbols)}")

    # to not hit rate limit in coingecko
    all_avail_symbols = random.sample(all_avail_symbols, len(all_avail_symbols))
    all_avail_symbols = all_avail_symbols[:200]

    cg_symbols = [symbol_map[sym][0] for sym in all_avail_symbols]

    print("get all tokens FDV")
    results = get_all_fdv_batched(cg_symbols)

    print(f"num of all results = {len(results)}")

    #need check if this correct, not sure why there is a None

    for result in results:
        cg = result['cg_symbol']
        for item in symbol_map:
            if cg in symbol_map[item]:
                bitget_symbol = item
                result['bitget_symbol'] = bitget_symbol

    ### FILTER FDV < $XM
    filtered = [
        x for x in results
        if x["fdv"] not in (None, 0) and x["fdv"] < MARKET_LIMIT
    ]

    print("\n=== TOKENS WITH FDV < $XM ===")
    for t in filtered:
        print(f"{t['symbol'].upper()} → FDV ${t['fdv']:,}")

    print("GET OB Data")
    OB_data_required = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_token, token,hl_symbols,binance_symbols) for token in filtered]

        for f in as_completed(futures):
            result = f.result()
            if result:
                OB_data_required.append(result)
    
    print("final OB data results")
    print(OB_data_required)

    if OB_data_required:
        message = format_ob_list(OB_data_required)
        send_telegram_message(message)



if __name__ == "__main__":
    main()

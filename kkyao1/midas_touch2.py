import os
import math
import json
import time
import twap
import numpy as np
import pandas as pd
import concurrent.futures
import MetaTrader5 as mt5
import stock_mapping as sm
from urllib import request
from datetime import datetime, timedelta
import shutil
import glob

def delete_folders_if_df_empty(df, folder_name_criteria):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    all_folders = [f for f in glob.glob(os.path.join(script_dir, '*')) if os.path.isdir(f)]
    folders_to_delete = [folder for folder in all_folders if any(criterion in folder for criterion in folder_name_criteria)]
    if df.empty:
        print("The DataFrame is empty. Deleting matched folders...")
        for folder_path in folders_to_delete:
            shutil.rmtree(folder_path)
            print(f"Deleted folder: {folder_path}")
    else:
        print("The DataFrame is not empty. No folders were deleted.")
    
def get_account_balance():
    account_info = mt5.account_info()
    if account_info is None:
        print("Failed to get account information.")
        return None
    account_balance = account_info.balance
    return account_balance

def save_df_to_csv(df, folder_name='No folder name specified', file_name='No file name specified', append=False):
    # Ensure the folder exists
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    if append:
        file_path = os.path.join(folder_name, f"{file_name}.csv")
        if os.path.exists(file_path):
            existing_df = pd.read_csv(file_path)
            updated_df = pd.concat([existing_df, df], ignore_index=True)
            updated_df.to_csv(file_path, index=False)
        else:
            df.to_csv(file_path, index=False)
    else:
        # If not appending, add date to the file name
        dated_file_name = f"{file_name}_{pd.to_datetime('today').strftime('%Y-%m-%d')}.csv"
        file_path = os.path.join(folder_name, dated_file_name)
        df.to_csv(file_path, index=False)
    print(f"Data {'appended to' if append else 'saved in'} {file_path}")

def get_api_data(symbol, end_date, period, num_days, api_token):
    base_url = "https://eodhd.com/api/eod/"
    period_in_days = 1 if period == 'd' else 0
    start_date = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=num_days * period_in_days)
    start_date = start_date.strftime("%Y-%m-%d")
    url = f"{base_url}{symbol}?from={start_date}&to={end_date}&period={period}&fmt=json&api_token={api_token}"
    try:
        with request.urlopen(url) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                return data[-num_days:]
            else:
                return f"Error: Unable to fetch data, status code {response.status}"
    except Exception as e:
        return f"Error: {e}"

def download_stocks(symbols, period, api_token, num_days=20):
    dfs = []
    for symbol in symbols:
        end_date = datetime.now().strftime("%Y-%m-%d")
        data = get_api_data(symbol, end_date, period, num_days, api_token)
        if isinstance(data, str) and "Error" in data:
            print(f"Failed to fetch data for {symbol}: {data}")
        else:
            try:
                df = pd.DataFrame(data)
                df.rename(columns={'date': 'time'}, inplace=True)  # Correctly rename 'date' to 'time'
                df.set_index('time', inplace=True)
                dfs.append(df[['adjusted_close']].rename(columns={'adjusted_close': symbol}))
            except KeyError as e:
                print(f"KeyError for {symbol}: {e}")
                continue
    if dfs:
        final_df = pd.concat(dfs, axis=1)
        return final_df
    else:
        return "No data fetched for any symbols."

def run_portfolio(prices, alpha_n=datetime.now().microsecond % 10 + 1, commission_rate=0.001):
    alpha1 = -(prices - prices.shift(alpha_n)) / prices.shift(alpha_n)
    alpha1 = alpha1.dropna() 
    weights = alpha1.div(alpha1.abs().sum(axis=1), axis=0)
    weights[weights < 0] = 0
    weights = weights.div(weights.sum(axis=1), axis=0)
    weights = weights.fillna(0)
    latest_weights = weights.iloc[-1]
    portfolio_returns = (weights.shift() * prices.pct_change()).sum(axis=1)
    portfolio_returns = portfolio_returns - commission_rate
    return weights, latest_weights

def calculate_stock_allocation(total_investment, weights_series, price_df, min_order_size=100):
    latest_prices = price_df.iloc[-1]
    allocated_money = weights_series * total_investment
    max_units_raw = allocated_money / latest_prices
    if not np.isfinite(max_units_raw).all():
        print("Non-finite values found in max_units_raw. Handling...")
    max_units_raw[~np.isfinite(max_units_raw)] = 0 #infinites are set to 0
    max_units = np.floor(max_units_raw / min_order_size) * min_order_size
    max_units = max_units.astype(int)
    allocated_money = latest_prices * max_units
    allocation_df = pd.DataFrame({
        'Share Symbol': latest_prices.index,
        'Share Price': latest_prices.values,
        'Allocated Units': max_units.values,
        'Weights': weights_series.values
    })
    return allocation_df

def find_latest_csv(folder_name):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(script_dir, folder_name)
    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return None
    files = os.listdir(folder_path)
    csv_files = [file for file in files if file.endswith('.csv')]
    if not csv_files:
        print("No CSV files found. Assuming initial run.")
        return None
    def extract_date(file_name):
        try:
            return datetime.strptime(file_name, 'allocation_%Y-%m-%d.csv')
        except ValueError:
            pass  # Handle other filename formats if needed
    csv_files.sort(key=extract_date, reverse=True)
    if not csv_files or extract_date(csv_files[0]) is None:
        csv_files.sort(key=lambda f: os.path.getmtime(os.path.join(folder_path, f)), reverse=True)

    return os.path.join(folder_path, csv_files[0])

def get_folder(folder_name='daily_allocation'):
    latest_csv_path = find_latest_csv(folder_name)
    if latest_csv_path:
        return pd.read_csv(latest_csv_path)
    else:
        return None

##########################################TWAP execution#############################################
# def place_order(row, comment="kkyao1"):
#     symbol = row['Share Symbol']
#     price = row['Share Price']
#     entry_units = row['Entry Units']
#     exit_units = row['Exit Units']
#     order_ids = []

#     if entry_units > 0:
#         print(f"Placing entry order for {symbol}")
#         result = twap.TWAPStrategy2(symbol=symbol, 
#                                     action="Buy", 
#                                     execPeriod=60,#*60*2, 
#                                     execMode='Qty', 
#                                     execUnits=entry_units, 
#                                     targetTWAP=price,
#                                     slippage=0.02, 
#                                     qtyRatio=0.2, 
#                                     orderInterval=5, 
#                                     magic=20231207, 
#                                     comment=comment)
#         if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
#             order_ids.append(result.order)
#     if exit_units > 0:
#         print(f"Placing exit order for {symbol}")
#         result = twap.TWAPStrategy2(symbol=symbol, 
#                                     action="Sell", 
#                                     execPeriod=60,#*60*2, 
#                                     execMode='Qty', 
#                                     execUnits=exit_units, 
#                                     targetTWAP=price, 
#                                     slippage=0.02, 
#                                     qtyRatio=0.2, 
#                                     orderInterval=5, 
#                                     magic=20231207, 
#                                     comment=comment)
#         if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
#             order_ids.append(result.order)
#     return order_ids

# def execute_trades_from_data(allocation_df):
#     with concurrent.futures.ThreadPoolExecutor() as executor:
#         futures = [executor.submit(place_order, row) for _, row in allocation_df.iterrows()]
#         results = [future.result() for future in concurrent.futures.as_completed(futures)]
#     order_ids = [order_id for sublist in results for order_id in sublist]
#     return order_ids
##########################################TWAP execution#############################################

##########################################LIMIT execution#############################################
def execute_mt5_order(symbol, execute_price, order_type, volume, sl, tp, deviation,magic_number=8888,comment_msg='say something'):
    if not mt5.symbol_select(symbol, True):
        print("symbol_select() failed, symbol not found in market watch:", symbol)
        return
    order_type_dict = {
        'buy': mt5.ORDER_TYPE_BUY, # mt5.ORDER_TYPE_BUY_LIMIT
        'sell': mt5.ORDER_TYPE_SELL # mt5.ORDER_TYPE_SELL_LIMIT
    }
    if order_type.lower() not in order_type_dict:
        print(f"Order type '{order_type}' is not supported.")
        return

    request = {
        "action": mt5.TRADE_ACTION_DEAL,#mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": order_type_dict[order_type.lower()],
        #"price": execute_price, #limit order ONLY
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": magic_number,
        "comment": comment_msg,
        "type_time": mt5.ORDER_TIME_GTC,  
        "type_filling": mt5.ORDER_FILLING_RETURN,  
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Order send failed, retcode =", result.retcode)
        print("Error message:", mt5.last_error())
    else:
        print("Order executed successfully, transaction ID =", result.order)
    return result

def execute_trades_from_data(allocation_df):
    order_ids = []
    for index, row in allocation_df.iterrows():
        symbol = row['Share Symbol']
        price = row['Share Price']
        entry_units = row['Entry Units']
        exit_units = row['Exit Units']
        if entry_units > 0:
            print(f"Placing entry order for {symbol}")
            result = execute_mt5_order(symbol=symbol, 
                                       execute_price=price, 
                                       order_type='buy', 
                                       volume=entry_units, 
                                       sl=0.0, tp=0.0, 
                                       deviation=10, 
                                       magic_number=20231207, 
                                       comment_msg='kkyao1 Entry')
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                order_ids.append(result.order)
        if exit_units > 0:
            print(f"Placing exit order for {symbol}")
            result = execute_mt5_order(symbol=symbol, 
                                       execute_price=price, 
                                       order_type='sell', 
                                       volume=exit_units,
                                       sl=0.0, tp=0.0, 
                                       deviation=10, 
                                       magic_number=20231207,
                                       comment_msg='kkyao1 Exit')
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                order_ids.append(result.order)
    return order_ids
##########################################LIMIT execution#############################################

##########################################second execution#############################################
def check_order_status(order_id):
    order_info = mt5.orders_get(ticket=order_id)
    if order_info is None or len(order_info) == 0:
        print(f"Order with ticket {order_id} not found or error occurred, error code =", mt5.last_error())
        return None
    order = order_info[0] 
    return {
        'ticket': order.ticket,
        'type': order.type,
        'volume_initial': order.volume_initial,
        'volume_current': order.volume_current,
        'price_open': order.price_open,
        'price_current': order.price_current,
        'symbol': order.symbol,
    }

def delete_orders(orders_details_list):
    deleted_volumes = []
    for order_details in orders_details_list:
        if order_details is not None:
            symbol_info = mt5.symbol_info(order_details['symbol'])
            if symbol_info is None:
                print("Failed to get symbol info, error code =", mt5.last_error())
                continue
            symbol = order_details['symbol']
            order_id = order_details['ticket']
            direction = order_details['type']
            volume_initial = order_details['volume_initial']
            volume_current = order_details['volume_current']
            volume_filled = volume_initial - volume_current
            delete_result = mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order_id
            })
            if not (delete_result and delete_result.retcode == mt5.TRADE_RETCODE_DONE):
                print(f"Failed to cancel order {order_id}, error code =", mt5.last_error())
            else:
                print(f"Order {order_id} canceled successfully.")
                # Record specific details of the deleted volume for the symbol
                deleted_info = {
                    'symbol': symbol,
                    'volume_filled': volume_filled,
                    'direction': direction
                }
                deleted_volumes.append(deleted_info)
    return deleted_volumes
##########################################second execution#############################################

##############################Dummy weights##############################
import random
import pandas as pd
def generate_random_series(tickers, seed=None):
    if seed is not None:
        random.seed(seed)
    random_values = [random.random() for _ in tickers]
    total = sum(random_values)
    normalized_values = [value / total for value in random_values]
    return pd.Series(normalized_values, index=tickers)
# latest_weights = mt2.generate_random_series(mt5_symbol)
#########################################################################
def get_opening_orders(stock_symbols, weights):
    all_positions = []
    open_prices = {}
    for symbol in stock_symbols:
        positions = mt5.positions_get(symbol=symbol)
        today_open_price = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 1)
        if positions is None:
            print(f"No positions for {symbol}, error code={mt5.last_error()}")
        elif len(positions) > 0:
            all_positions.extend(list(positions))
            open_prices[symbol] = today_open_price[0]['open']
    df = pd.DataFrame()
    if all_positions:
        df = pd.DataFrame(all_positions, columns=all_positions[0]._asdict().keys())
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.drop(['time_msc', 'time_update', 'time_update_msc', 'identifier', 'reason', 
                      'sl', 'tp', 'swap', 'comment', 'external_id'], axis=1)
        df['position_change'] = (df['price_current'] / df['price_open']) - 1
        df['open_value'] = df['volume'] * df['price_open']
        df['curr_value'] = df['volume'] * df['price_current']
        df['weights'] = df['symbol'].map(weights)
        df['portfolio_change_position'] = df['weights'] * df['position_change']
    total_portfolio_change_position = df['portfolio_change_position'].sum() if not df.empty else 0
    print(f"Total portfolio change position: {total_portfolio_change_position:.4%}")
    return total_portfolio_change_position, df

def get_filled_orders(symbol_list, magic = 4444):
    from_date = datetime.now()
    to_date = datetime.now() + timedelta(days=1)

    print(f"from_date: {from_date}")
    print(f"to_date: {to_date}")
    all_deals = []
    for symbol in symbol_list:
        deals = mt5.history_orders_get(from_date, to_date)
        if deals is None:
            print(f"No deals for {symbol}, error code={mt5.last_error()}")
        elif len(deals) > 0:
            all_deals.extend(list(deals))
    if not all_deals:
        print("No deals found for any of the specified symbols.")
        return pd.DataFrame()
    df = pd.DataFrame(all_deals, columns=all_deals[0]._asdict().keys())
    df['time_done'] = pd.to_datetime(df['time_done'], unit='s')
    # Drop columns
    df = df.drop(['time_setup', 'time_done_msc', 'time_setup_msc', 'time_expiration', 'sl',
                  'type_time', 'type_filling', 'reason', 'tp',
                  'position_id', 'position_by_id', 'external_id', 'price_stoplimit'], axis=1)
    df = df.drop_duplicates()
    df['volume_filled'] = df['volume_initial'] - df['volume_current']
    filled_orders = df[(df['state'] == 4) | (df['state'] == 2)]
    #filled_orders = df[df['magic'] == magic]
    filled_orders = filled_orders[filled_orders['symbol'].isin(symbol_list)]
    return filled_orders
    
def create_daily_log(filled_orders, opening_df, starting_cash=10000, log_folder="daily_portfolio", log_file_name="balance.csv"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_folder_path = os.path.join(script_dir, log_folder)
    log_file_path = os.path.join(log_folder_path, log_file_name)
    if os.path.exists(log_folder_path) and os.path.isfile(log_file_path):
        previous_log = pd.read_csv(log_file_path)
        initial_capital = previous_log.iloc[-1]['Cash Balance']
    else:
        initial_capital = starting_cash
    cash_balance = initial_capital
    # Calculate purchase cost
    buy_order = filled_orders[filled_orders['type'] == 0] #==2 if limit buy
    #price_open if limit buy
    purchase_cost = (buy_order['price_current'] * buy_order['volume_filled']).sum()
    cash_balance -= purchase_cost
    # Calculate portfolio value
    portfolio_value = (opening_df['price_current'] * opening_df['volume']).sum()
    # Calculate sales proceeds
    sell_order = filled_orders[filled_orders['type'] == 1] #==3 if limit sell
    sales_proceed = (sell_order['price_open'] * sell_order['volume_filled']).sum()
    cash_balance += sales_proceed
    # Total value
    total_value = cash_balance + portfolio_value
    # Create the log dataframe
    log_df = pd.DataFrame({
        'Date': [pd.to_datetime('today').date()],
        'Initial Capital': [initial_capital],
        'Cash Balance': [cash_balance],
        'Portfolio Value': [portfolio_value],
        'Purchase Cost': [purchase_cost],
        'Sales Proceeds': [sales_proceed],
        'Total Value': [total_value]
    })
    return log_df

def close_all_positions(df, comment):
    for _, row in df.iterrows():
        symbol = row['symbol']
        volume = row['volume']
        # Fetch the current bid price for the symbol
        symbol_info = mt5.symbol_info_tick(symbol)
        if symbol_info is None:
            print(f"Failed to get symbol info for {symbol}, error code =", mt5.last_error())
            continue
        current_bid = symbol_info.bid
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL_LIMIT,
            "price": current_bid-0.02,
            "deviation": 20,  # Deviation in points
            "magic": 20231207,       # Magic number, if needed
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to close position for {symbol}, error code: {result.retcode}")
        else:
            print(f"Position on {symbol} closed successfully.")

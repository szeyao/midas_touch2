import os
import math
import pandas as pd
from datetime import datetime
import numpy as np
import MetaTrader5 as mt5

def tick_rule(price):
    price = int(price)
    if price < int(1):
        return 0.005
    elif price >= int(1) and price < int(10):
        return 0.01
    elif price >= int(10) and price < int(100):
        return 0.02
    else:
        return 0.1
    
def get_account_balance():
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        return None
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

def download_stocks(symbols, n_dfPoint=200, timeframe=mt5.TIMEFRAME_D1):
    dfs = []  # List to hold individual dataframes
    if not mt5.initialize():
        print("initialize() failed, error code =",mt5.last_error())
        return None
    for symbol in symbols:
        # Fetch the data using MT5 API
        data = mt5.copy_rates_from_pos(symbol, timeframe, 1, n_dfPoint)
        # Convert the data into a DataFrame
        df = pd.DataFrame(data)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        # Rename the 'close' column to the stock symbol and append to the dfs list
        dfs.append(df[['close']].rename(columns={'close': symbol}))
    final_df = pd.concat(dfs, axis=1)
    return final_df

def run_portfolio(prices, commission_rate=0.001):
    # Calculate Alpha1
    alpha1 = -(prices - prices.shift(5)) / prices.shift(5)
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

def compile_portfolio_data(allocation_df, starting_cash, current_share_value):
    purchase_cost = (allocation_df['Share Price'] * allocation_df['Entry Units']).sum()
    sale_proceed = (allocation_df['Share Price'] * allocation_df['Exit Units']).sum()
    cash_value = starting_cash - purchase_cost + sale_proceed
    portfolio_value = current_share_value
    total_value = portfolio_value + cash_value  # adjusted to account for the initial capital
    portfolio_data = {
        'Starting Capital': [starting_cash],
        'Purchase Cost': [purchase_cost],
        'Sale Proceed': [sale_proceed],
        'Cash Value': [cash_value],
        'Portfolio Value': [portfolio_value],
        'Total Value': [total_value]
    }
    portfolio_df = pd.DataFrame(portfolio_data)
    return portfolio_df

def find_latest_csv(folder_path):
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
    
def get_open_positions(ticker):
    positions = mt5.positions_get(symbol=ticker)
    if positions is None or len(positions) == 0:
        print('No open positions for', ticker)
        return 0, 0
    else:
        positions_dict = positions[0]._asdict()
        holding_vol = positions_dict['volume']
        holding_price = positions_dict['price_open']
        return holding_vol, holding_price

def round_to_tick(price):
    tick = tick_rule(price)
    tick_decimal_point = len(str(tick).split('.')[1])
    n_ticks = price / tick
    rounded_ticks = math.ceil(n_ticks)
    rounded_price = round(rounded_ticks * tick, tick_decimal_point)
    return rounded_price


##########################################first execution#############################################
def execute_mt5_order(symbol, execute_price, order_type, volume, sl, tp, deviation,magic_number=8888,comment_msg='say something'):
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        return
    if not mt5.symbol_select(symbol, True):
        print("symbol_select() failed, symbol not found in market watch:", symbol)
        return
    order_type_dict = {
        'buy': mt5.ORDER_TYPE_BUY_LIMIT,
        'sell': mt5.ORDER_TYPE_SELL_LIMIT
    }
    if order_type.lower() not in order_type_dict:
        print(f"Order type '{order_type}' is not supported.")
        return

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": order_type_dict[order_type.lower()],
        "price": execute_price,
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
                                       magic_number=8888, 
                                       comment_msg='First entry')
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
                                       magic_number=8888, 
                                       comment_msg='First exit')
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                order_ids.append(result.order)
    return order_ids
##########################################first execution#############################################


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

def delete_and_resubmit_orders(orders_details_list):
    resubmitted_orders = []
    for order_details in orders_details_list:
        if order_details is not None:
            symbol_info = mt5.symbol_info(order_details['symbol'])
            if symbol_info is None:
                print("Failed to get symbol info, error code =", mt5.last_error())
                continue
            symbol = order_details['symbol']
            order_id = order_details['ticket']
            volume_current = order_details['volume_current']
            order_type = order_details['type']
            delete_result = mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order_id
            })
            if not (delete_result and delete_result.retcode == mt5.TRADE_RETCODE_DONE):
                print(f"Failed to cancel order {order_id}, error code =", mt5.last_error())
                continue
            print(f"Order {order_id} canceled successfully.")
            price = symbol_info.ask if order_type == mt5.ORDER_TYPE_BUY_LIMIT else symbol_info.bid
            new_request = {
                'action': mt5.TRADE_ACTION_PENDING,
                'symbol': symbol,
                'volume': volume_current,
                'type': order_type,
                'price': price,
                'deviation': 10,
                'magic': 6666,
                'comment': 'Resubmitted order',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_RETURN,
            }
            new_order_result = mt5.order_send(new_request)
            if new_order_result and new_order_result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"New order placed successfully with ticket {new_order_result.order}")
                # Record specific details of the new order
                order_info = {
                    'symbol': symbol,
                    'volume': volume_current,
                    'price': price,
                    'type': order_type
                }
                resubmitted_orders.append(order_info)
            else:
                print("Failed to place a new order, error code =", mt5.last_error())
    return resubmitted_orders
##########################################second execution#############################################

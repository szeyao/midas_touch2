import os
import math
import pandas as pd
from datetime import datetime
import numpy as np
import MetaTrader5 as mt5
import time
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
        mt5.shutdown()
        return None
    account_balance = account_info.balance
    mt5.shutdown()
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
    mt5.shutdown()
    final_df = pd.concat(dfs, axis=1)
    return final_df

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





##########################################
def cancel_order(order_id):
    """Attempt to cancel the order with the given order_id and store its details."""
    # First, retrieve the order details
    order_info = mt5.orders_get(ticket=order_id)
    
    if order_info is None or len(order_info) == 0:
        print(f"No order with ID {order_id} found.")
        return None

    # Assuming there is only one order with this ticket, as ticket numbers are unique
    order_info = order_info[0]

    # Store the details you want from the order
    order_details = {
        'ticket': order_info.ticket,
        'symbol': order_info.symbol,
        'type': order_info.type,
        'volume': order_info.volume,
        # Add other fields if needed
    }

    # Now, create and send the cancellation request
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": order_id,
    }
    result = mt5.order_send(request)
    
    # If the cancellation was successful, return the stored order details
    if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"Order {order_id} was successfully canceled.")
        return order_details
    else:
        error_code = result.retcode if result is not None else mt5.last_error()
        print(f"Failed to cancel order {order_id}, error code =", error_code)
        return None

def cancel_order(order_id):
    """Attempt to cancel the order with the given order_id."""
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": order_id,
    }
    result = mt5.order_send(request)
    return result  # Make sure this line is included to return the result
##################################






def check_order_status(order_id, timeout=10):  # timeout in seconds, 10 minutes = 600 seconds
    """Check if an order with the specified order_id has been executed or cancel it if it exceeds the timeout."""
    mt5.initialize()
    start_time = time.time()  # Record the start time
    while True:
        current_time = time.time()
        elapsed_time = current_time - start_time
        if elapsed_time > timeout:
            print(f"Order {order_id} has not been executed within the timeout period. Canceling the order.")
            result = cancel_order(order_id)  # Attempt to cancel the order
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"Order {order_id} canceled successfully.")
                break
            else:
                print(f"Failed to cancel order {order_id}, error code =", mt5.last_error())
                break
        orders = mt5.orders_get()
        if orders is None:
            print("No orders found, error code =", mt5.last_error())
            break
        order_found = False
        for order in orders:
            if order.ticket == order_id:
                order_found = True
                if order.type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
                    print(f"Order {order_id} is still pending.")
                break
        if not order_found:
            print(f"Order {order_id} has been executed or canceled.")
            break
        time.sleep(2) 

def execute_mt5_order(symbol, execute_price, order_type, volume, sl, tp, deviation,magic_number=8888,comment_msg='say something'):
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        mt5.shutdown()
        return
    if not mt5.symbol_select(symbol, True):
        print("symbol_select() failed, symbol not found in market watch:", symbol)
        mt5.shutdown()
        return
    order_type_dict = {
        'buy': mt5.ORDER_TYPE_BUY_LIMIT,
        'sell': mt5.ORDER_TYPE_SELL_LIMIT
    }
    if order_type.lower() not in order_type_dict:
        print(f"Order type '{order_type}' is not supported.")
        mt5.shutdown()
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
    mt5.shutdown()
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
                                       comment_msg='Entry order')
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
                                       comment_msg='Exit order')
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                order_ids.append(result.order)
    for order_id in order_ids:
        check_order_status(order_id)
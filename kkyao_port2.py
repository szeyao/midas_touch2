import os
import json
import time
import twap
import datetime
import asyncio
import warnings
import pandas as pd
import MetaTrader5 as mt5
import midas_touch2 as mt2
import stock_mapping as sm
warnings.filterwarnings('ignore')
if not mt5.initialize():
    print("initialize() failed")
else:
    print("MT5 successfully initialised.\n")

current_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_path)
config_file_name = 'config.json'
config_file_path = os.path.join(current_dir, config_file_name)
with open(config_file_path, 'r') as config_file:
        config = json.load(config_file)

symbols = config['symbols']
api_token = config['api_token']
mapping_file = config['mapping_file_path']
sleep_time = config['sleep_time']
account=config['execute_account']
password=config['password']
server=config['server']
Port_TPSL = config['Port_TPSL']
Magic = config['Magic']
starting_cash = config['starting_cash']
authorized=mt5.login(account, password=password, server=server)
if authorized:
    print(mt5.account_info())
else:
    print("failed to connect at account #{}, error code: {}".format(account, mt5.last_error()))

mt5_symbol = sm.get_ticker_list(symbols, file_path=mapping_file)
symbols = [symbol + "SE" for symbol in symbols]
price_df = mt2.download_stocks(symbols, "d", api_token, num_days=20)
price_df = pd.DataFrame(price_df)
price_df.columns = mt5_symbol
weights_df, latest_weights = mt2.run_portfolio(price_df, alpha_n=5)
print(f'latest_weights: {latest_weights}')
latest_weights = mt2.generate_random_series(mt5_symbol)
#ADD DUMMY WEIGHTS HERE TO TEST
total_investment = starting_cash
previous_allocation_df = mt2.get_folder(folder_name='daily_allocation')
previous_portfolio_df = mt2.get_folder(folder_name='daily_portfolio')
if previous_allocation_df is not None and previous_portfolio_df is not None:
    prev_holding = previous_allocation_df['Holding Units']
    prev_entry = previous_allocation_df['Entry Units']
    prev_exit = previous_allocation_df['Exit Units']
    total_investment = abs(previous_portfolio_df['Total Value'].iloc[-1])
    allocation_df = mt2.calculate_stock_allocation(total_investment, latest_weights, price_df)
    allocation_df['Holding Units'] = prev_holding + prev_entry - prev_exit
else: #first run
    allocation_df = mt2.calculate_stock_allocation(total_investment, latest_weights, price_df)
    print("This is the initial run. No previous allocation data available.")
    allocation_df['Holding Units'] = 0

# Calculate Entry and Exit Units
allocation_df['Entry Units'] = allocation_df.apply(
    lambda row: max(row['Allocated Units'] - row['Holding Units'], 0), axis=1)
allocation_df['Exit Units'] = allocation_df.apply(
    lambda row: max(row['Holding Units'] - row['Allocated Units'], 0), axis=1)
numeric_cols = allocation_df.select_dtypes(include=['number']).astype(float)
for col in numeric_cols.columns:
    allocation_df[col] = numeric_cols[col]
#print(f'first allocation: {allocation_df}')
# LIMIT
async def execute_and_check_trades(allocation_df, time):
    order_ids = mt2.execute_trades_from_data(allocation_df)
    await asyncio.sleep(time)
    orders_list = [mt2.check_order_status(order_id) for order_id in order_ids]
    deleted_volumes = mt2.delete_orders(orders_list)
    return orders_list, deleted_volumes
orders_list, deleted_volumes = asyncio.run(execute_and_check_trades(allocation_df, sleep_time))

# TWAP
# order_ids = mt2.execute_trades_from_data(allocation_df)
# orders_list = [mt2.check_order_status(order_id) for order_id in order_ids]
# deleted_volumes = mt2.delete_orders(orders_list)

for order in deleted_volumes:
    symbol = order['symbol']
    volume_filled = order['volume_filled']
    if order['direction'] == mt5.ORDER_TYPE_BUY_LIMIT:
        allocation_df.loc[allocation_df['Share Symbol'] == symbol, 'Entry Units'] = volume_filled
    else: 
        allocation_df.loc[allocation_df['Share Symbol'] == symbol, 'Exit Units'] = volume_filled
_, opening_orders = mt2.get_opening_orders(mt5_symbol, latest_weights)
filled_orders = mt2.get_filled_orders(mt5_symbol)

if not opening_orders.empty and not filled_orders.empty:
    # Create new columns for actual values without dropping the original columns
    entry_orders = filled_orders[filled_orders['type'] == 0]
    exits_orders = filled_orders[filled_orders['type'] == 1]

    # Group and rename for actual holding units
    actual_opening_units = opening_orders.groupby('symbol')['volume'].sum().reset_index()
    actual_opening_units.rename(columns={'volume': 'Actual Holding Units', 'symbol': 'Share Symbol'}, inplace=True)

    # Group and rename for actual entry units
    actual_entry_units = entry_orders.groupby('symbol')['volume_initial'].sum().reset_index()
    actual_entry_units.rename(columns={'volume_initial': 'Actual Entry Units', 'symbol': 'Share Symbol'}, inplace=True)

    # Group and rename for actual exit units
    actual_exit_units = exits_orders.groupby('symbol')['volume_initial'].sum().reset_index()
    actual_exit_units.rename(columns={'volume_initial': 'Actual Exit Units', 'symbol': 'Share Symbol'}, inplace=True)

    # Group and rename for actual exit prices
    actual_exit_prices = exits_orders.groupby('symbol')['price_current'].mean().reset_index()
    actual_exit_prices.rename(columns={'price_current': 'Actual Exit Price', 'symbol': 'Share Symbol'}, inplace=True)
    if 'Exit Price' not in allocation_df.columns:
        allocation_df['Exit Price'] = 0.0
    # Merge the new columns with allocation_df
    allocation_df = pd.merge(allocation_df, actual_exit_prices, on='Share Symbol', how='left')
    allocation_df = pd.merge(allocation_df, actual_opening_units, on='Share Symbol', how='left')
    allocation_df = pd.merge(allocation_df, actual_entry_units, on='Share Symbol', how='left')
    allocation_df = pd.merge(allocation_df, actual_exit_units, on='Share Symbol', how='left')

    # Fill NaN values with 0 for the new columns
    allocation_df['Actual Exit Price'].fillna(0, inplace=True)
    allocation_df['Actual Holding Units'].fillna(0, inplace=True)
    allocation_df['Actual Entry Units'].fillna(0, inplace=True)
    allocation_df['Actual Exit Units'].fillna(0, inplace=True)

    # Assuming you still want to update 'Entry Price' and 'Current Price' from opening_orders
    allocation_df['Entry Price'] = opening_orders['price_open']
    allocation_df['Current Price'] = opening_orders['price_current']
    allocation_df['Entry Price'].fillna(0, inplace=True)
    allocation_df['Current Price'].fillna(0, inplace=True)
else:
    print("No opening_orders or filled_orders found.")

log_entry = mt2.generate_daily_log(allocation_df)
start_time = datetime.time(9, 00)
end_time = datetime.time(14, 40)
while True:
    current_time = datetime.datetime.now().time()
    if start_time <= current_time <= end_time:
        today_return,_ = mt2.get_opening_orders(mt5_symbol, latest_weights)
        if today_return <= -Port_TPSL:
            mt2.close_all_positions(opening_orders, 'Port_SL')
            break
        elif today_return >= Port_TPSL:
            mt2.close_all_positions(opening_orders, 'Port_TP')
            break
        else:
            print("Portfolio within risk limits.")
        print('Checked, sleeping for 5 seconds...')
        time.sleep(5) 
    else:
        print("Outside monitoring hours.")
        break
mt2.save_df_to_csv(log_entry, 
                   folder_name='daily_portfolio', 
                   file_name='balance',
                   append=True)
mt2.save_df_to_csv(allocation_df,
                     folder_name='daily_allocation', 
                     file_name='allocation')
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

# mt5.market_book_add('CIMB')
# add = mt5.market_book_get('CIMB')
# print(f'add: {add}')
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
recent_filled_time = config['recent_filled_time']
starting_cash = config['starting_cash']

# mt5.market_book_add('CIMB')
# add = mt5.market_book_get('CIMB')
# print(f'add: {add}')
authorized=mt5.login(account, password=password, server=server)
if authorized:
    print(mt5.account_info())
else:
    print("failed to connect at account #{}, error code: {}".format(account, mt5.last_error()))
# mt5.market_book_add('CIMB')
# add = mt5.market_book_get('CIMB')
# print(f'add: {add}')
mt5_symbol = sm.get_ticker_list(symbols, file_path=mapping_file)
symbols = [symbol + "SE" for symbol in symbols]
price_df = mt2.download_stocks(symbols, "d", api_token, num_days=20)
price_df = pd.DataFrame(price_df)
#price_df = price_df[:-1]
price_df.columns = mt5_symbol
weights_df, latest_weights = mt2.run_portfolio(price_df, alpha_n=5)

#latest_weights = mt2.generate_random_series(mt5_symbol)
#ADD DUMMY WEIGHTS HERE TO TEST
print(f'latest_weights: {latest_weights}')
total_investment = starting_cash

_, odf_check = mt2.get_opening_orders(mt5_symbol, latest_weights)
folder_name_criteria = ['daily_allocation', 'daily_portfolio']
mt2.delete_folders_if_df_empty(odf_check, folder_name_criteria)
if not odf_check.empty:
    current_portfolio_value = odf_check.value.sum()

previous_allocation_df = mt2.get_folder(folder_name='daily_allocation')
previous_portfolio_df = mt2.get_folder(folder_name='daily_portfolio')

if previous_allocation_df is not None and previous_portfolio_df is not None:
    prev_holding = previous_allocation_df['Holding Units']
    prev_entry = previous_allocation_df['Entry Units']
    prev_exit = previous_allocation_df['Exit Units']
    total_investment = abs(previous_portfolio_df['Cash Balance'].iloc[-1] + current_portfolio_value)
    print(f'total_investment: {total_investment}')
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
# LIMIT

async def execute_and_check_trades(allocation_df, sleep_time): 
    order_ids = mt2.execute_trades_from_data(allocation_df)
    await asyncio.sleep(sleep_time)
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
############## testing only
current_time = datetime.datetime.now()
# Filter for orders done in the last 5 minutes
five_minutes_ago = current_time - datetime.timedelta(minutes=recent_filled_time)#minutes
recent_filled_orders = filled_orders[pd.to_datetime(filled_orders['time_done']) >= five_minutes_ago]
print(f'recent_filled_orders: {recent_filled_orders}')
print(f'opening_orders: {opening_orders}')
############## testing only
if not opening_orders.empty:
    print("Opening orders found.")
else:
    print("No opening orders found.")

log_df = mt2.create_daily_log(recent_filled_orders, opening_orders,starting_cash=starting_cash) #recent_filled_orders to filled_orders
start_time = datetime.time(9, 00)
end_time = datetime.time(16, 40) #16:40
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
mt2.save_df_to_csv(log_df, 
                   folder_name='kkyao1/daily_portfolio', 
                   file_name='balance',
                   append=True)
mt2.save_df_to_csv(allocation_df,
                     folder_name='kkyao1/daily_allocation', 
                     file_name='allocation')
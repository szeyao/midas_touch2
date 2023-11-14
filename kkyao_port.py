import midas_touch2 as mt2
import MetaTrader5 as mt5
import json
import pandas as pd
import warnings
import asyncio
import os
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

async def execute_and_check_trades(allocation_df, time):
    order_ids = mt2.execute_trades_from_data(allocation_df)
    await asyncio.sleep(time)  # Asynchronous sleep
    orders_list = [mt2.check_order_status(order_id) for order_id in order_ids]
    deleted_volumes = mt2.delete_orders(orders_list)
    return orders_list, deleted_volumes
orders_list, deleted_volumes = asyncio.run(execute_and_check_trades(allocation_df, sleep_time))

for order in deleted_volumes:
    symbol = order['symbol']
    volume_filled = order['volume_filled']
    if order['direction'] == mt5.ORDER_TYPE_BUY_LIMIT:
        allocation_df.loc[allocation_df['Share Symbol'] == symbol, 'Entry Units'] = volume_filled
    else: 
        allocation_df.loc[allocation_df['Share Symbol'] == symbol, 'Exit Units'] = volume_filled

entry_unit = allocation_df['Entry Units']
exit_unit = allocation_df['Exit Units']
share_price = allocation_df['Share Price']
allocated_unit = allocation_df['Allocated Units']
if previous_allocation_df is not None and previous_portfolio_df is not None: #2nd run onwards
    starting_cash = previous_portfolio_df['Cash Value'].iloc[-1]
    current_share_value = ((entry_unit*share_price)-(exit_unit*share_price)).sum()
    current_share_value += previous_portfolio_df['Portfolio Value'].iloc[-1]
else: #first run
    starting_cash = total_investment
    current_share_value = (entry_unit*share_price).sum()

portfolio_df = mt2.compile_portfolio_data(allocation_df, starting_cash, current_share_value)

mt2.save_df_to_csv(portfolio_df, 
                   folder_name='daily_portfolio', 
                   file_name='balance',
                   append=True)
mt2.save_df_to_csv(allocation_df, 
                   folder_name='daily_allocation', 
                   file_name='allocation')
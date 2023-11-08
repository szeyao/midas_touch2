import os
import midas_touch2 as mt2
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import warnings
import asyncio
import time
warnings.filterwarnings('ignore')

if not mt5.initialize():
    print("initialize() failed")
else:
    print("MT5 successfully initialised.\n")

symbols = ['AXREIT', 'MAXIS', 'ABMB', 'LYSAGHT', 'HARBOUR', 
        'DIALOG', 'SHL', 'YOCB', 'VSTECS', 'GASMSIA', 
        'AHEALTH', 'SWKPLNT', 'IJM']

price_df = mt2.download_stocks(symbols)
weights_df, latest_weights = mt2.run_portfolio(price_df)

#check folder
previous_allocation_df = mt2.get_folder(folder_name='daily_allocation')
previous_portfolio_df = mt2.get_folder(folder_name='daily_portfolio')
if previous_allocation_df is not None and previous_portfolio_df is not None:
    # Process the existing CSV data
    total_investment = abs(previous_portfolio_df['Total Value'].iloc[-1])
    allocation_df = mt2.calculate_stock_allocation(total_investment, latest_weights, price_df)
    allocation_df['Holding Units'] = previous_allocation_df['Allocated Units']

else: #first run
    total_investment = 100000 #TRY 15K 10K 5K
    allocation_df = mt2.calculate_stock_allocation(total_investment, latest_weights, price_df)
    # Handle the initial run scenario
    print("This is the initial run. No previous allocation data available.")
    allocation_df['Holding Units'] = 0

# Calculate Entry and Exit Units
allocation_df['Entry Units'] = allocation_df.apply(
    lambda row: max(row['Allocated Units'] - row['Holding Units'], 0), axis=1
)
allocation_df['Exit Units'] = allocation_df.apply(
    lambda row: max(row['Holding Units'] - row['Allocated Units'], 0), axis=1
)
numeric_cols = allocation_df.select_dtypes(include=['number']).astype(float)

for col in numeric_cols.columns:
    allocation_df[col] = numeric_cols[col]

#async start here
async def execute_and_monitor(allocation_df, timeout=60):
    print(allocation_df)
    order_ids = mt2.execute_trades_from_data(allocation_df)
    print(f'Waiting for {timeout/60} minutes..')
    await asyncio.sleep(timeout)
    orders_list = [mt2.check_order_status(order_id) for order_id in order_ids] 
    print(f'orders_list: {orders_list}')
    resubmitted_orders = mt2.delete_and_resubmit_orders(orders_list) 
    print(f'resubmitted_orders: {resubmitted_orders}')
    return orders_list, resubmitted_orders  
orders_list, resubmitted_orders = asyncio.run(execute_and_monitor(allocation_df, timeout=90))

for order in resubmitted_orders:
    symbol = order['symbol']
    price = order['price'] 
    allocation_df.loc[allocation_df['Share Symbol'] == symbol, 'Share Price'] = price
allocation_df
import MetaTrader5 as mt5
import pandas as pd
import time
import datetime
import os
import json
import stock_mapping as sm

current_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_path)
config_file_name = 'config.json'
config_file_path = os.path.join(current_dir, config_file_name)
with open(config_file_path, 'r') as config_file:
        config = json.load(config_file)



def main():
    start_time = datetime.time(9, 30)  # 9:30 AM
    end_time = datetime.time(16, 30)   # 4:30 PM

    while True:
        current_time = datetime.datetime.now().time()
        if start_time <= current_time <= end_time:
            if not mt5.initialize():
                    print("initialize() failed, error code =", mt5.last_error())
                    quit()

            stock_symbols = mt5_symbol
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

            if all_positions:
                df = pd.DataFrame(all_positions, columns=all_positions[0]._asdict().keys())
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df = df.drop(['time_msc','time_update', 'time_update_msc', 'identifier', 'reason', 
                            'sl', 'tp', 'swap', 'comment', 'external_id'], axis=1)
                df['today_open'] = df['symbol'].map(open_prices)
                df['today_change'] = (df['price_current'] / df['today_open']) - 1
                df['position_change'] = (df['price_current'] / df['price_open']) - 1
                df['value'] = df['volume'] * df['price_open']
                df['weights'] = df['value'] / 
                df['portfolio_change_position'] = df['weights'] * df['position_change']
                df['portfolio_change_today'] = df['weights'] * df['today_change']
                print(df)
            else:
                print("No open positions for any of the specified symbols.")

            total_portfolio_change_position = df['portfolio_change_position'].sum()
            total_portfolio_change_today = df['portfolio_change_today'].sum()
            print(f"Total portfolio change position: {total_portfolio_change_position:.4%}")
            print(f"Total portfolio change today: {total_portfolio_change_today:.4%}")
            mt5.shutdown()

            today_return = max(total_portfolio_change_position, total_portfolio_change_today)
            #today_return = 0.01
            tp_sl = VaR
            print(f"VaR: {VaR:.4%}")
            if today_return <= -tp_sl:
                print("Stop loss!!!")
            elif today_return >= tp_sl:
                print("Take profit!!!")
            else:
                print("Portfolio within risk limits.")
            time.sleep(5)  # Wait for 5 seconds
        else:
            print("Outside monitoring hours.")
            break  # Exit the loop if the time is outside monitoring hours

if __name__ == "__main__":
    main()

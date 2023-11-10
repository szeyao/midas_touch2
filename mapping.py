import pandas as pd
file_path = r'C:\Users\jeffnsy\Desktop\Python codes\midas_touch2\stock_mapping.xlsx'


def load_data(file_path):
    df = pd.read_excel(file_path, index_col=0)
    df.dropna(inplace=True)
    df.set_index('No', inplace=True)
    symbol_map = dict(zip(df[" Yahoo Finance Symbol"].str.strip(), df["MT5 Symbol"]))
    return symbol_map

def map_symbols_df(yahoo_symbols, symbol_map):
    return [symbol_map[symbol] for symbol in yahoo_symbols if symbol in symbol_map]

    
    symbol_map = load_data(file_path)
    test_input = ['1007.KL', '1015.KL']
    mapped_symbols = map_symbols_df(test_input, symbol_map)
    print(mapped_symbols)
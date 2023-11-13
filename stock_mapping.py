import pandas as pd
def load_data(file_path):
    df = pd.read_excel(file_path, index_col=0)
    df.dropna(inplace=True)
    #df.set_index('No', inplace=True)
    symbol_map = dict(zip(df[" Yahoo Finance Symbol"].str.strip(), df["MT5 Symbol"]))
    return symbol_map

def find_opposite(input_list, symbol_map):
    results = []
    for item in input_list:
        if item in symbol_map:
            results.append(symbol_map[item])  
        else:
            for symbol, name in symbol_map.items():
                if name == item:
                    results.append(symbol)  
                    break  
            else:
                results.append("Not Found")
    return results

def get_ticker_list(input_symbols, file_path):
    symbol_map = load_data(file_path)
    output = find_opposite(input_symbols, symbol_map)
    return output




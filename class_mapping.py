import pandas as pd
class StockSymbolMapper:
    def __init__(self, file_path):
        self.file_path = file_path
        self.symbol_map = self.load_data()

    def load_data(self):
        df = pd.read_excel(self.file_path, index_col=0)
        df.dropna(inplace=True)
        df.set_index('No', inplace=True)
        symbol_map = dict(zip(df[" Yahoo Finance Symbol"].str.strip(), df["MT5 Symbol"]))
        return symbol_map

    def find_opposite(self, input_list):
        results = []
        for item in input_list:
            if item in self.symbol_map:
                results.append(self.symbol_map[item])
            else:
                for symbol, name in self.symbol_map.items():
                    if name == item:
                        results.append(symbol)
                        break
                else:
                    results.append("Not Found")
        return results
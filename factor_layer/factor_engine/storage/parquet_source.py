from dataclasses import dataclass

from .datasource import DataSource


@dataclass
class ParquetSource(DataSource):
    path: str
    timestamp_col: str = "timestamp"
    instrument_col: str = "instrument"

    def load_column(self, name: str):
        import pandas as pd

        cols = [self.timestamp_col, self.instrument_col, name]
        df = pd.read_parquet(self.path, columns=cols)
        return df.set_index([self.timestamp_col, self.instrument_col])[name]

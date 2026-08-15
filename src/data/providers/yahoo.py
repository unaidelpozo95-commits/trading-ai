import yfinance as yf
import pandas as pd


class YahooProvider:
    def get_daily(
        self,
        ticker: str,
        start: str,
        end: str | None = None,
    ) -> pd.DataFrame:

        data = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
        )

        if data.empty:
            raise ValueError(f"No data received for {ticker}")

        # Flatten yfinance MultiIndex columns
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            data.columns.name = None

        # Standard column order
        columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Adj Close",
            "Volume",
        ]

        data = data[columns]

        # Remove rows with missing OHLCV data
        data = data.dropna(subset=[
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ])

        # Ensure chronological order
        data = data.sort_index()

        return data

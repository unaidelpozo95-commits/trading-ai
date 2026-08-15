from dataclasses import dataclass
import pandas as pd


REQUIRED_COLUMNS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
]


@dataclass
class ValidationReport:
    ticker: str
    rows: int
    duplicate_dates: int
    chronological: bool
    missing_values: int
    invalid_prices: int
    invalid_ohlc: int
    invalid_volume: int

    @property
    def is_valid(self) -> bool:
        return (
            self.duplicate_dates == 0
            and self.chronological
            and self.missing_values == 0
            and self.invalid_prices == 0
            and self.invalid_ohlc == 0
            and self.invalid_volume == 0
        )

    def print(self) -> None:
        print(f"DATA QUALITY REPORT")
        print("-" * 40)
        print(f"Ticker: {self.ticker}")
        print(f"Rows:   {self.rows}")
        print()

        self._result(
            "No duplicate dates",
            self.duplicate_dates == 0,
            f"{self.duplicate_dates} duplicates",
        )

        self._result(
            "Chronological order",
            self.chronological,
            "Dates are not ordered",
        )

        self._result(
            "No missing values",
            self.missing_values == 0,
            f"{self.missing_values} missing values",
        )

        self._result(
            "Valid prices",
            self.invalid_prices == 0,
            f"{self.invalid_prices} invalid values",
        )

        self._result(
            "OHLC consistency",
            self.invalid_ohlc == 0,
            f"{self.invalid_ohlc} invalid rows",
        )

        self._result(
            "Valid volume",
            self.invalid_volume == 0,
            f"{self.invalid_volume} invalid values",
        )

        print()
        print("Overall:", "VALID" if self.is_valid else "INVALID")

    @staticmethod
    def _result(name: str, valid: bool, detail: str) -> None:
        if valid:
            print(f"✓ {name}")
        else:
            print(f"✗ {name} ({detail})")


class DataValidator:

    def validate(
        self,
        data: pd.DataFrame,
        ticker: str = "UNKNOWN",
    ) -> ValidationReport:

        missing_columns = [
            column for column in REQUIRED_COLUMNS
            if column not in data.columns
        ]

        if missing_columns:
            raise ValueError(
                f"Missing required columns: {missing_columns}"
            )

        duplicate_dates = int(data.index.duplicated().sum())

        chronological = data.index.is_monotonic_increasing

        missing_values = int(
            data[REQUIRED_COLUMNS].isna().sum().sum()
        )

        price_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Adj Close",
        ]

        invalid_prices = int(
            (data[price_columns] <= 0).sum().sum()
        )

        invalid_ohlc = int(
            (
                (data["High"] < data["Low"])
                | (data["High"] < data["Open"])
                | (data["High"] < data["Close"])
                | (data["Low"] > data["Open"])
                | (data["Low"] > data["Close"])
            ).sum()
        )

        invalid_volume = int(
            (data["Volume"] < 0).sum()
        )

        return ValidationReport(
            ticker=ticker,
            rows=len(data),
            duplicate_dates=duplicate_dates,
            chronological=chronological,
            missing_values=missing_values,
            invalid_prices=invalid_prices,
            invalid_ohlc=invalid_ohlc,
            invalid_volume=invalid_volume,
        )
@dataclass
class Anomaly:
    date: pd.Timestamp
    kind: str
    description: str


class AnomalyDetector:

    def __init__(
        self,
        price_change_threshold: float = 0.15,
        volume_ratio_threshold: float = 5.0,
    ):
        self.price_change_threshold = price_change_threshold
        self.volume_ratio_threshold = volume_ratio_threshold

    def detect(
        self,
        data: pd.DataFrame,
    ) -> list[Anomaly]:

        anomalies = []

        # Daily percentage change
        returns = data["Close"].pct_change()

        # 20-day average volume
        average_volume = (
            data["Volume"]
            .rolling(20)
            .mean()
            .shift(1)
        )

        for date in data.index:

            # Large daily price movement
            if pd.notna(returns.loc[date]):
                change = returns.loc[date]

                if abs(change) >= self.price_change_threshold:
                    anomalies.append(
                        Anomaly(
                            date=date,
                            kind="PRICE_MOVE",
                            description=(
                                f"Daily close change: "
                                f"{change:.2%}"
                            ),
                        )
                    )

            # Exceptional volume
            if (
                pd.notna(average_volume.loc[date])
                and average_volume.loc[date] > 0
            ):
                volume_ratio = (
                    data.loc[date, "Volume"]
                    / average_volume.loc[date]
                )

                if volume_ratio >= self.volume_ratio_threshold:
                    anomalies.append(
                        Anomaly(
                            date=date,
                            kind="VOLUME",
                            description=(
                                f"Volume is "
                                f"{volume_ratio:.1f}x "
                                f"20-day average"
                            ),
                        )
                    )

        return anomalies

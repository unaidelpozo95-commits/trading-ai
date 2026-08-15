import pandas as pd


class FeatureEngine:

    def build(self, data: pd.DataFrame) -> pd.DataFrame:

        df = data.copy()

        # -------------------------------------------------
        # RETURNS
        # -------------------------------------------------

        df["return_1d"] = df["Close"].pct_change()

        df["return_5d"] = (
            df["Close"].pct_change(5)
        )

        df["return_20d"] = (
            df["Close"].pct_change(20)
        )

        # -------------------------------------------------
        # RELATIVE VOLUME
        # -------------------------------------------------

        volume_mean_20 = (
            df["Volume"]
            .rolling(20)
            .mean()
            .shift(1)
        )

        df["rvol_20"] = (
            df["Volume"] / volume_mean_20
        )

        # -------------------------------------------------
        # SIMPLE MOVING AVERAGES
        # -------------------------------------------------

        df["sma_20"] = (
            df["Close"]
            .rolling(20)
            .mean()
        )

        df["sma_50"] = (
            df["Close"]
            .rolling(50)
            .mean()
        )

        df["sma_200"] = (
            df["Close"]
            .rolling(200)
            .mean()
        )

        # -------------------------------------------------
        # DISTANCE FROM MOVING AVERAGES
        # -------------------------------------------------

        df["distance_sma_20"] = (
            df["Close"] / df["sma_20"] - 1
        )

        df["distance_sma_200"] = (
            df["Close"] / df["sma_200"] - 1
        )

        # -------------------------------------------------
        # TRUE RANGE
        # -------------------------------------------------

        previous_close = df["Close"].shift(1)

        true_range = pd.concat(
            [
                df["High"] - df["Low"],
                (df["High"] - previous_close).abs(),
                (df["Low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        df["true_range"] = true_range

        # -------------------------------------------------
        # ATR 14
        # -------------------------------------------------

        df["atr_14"] = (
            true_range
            .rolling(14)
            .mean()
        )

        df["atr_pct"] = (
            df["atr_14"] / df["Close"]
        )

        # -------------------------------------------------
        # VOLATILITY
        # -------------------------------------------------

        df["volatility_20"] = (
            df["return_1d"]
            .rolling(20)
            .std()
        )

        # -------------------------------------------------
        # 20-DAY HIGH / LOW
        # -------------------------------------------------

        df["high_20"] = (
            df["High"]
            .rolling(20)
            .max()
            .shift(1)
        )

        df["low_20"] = (
            df["Low"]
            .rolling(20)
            .min()
            .shift(1)
        )

        # -------------------------------------------------
        # BREAKOUT DISTANCE
        # -------------------------------------------------

        df["distance_high_20"] = (
            df["Close"] / df["high_20"] - 1
        )

        df["distance_low_20"] = (
            df["Close"] / df["low_20"] - 1
        )

        return df

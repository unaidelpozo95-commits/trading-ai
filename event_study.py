import pandas as pd

from src.features.engine import FeatureEngine


data = pd.read_parquet(
    "data/raw/yahoo/AAPL.parquet"
)

engine = FeatureEngine()

df = engine.build(data)


# -------------------------------------------------
# FORWARD RETURNS
#
# Signal is generated at Close[D]
# Entry is Open[D+1]
# Exit is Open[D+1+N]
# -------------------------------------------------

for days in [1, 3, 5, 10, 20]:

    entry = df["Open"].shift(-1)
    exit_price = df["Open"].shift(-(days + 1))

    df[f"forward_{days}d"] = (
        exit_price / entry - 1
    )


# -------------------------------------------------
# STATISTICS
# -------------------------------------------------

def print_statistics(returns: pd.Series):

    returns = returns.dropna()

    if len(returns) == 0:
        return

    print(f"Mean:      {returns.mean():>8.2%}")
    print(f"Median:    {returns.median():>8.2%}")
    print(f"Std:       {returns.std():>8.2%}")
    print(f"Win rate:  {(returns > 0).mean():>8.1%}")
    print(f"25th pct:  {returns.quantile(0.25):>8.2%}")
    print(f"75th pct:  {returns.quantile(0.75):>8.2%}")
    print(f"Worst:     {returns.min():>8.2%}")
    print(f"Best:      {returns.max():>8.2%}")
    print(f"N:         {len(returns)}")


# -------------------------------------------------
# EVENT STUDY
# -------------------------------------------------

# -------------------------------------------------
# BASELINE
# -------------------------------------------------

print()
print("=" * 60)
print("UNCONDITIONAL AAPL BASELINE")
print("=" * 60)

for days in [1, 3, 5, 10, 20]:

    returns = df[
        f"forward_{days}d"
    ].dropna()

    print()
    print(f"--- {days} trading days ---")

    print_statistics(returns)


thresholds = [2, 3, 5]


# -------------------------------------------------
# TREND REGIME
# -------------------------------------------------

df["above_sma200"] = (
    df["Close"] > df["sma_200"]
)

for threshold in thresholds:

    events = df[
        df["rvol_20"] >= threshold
    ].copy()

    print()
    print("=" * 60)
    print(f"RVOL >= {threshold}")
    print("=" * 60)

    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ]

        if returns.dropna().empty:
            continue

        print()
        print(f"--- {days} trading days ---")

        print_statistics(returns)


# -------------------------------------------------
# RVOL + TREND STUDY
# -------------------------------------------------

print()
print("=" * 60)
print("RVOL + SMA200")
print("=" * 60)

conditions = {
    "RVOL >= 2": (
        df["rvol_20"] >= 2
    ),

    "RVOL >= 2 + Above SMA200": (
        (df["rvol_20"] >= 2)
        & (df["above_sma200"])
    ),

    "RVOL >= 2 + Below SMA200": (
        (df["rvol_20"] >= 2)
        & (~df["above_sma200"])
    ),
}


for name, condition in conditions.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# RVOL x TREND MATRIX
# -------------------------------------------------

print()
print("=" * 60)
print("RVOL x SMA200 MATRIX")
print("=" * 60)

groups = {
    "RVOL < 2 + Above SMA200": (
        (df["rvol_20"] < 2)
        & (df["above_sma200"])
    ),

    "RVOL >= 2 + Above SMA200": (
        (df["rvol_20"] >= 2)
        & (df["above_sma200"])
    ),

    "RVOL < 2 + Below SMA200": (
        (df["rvol_20"] < 2)
        & (~df["above_sma200"])
    ),

    "RVOL >= 2 + Below SMA200": (
        (df["rvol_20"] >= 2)
        & (~df["above_sma200"])
    ),
}


for name, condition in groups.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# RVOL + PRICE ACTION
# -------------------------------------------------

print()
print("=" * 60)
print("RVOL x PRICE ACTION")
print("=" * 60)

groups = {
    "RVOL >= 2 + Strong Up Day": (
        (df["rvol_20"] >= 2)
        & (df["return_1d"] >= 0.02)
    ),

    "RVOL >= 2 + Neutral Day": (
        (df["rvol_20"] >= 2)
        & (df["return_1d"] > -0.02)
        & (df["return_1d"] < 0.02)
    ),

    "RVOL >= 2 + Strong Down Day": (
        (df["rvol_20"] >= 2)
        & (df["return_1d"] <= -0.02)
    ),
}


for name, condition in groups.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# PRICE ACTION x RVOL CONTROL
# -------------------------------------------------

print()
print("=" * 60)
print("PRICE ACTION x RVOL CONTROL")
print("=" * 60)

groups = {
    "Up >= 2% + RVOL < 2": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] < 2)
    ),

    "Up >= 2% + RVOL >= 2": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] >= 2)
    ),

    "Neutral + RVOL < 2": (
        (df["return_1d"] > -0.02)
        & (df["return_1d"] < 0.02)
        & (df["rvol_20"] < 2)
    ),

    "Neutral + RVOL >= 2": (
        (df["return_1d"] > -0.02)
        & (df["return_1d"] < 0.02)
        & (df["rvol_20"] >= 2)
    ),

    "Down <= -2% + RVOL < 2": (
        (df["return_1d"] <= -0.02)
        & (df["rvol_20"] < 2)
    ),

    "Down <= -2% + RVOL >= 2": (
        (df["return_1d"] <= -0.02)
        & (df["rvol_20"] >= 2)
    ),
}


for name, condition in groups.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# PRICE ACTION + RVOL + SMA200
# -------------------------------------------------

print()
print("=" * 60)
print("PRICE ACTION + RVOL + SMA200")
print("=" * 60)

groups = {
    "Up >= 2% + RVOL >= 2 + Above SMA200": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] >= 2)
        & (df["above_sma200"])
    ),

    "Up >= 2% + RVOL >= 2 + Below SMA200": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] >= 2)
        & (~df["above_sma200"])
    ),

    "Up >= 2% + RVOL < 2 + Above SMA200": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] < 2)
        & (df["above_sma200"])
    ),

    "Up >= 2% + RVOL < 2 + Below SMA200": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] < 2)
        & (~df["above_sma200"])
    ),
}


for name, condition in groups.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# RVOL + PRICE ACTION + 20D RANGE
# -------------------------------------------------

print()
print("=" * 60)
print("RVOL + PRICE ACTION + 20D RANGE")
print("=" * 60)

# Distance to 20d high/low
#
# distance_high_20:
#   0.00  -> at 20d high
#  -0.05  -> 5% below 20d high
#
# distance_low_20:
#   0.00  -> at 20d low
#   0.05  -> 5% above 20d low


groups = {

    "Strong Up + RVOL >= 2 + Near 20d High": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] >= 2)
        & (df["distance_high_20"] >= -0.05)
    ),

    "Strong Up + RVOL >= 2 + Away from 20d High": (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] >= 2)
        & (df["distance_high_20"] < -0.05)
    ),

    "Strong Down + RVOL >= 2 + Near 20d Low": (
        (df["return_1d"] <= -0.02)
        & (df["rvol_20"] >= 2)
        & (df["distance_low_20"] <= 0.05)
    ),

    "Strong Down + RVOL >= 2 + Away from 20d Low": (
        (df["return_1d"] <= -0.02)
        & (df["rvol_20"] >= 2)
        & (df["distance_low_20"] > 0.05)
    ),
}


for name, condition in groups.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# STRONG UP + RVOL + DISTANCE TO 20D HIGH
# -------------------------------------------------

print()
print("=" * 60)
print("STRONG UP + RVOL + DISTANCE TO 20D HIGH")
print("=" * 60)


groups = {

    "Up 2-3% + RVOL 2-3 + Near High 0-1%": (
        (df["return_1d"] >= 0.02)
        & (df["return_1d"] < 0.03)
        & (df["rvol_20"] >= 2)
        & (df["rvol_20"] < 3)
        & (df["distance_high_20"] >= -0.01)
    ),

    "Up 2-3% + RVOL 2-3 + Near High 1-3%": (
        (df["return_1d"] >= 0.02)
        & (df["return_1d"] < 0.03)
        & (df["rvol_20"] >= 2)
        & (df["rvol_20"] < 3)
        & (df["distance_high_20"] < -0.01)
        & (df["distance_high_20"] >= -0.03)
    ),

    "Up 3-5% + RVOL 2-3 + Near High 0-1%": (
        (df["return_1d"] >= 0.03)
        & (df["return_1d"] < 0.05)
        & (df["rvol_20"] >= 2)
        & (df["rvol_20"] < 3)
        & (df["distance_high_20"] >= -0.01)
    ),

    "Up 3-5% + RVOL 2-3 + Near High 1-3%": (
        (df["return_1d"] >= 0.03)
        & (df["return_1d"] < 0.05)
        & (df["rvol_20"] >= 2)
        & (df["rvol_20"] < 3)
        & (df["distance_high_20"] < -0.01)
        & (df["distance_high_20"] >= -0.03)
    ),

    "Up 2-5% + RVOL 3+ + Near High 0-3%": (
        (df["return_1d"] >= 0.02)
        & (df["return_1d"] < 0.05)
        & (df["rvol_20"] >= 3)
        & (df["distance_high_20"] >= -0.03)
    ),
}


for name, condition in groups.items():

    events = df[condition]

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:
            continue

        print(
            f"{days:>2}d | "
            f"Mean: {returns.mean():>7.2%} | "
            f"Median: {returns.median():>7.2%} | "
            f"Win: {(returns > 0).mean():>6.1%} | "
            f"N: {len(returns)}"
        )


# -------------------------------------------------
# MAE / MFE STUDY
# -------------------------------------------------

print()
print("=" * 60)
print("MAE / MFE STUDY")
print("=" * 60)


def mae_mfe_study(events, name):

    print()
    print("-" * 60)
    print(name)
    print(f"Events: {len(events)}")

    for days in [1, 3, 5, 10, 20]:

        results = []

        for idx in events.index:

            try:
                # Entry at Open[D+1]
                entry_price = df["Open"].shift(-1).loc[idx]

                if pd.isna(entry_price):
                    continue

                # Future candles: D+1 ... D+N
                future = df.loc[idx:].iloc[1:days + 1]

                if len(future) < days:
                    continue

                future_high = future["High"].max()
                future_low = future["Low"].min()

                mfe = future_high / entry_price - 1
                mae = future_low / entry_price - 1

                # Exit at Open[D+N]
                exit_price = future["Open"].iloc[-1]

                final_return = exit_price / entry_price - 1

                results.append({
                    "return": final_return,
                    "mfe": mfe,
                    "mae": mae,
                })

            except Exception:
                continue

        if not results:
            continue

        result = pd.DataFrame(results)

        print()
        print(f"--- {days} trading days ---")
        print(f"Final return mean:   {result['return'].mean():>7.2%}")
        print(f"Final return median: {result['return'].median():>7.2%}")

        print(f"MFE mean:            {result['mfe'].mean():>7.2%}")
        print(f"MFE median:          {result['mfe'].median():>7.2%}")
        print(f"MFE 75th pct:        {result['mfe'].quantile(.75):>7.2%}")

        print(f"MAE mean:            {result['mae'].mean():>7.2%}")
        print(f"MAE median:          {result['mae'].median():>7.2%}")
        print(f"MAE 25th pct:        {result['mae'].quantile(.25):>7.2%}")

        print(f"Hit +1%:             {(result['mfe'] >= .01).mean():>7.1%}")
        print(f"Hit +2%:             {(result['mfe'] >= .02).mean():>7.1%}")
        print(f"Hit +5%:             {(result['mfe'] >= .05).mean():>7.1%}")
        print(f"Hit +10%:            {(result['mfe'] >= .10).mean():>7.1%}")

        print(f"Hit -1%:             {(result['mae'] <= -.01).mean():>7.1%}")
        print(f"Hit -2%:             {(result['mae'] <= -.02).mean():>7.1%}")
        print(f"Hit -5%:             {(result['mae'] <= -.05).mean():>7.1%}")


# -------------------------------------------------
# SIGNALS
# -------------------------------------------------

strong_up = df["return_1d"] >= 0.02
high_rvol = df["rvol_20"] >= 2

near_20d_high = (
    df["distance_high_20"] >= -0.05
)

signal = (
    strong_up
    & high_rvol
    & near_20d_high
)

control = (
    strong_up
    & (df["rvol_20"] < 2)
)


mae_mfe_study(
    df[signal],
    "Strong Up + RVOL >= 2 + Near 20d High"
)

mae_mfe_study(
    df[control],
    "Up >= 2% + RVOL < 2"
)


# -------------------------------------------------
# FIXED STOP / TAKE PROFIT STUDY
# -------------------------------------------------

print()
print("=" * 60)
print("FIXED STOP / TAKE PROFIT STUDY")
print("=" * 60)


def stop_tp_study(events, stop_pct, target_pct, max_days=20):

    results = []

    for idx in events.index:

        # Signal generated at Close[D]
        # Entry at Open[D+1]
        entry_price = df["Open"].shift(-1).loc[idx]

        if pd.isna(entry_price):
            continue

        # Future candles: D+1 ... D+max_days
        future = df.loc[idx:].iloc[1:max_days + 1]

        if len(future) == 0:
            continue

        stop_price = entry_price * (1 - stop_pct)
        target_price = entry_price * (1 + target_pct)

        outcome = None
        exit_return = None
        exit_day = None

        for day_number, (_, row) in enumerate(
            future.iterrows(),
            start=1
        ):

            hit_stop = row["Low"] <= stop_price
            hit_target = row["High"] >= target_price

            # Both touched on same daily candle:
            # OHLC data cannot determine which happened first.
            if hit_stop and hit_target:
                outcome = "AMBIGUOUS"
                exit_return = None
                exit_day = day_number
                break

            if hit_target:
                outcome = "TP"
                exit_return = target_pct
                exit_day = day_number
                break

            if hit_stop:
                outcome = "SL"
                exit_return = -stop_pct
                exit_day = day_number
                break

        # Neither SL nor TP was hit
        if outcome is None:

            # Exit at Open[D+N]
            exit_price = future["Open"].iloc[-1]

            exit_return = exit_price / entry_price - 1

            outcome = "TIME"
            exit_day = len(future)

        results.append({
            "return": exit_return,
            "outcome": outcome,
            "exit_day": exit_day,
        })

    result = pd.DataFrame(results)

    clean = result[
        result["outcome"] != "AMBIGUOUS"
    ].dropna(subset=["return"])

    if clean.empty:
        return None

    return {
        "n": len(clean),

        "ambiguous": (
            result["outcome"] == "AMBIGUOUS"
        ).sum(),

        "mean": clean["return"].mean(),

        "median": clean["return"].median(),

        "win_rate": (
            clean["return"] > 0
        ).mean(),

        "expectancy": clean["return"].mean(),

        "tp_rate": (
            clean["outcome"] == "TP"
        ).mean(),

        "sl_rate": (
            clean["outcome"] == "SL"
        ).mean(),

        "time_rate": (
            clean["outcome"] == "TIME"
        ).mean(),

        "avg_exit_day": clean["exit_day"].mean(),
    }


stops = [
    0.01,
    0.015,
    0.02,
    0.025,
    0.03,
    0.04,
]


targets = [
    0.02,
    0.03,
    0.04,
    0.05,
    0.07,
    0.10,
]


events = df[signal]


for stop in stops:

    print()
    print("=" * 60)
    print(f"STOP = {stop:.1%}")
    print("=" * 60)

    for target in targets:

        stats = stop_tp_study(
            events,
            stop,
            target,
            max_days=20,
        )

        if stats is None:
            continue

        print(
            f"SL {stop:>5.1%} | "
            f"TP {target:>5.1%} | "
            f"Mean {stats['mean']:>7.2%} | "
            f"Win {stats['win_rate']:>6.1%} | "
            f"TP {stats['tp_rate']:>6.1%} | "
            f"SL {stats['sl_rate']:>6.1%} | "
            f"Time {stats['time_rate']:>6.1%} | "
            f"Amb {stats['ambiguous']:>2} | "
            f"Avg days {stats['avg_exit_day']:>5.1f}"
        )

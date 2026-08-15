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

import pandas as pd

from src.features.engine import FeatureEngine


# =============================================================
# LOAD DATA
# =============================================================

data = pd.read_parquet(
    "data/raw/yahoo/AAPL.parquet"
)

engine = FeatureEngine()

df = engine.build(data)

if not isinstance(df.index, pd.DatetimeIndex):
    df.index = pd.to_datetime(df.index)


# =============================================================
# FORWARD RETURNS
# =============================================================

for days in [1, 3, 5, 10, 20]:

    entry = df["Open"].shift(-1)
    exit_price = df["Open"].shift(-(days + 1))

    df[f"forward_{days}d"] = (
        exit_price / entry - 1
    )


# =============================================================
# PERIODS
# =============================================================

development = df.index.year <= 2022
test = df.index.year >= 2023


# =============================================================
# PARAMETERS TO TEST
# =============================================================

move_thresholds = [
    0.015,
    0.020,
    0.025,
    0.030,
]

rvol_thresholds = [
    1.5,
    2.0,
    2.5,
    3.0,
]

distance_thresholds = [
    0.01,
    0.03,
    0.05,
    0.075,
    0.10,
]


# =============================================================
# FUNCTION
# =============================================================

def evaluate_signal(
    move_threshold,
    rvol_threshold,
    distance_threshold,
    period_mask,
):

    signal = (
        (df["return_1d"] >= move_threshold)
        & (df["rvol_20"] >= rvol_threshold)
        & (
            df["distance_high_20"]
            >= -distance_threshold
        )
    )

    events = df[
        signal & period_mask
    ]

    result = {
        "events": len(events),
    }

    for days in [1, 3, 5, 10, 20]:

        returns = events[
            f"forward_{days}d"
        ].dropna()

        if returns.empty:

            result[f"mean_{days}d"] = None
            result[f"median_{days}d"] = None
            result[f"win_{days}d"] = None
            result[f"alpha_{days}d"] = None

            continue

        baseline = df.loc[
            period_mask,
            f"forward_{days}d"
        ].dropna()

        result[f"mean_{days}d"] = (
            returns.mean()
        )

        result[f"median_{days}d"] = (
            returns.median()
        )

        result[f"win_{days}d"] = (
            returns > 0
        ).mean()

        result[f"alpha_{days}d"] = (
            returns.mean()
            - baseline.mean()
        )

    return result


# =============================================================
# SENSITIVITY TEST
# =============================================================

print()
print("=" * 80)
print("ROBUSTNESS TEST 2 — PARAMETER SENSITIVITY")
print("=" * 80)


results = []


for move in move_thresholds:

    for rvol in rvol_thresholds:

        for distance in distance_thresholds:

            dev = evaluate_signal(
                move,
                rvol,
                distance,
                development,
            )

            oos = evaluate_signal(
                move,
                rvol,
                distance,
                test,
            )

            results.append({

                "move": move,
                "rvol": rvol,
                "distance": distance,

                "dev_events":
                    dev["events"],

                "oos_events":
                    oos["events"],

                "dev_mean_5d":
                    dev["mean_5d"],

                "oos_mean_5d":
                    oos["mean_5d"],

                "dev_alpha_5d":
                    dev["alpha_5d"],

                "oos_alpha_5d":
                    oos["alpha_5d"],

                "dev_win_5d":
                    dev["win_5d"],

                "oos_win_5d":
                    oos["win_5d"],

                "dev_mean_20d":
                    dev["mean_20d"],

                "oos_mean_20d":
                    oos["mean_20d"],

                "dev_alpha_20d":
                    dev["alpha_20d"],

                "oos_alpha_20d":
                    oos["alpha_20d"],

                "dev_win_20d":
                    dev["win_20d"],

                "oos_win_20d":
                    oos["win_20d"],

            })


results_df = pd.DataFrame(results)


# =============================================================
# SAVE RESULTS
# =============================================================

results_df.to_csv(
    "data/robustness_sensitivity.csv",
    index=False,
)


# =============================================================
# DEVELOPMENT RESULTS
# =============================================================

print()
print("=" * 80)
print("DEVELOPMENT — 2015 TO 2022")
print("=" * 80)

dev_sorted = results_df.sort_values(
    "dev_alpha_20d",
    ascending=False,
)

for _, row in dev_sorted.head(15).iterrows():

    print(
        f"Move {row['move']:>5.1%} | "
        f"RVOL {row['rvol']:>3.1f} | "
        f"High {row['distance']:>5.1%} | "
        f"N {int(row['dev_events']):>3} | "
        f"5d {row['dev_mean_5d']:>7.2%} | "
        f"20d {row['dev_mean_20d']:>7.2%} | "
        f"20d alpha {row['dev_alpha_20d']:>7.2%}"
    )


# =============================================================
# OUT-OF-SAMPLE RESULTS
# =============================================================

print()
print("=" * 80)
print("OUT-OF-SAMPLE — 2023 TO 2026")
print("=" * 80)

oos_sorted = results_df.sort_values(
    "oos_alpha_20d",
    ascending=False,
)

for _, row in oos_sorted.head(15).iterrows():

    print(
        f"Move {row['move']:>5.1%} | "
        f"RVOL {row['rvol']:>3.1f} | "
        f"High {row['distance']:>5.1%} | "
        f"N {int(row['oos_events']):>3} | "
        f"5d {row['oos_mean_5d']:>7.2%} | "
        f"20d {row['oos_mean_20d']:>7.2%} | "
        f"20d alpha {row['oos_alpha_20d']:>7.2%}"
    )


# =============================================================
# ORIGINAL SIGNAL
# =============================================================

original = results_df[
    (results_df["move"] == 0.02)
    & (results_df["rvol"] == 2.0)
    & (results_df["distance"] == 0.05)
]


print()
print("=" * 80)
print("ORIGINAL SIGNAL — REFERENCE")
print("=" * 80)

print(
    original[
        [
            "move",
            "rvol",
            "distance",
            "dev_events",
            "oos_events",
            "dev_mean_5d",
            "oos_mean_5d",
            "dev_alpha_5d",
            "oos_alpha_5d",
            "dev_mean_20d",
            "oos_mean_20d",
            "dev_alpha_20d",
            "oos_alpha_20d",
            "dev_win_20d",
            "oos_win_20d",
        ]
    ].to_string(index=False)
)


# =============================================================
# ROBUST REGION
# =============================================================

print()
print("=" * 80)
print("ROBUST REGION")
print("=" * 80)

robust = results_df[
    (results_df["dev_events"] >= 10)
    & (results_df["oos_events"] >= 5)
    & (results_df["dev_alpha_20d"] > 0)
    & (results_df["oos_alpha_20d"] > 0)
]

print(
    f"Parameter combinations satisfying:"
)
print(
    f"  Development events >= 10"
)
print(
    f"  OOS events >= 5"
)
print(
    f"  Positive 20d alpha in BOTH periods"
)
print()
print(
    f"Robust combinations: {len(robust)}"
)


if not robust.empty:

    print()

    robust = robust.sort_values(
        "oos_alpha_20d",
        ascending=False,
    )

    for _, row in robust.head(20).iterrows():

        print(
            f"Move {row['move']:>5.1%} | "
            f"RVOL {row['rvol']:>3.1f} | "
            f"High {row['distance']:>5.1%} | "
            f"Dev N {int(row['dev_events']):>3} | "
            f"OOS N {int(row['oos_events']):>3} | "
            f"Dev alpha {row['dev_alpha_20d']:>7.2%} | "
            f"OOS alpha {row['oos_alpha_20d']:>7.2%}"
        )


# =============================================================
# SUMMARY
# =============================================================

print()
print("=" * 80)
print("DONE")
print("=" * 80)

print()
print(
    "Full results saved to:"
)
print(
    "data/robustness_sensitivity.csv"
)

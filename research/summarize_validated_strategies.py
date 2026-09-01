"""
Resumen de todos los tickers con estrategia validada.

Lee data/strategies/*.json (vía strategy_store.load_all_validated_strategies),
arma una tabla y la ordena por calidad — para no tener que abrir cada
JSON uno por uno.
"""

import pandas as pd

from src.research.strategy_store import load_all_validated_strategies


validated = load_all_validated_strategies()

print(f"Tickers validados: {len(validated)}")

if not validated:
    print("Ninguno todavía.")
    raise SystemExit

rows = []
for ticker, strategy in validated.items():
    rows.append({
        "ticker": ticker,
        "recipe": strategy.get("recipe"),
        "params": strategy.get("params"),
        "dev_events": strategy.get("dev_events"),
        "oos_events": strategy.get("oos_events"),
        "dev_alpha_20d": strategy.get("dev_alpha_20d"),
        "oos_alpha_20d": strategy.get("oos_alpha_20d"),
        "dev_tstat_20d": strategy.get("dev_tstat_20d"),
        "oos_tstat_20d": strategy.get("oos_tstat_20d"),
    })

df = pd.DataFrame(rows)

df["min_tstat"] = df[["dev_tstat_20d", "oos_tstat_20d"]].min(axis=1)
df = df.sort_values("min_tstat", ascending=False)

print()
print("=" * 110)
print("TICKERS VALIDADOS — ordenados por t-stat más débil de los dos (Dev/OOS)")
print("=" * 110)
print(f"{'Ticker':<8} | {'Receta':<20} | {'DevN':>5} {'DevAlpha':>9} {'DevT':>6} | "
      f"{'OOSN':>5} {'OOSAlpha':>9} {'OOST':>6}")
print("-" * 110)

for _, row in df.iterrows():
    print(
        f"{row['ticker']:<8} | {row['recipe']:<20} | "
        f"{row['dev_events']:>5} {row['dev_alpha_20d']:>8.2%} {row['dev_tstat_20d']:>6.2f} | "
        f"{row['oos_events']:>5} {row['oos_alpha_20d']:>8.2%} {row['oos_tstat_20d']:>6.2f}"
    )

print()
print("=" * 60)
print("DESGLOSE POR RECETA")
print("=" * 60)
print(df["recipe"].value_counts().to_string())

df.to_csv("data/validated_strategies_summary.csv", index=False)

print()
print("Resumen completo guardado en: data/validated_strategies_summary.csv")
print()
print("=" * 60)
print("PRÓXIMO PASO SUGERIDO")
print("=" * 60)
print(
    "Antes de confiar en estos 41, mira el desglose por receta y por\n"
    "sector: si la mayoría son 'original_breakout' o 'trend_breakout' y\n"
    "muchos son nombres de un mismo sector/tema (ej. varios de IA/tech),\n"
    "podría ser el mismo problema de concentración que vimos antes\n"
    "(AMD/NVDA/TSLA), no 41 patrones independientes de verdad."
)

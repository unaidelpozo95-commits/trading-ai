"""
Pipeline diario completo — un solo comando, pensado para cron.

Ejecuta, en orden:
  1. Actualización incremental de precios (todos los días)
  2. Refresco de fundamentales SEC — solo para tickers cuyo dato
     tenga más de FUNDAMENTALS_MAX_AGE_DAYS (por defecto 25), para no
     martillear la API de la SEC sin necesidad (el ROE solo cambia
     una vez al año por ticker)
  3. Screener de Valor + Calidad
  4. Envío del informe por email

El universo de tickers es dinámico: todo lo que haya en
data/tickers/*.csv se procesa automáticamente — añade un CSV nuevo
ahí y al día siguiente ya está incluido, sin tocar código.

Se puede dividir en dos fases (por ejemplo, cálculo la noche antes y
envío por la mañana, con dos entradas de cron distintas):

    python run_daily_pipeline.py --calculate-only   # pasos 1-3, sin email
    python run_daily_pipeline.py --send-only        # solo el paso 4

USO (pensado para cron):
    python run_daily_pipeline.py
    python run_daily_pipeline.py --top 30 --min-roe 0.15
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

from ticker_universe import load_tickers


FUNDAMENTALS_DIR = "data/sec_fundamentals"
FUNDAMENTALS_MAX_AGE_DAYS = 25


def run_step(description: str, command: list) -> bool:

    print()
    print("=" * 70)
    print(f"PASO: {description}")
    print("=" * 70)

    result = subprocess.run([sys.executable] + command)

    if result.returncode != 0:
        print(f"AVISO: '{description}' terminó con error (código {result.returncode}). Se continúa igualmente.")
        return False

    return True


def get_stale_tickers(tickers: list, max_age_days: int) -> list:

    stale = []
    now = time.time()

    for ticker in tickers:

        path = os.path.join(FUNDAMENTALS_DIR, f"{ticker}.csv")

        if not os.path.exists(path):
            stale.append(ticker)
            continue

        age_days = (now - os.path.getmtime(path)) / 86400

        if age_days > max_age_days:
            stale.append(ticker)

    return stale


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-roe", type=float, default=0.10)
    parser.add_argument("--skip-fundamentals", action="store_true",
                         help="No refrescar fundamentales aunque estén desactualizados")
    parser.add_argument("--calculate-only", action="store_true",
                         help="Solo precios+fundamentales+screener, sin enviar email")
    parser.add_argument("--send-only", action="store_true",
                         help="Solo enviar el email con el último informe ya calculado")
    args = parser.parse_args()

    if args.calculate_only and args.send_only:
        raise ValueError("--calculate-only y --send-only son excluyentes, usa solo uno")

    start_time = datetime.now()
    print(f"Pipeline diario — inicio: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    if args.send_only:
        run_step("Envío del informe por email", ["send_email_report.py"])
        end_time = datetime.now()
        print()
        print("=" * 70)
        print(f"Fase de envío completa. Duración: {end_time - start_time}")
        print("=" * 70)
        return

    print()
    print("Cargando universo de tickers desde data/tickers/...")
    tickers = load_tickers()

    run_step("Actualización de precios (Yahoo)", ["update_prices_daily.py"])

    if not args.skip_fundamentals:

        stale = get_stale_tickers(tickers, FUNDAMENTALS_MAX_AGE_DAYS)

        if stale:
            print()
            print(f"{len(stale)} de {len(tickers)} tickers tienen fundamentales "
                  f"desactualizados (> {FUNDAMENTALS_MAX_AGE_DAYS} días) o ausentes.")
            run_step("Refresco de fundamentales (SEC EDGAR)", ["fetch_sec_fundamentals.py"])
        else:
            print()
            print("Fundamentales al día para todos los tickers — se omite este paso.")
    else:
        print()
        print("--skip-fundamentals activado — se omite el refresco de fundamentales.")

    run_step(
        "Screener de Valor + Calidad",
        ["value_quality_screener.py", "--top", str(args.top), "--min-roe", str(args.min_roe)],
    )

    if not args.calculate_only:
        run_step("Envío del informe por email", ["send_email_report.py"])
    else:
        print()
        print("--calculate-only activado — se omite el envío del email (se hará en la fase de envío).")

    end_time = datetime.now()
    print()
    print("=" * 70)
    print(f"Pipeline completo. Duración: {end_time - start_time}")
    print("=" * 70)


if __name__ == "__main__":
    main()

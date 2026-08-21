# Quantitative Market Research Platform

## Estado del proyecto

> **Estado actual: En desarrollo — fase de investigación cuantitativa + primeros pasos en backtesting**

Este proyecto pretende convertirse en una plataforma de análisis cuantitativo de mercados capaz de estudiar datos históricos, detectar oportunidades, evaluar estrategias y asistir en el proceso de investigación mediante IA.

Actualmente se ha construido la **base de investigación cuantitativa** y ya existe un **motor de backtesting inicial**, pendiente de validar contra datos reales.

### Lo que ya está implementado

* [x] Arquitectura de proveedores de datos.
* [x] Obtención de datos históricos mediante Yahoo Finance.
* [x] Almacenamiento de datos raw en formato Parquet.
* [x] Validación de calidad de datos.
* [x] Detección de anomalías de precio y volumen.
* [x] Motor de generación de features.
* [x] Cálculo de retornos, RVOL, medias móviles, ATR, volatilidad y rangos.
* [x] Event studies sobre datos históricos.
* [x] Forward returns a 1, 3, 5, 10 y 20 sesiones.
* [x] Análisis estadístico de eventos.
* [x] Análisis MAE / MFE.
* [x] Estudios de Stop Loss / Take Profit.
* [x] Análisis de sensibilidad de parámetros.
* [x] Separación Development / Out-of-Sample.
* [x] Comparación contra baseline.
* [x] Identificación de regiones de parámetros potencialmente robustas.
* [x] Motor de backtesting base (`src/backtest/`): simulación de entradas/salidas con Stop Loss, Take Profit y salida por tiempo, curva de equity y métricas (CAGR, Sharpe, drawdown, win rate, profit factor).

### Lo que todavía NO está implementado

* [ ] Validación del motor de backtesting contra los datos reales de AAPL (pendiente de ejecutar).
* [ ] Position sizing avanzado (basado en equity total, no solo en cash libre) — necesario para multi-activo.
* [ ] Comisiones y slippage reales (el motor ya tiene el hook, falta poner valores).
* [ ] Walk-forward analysis (hoy el split Dev/OOS son dos backtests independientes, no una única curva continua).
* [ ] Scanner automático de oportunidades.
* [ ] Gestión del riesgo.
* [ ] Análisis asistido por IA.
* [ ] Pipeline completo para múltiples activos.
* [ ] Evaluación sistemática de costes de transacción y slippage.
* [ ] Sistema completo de generación y seguimiento de señales.
* [ ] Conectar `DataValidator` / `AnomalyDetector` (ya implementados en `validator.py`) al pipeline de `event_study.py` / `robustness.py` / `backtest_run.py`.

---

# Roadmap del proyecto

El objetivo final es desarrollar una plataforma dividida conceptualmente en las siguientes áreas.

## 1. Análisis de precio y volumen

**Estado: 🟢 Base implementada**

Análisis cuantitativo de:

* Precio.
* Volumen.
* Retornos.
* RVOL.
* Tendencia.
* Medias móviles.
* Volatilidad.
* ATR.
* Rangos.
* Breakouts.
* Contexto de mercado.

La arquitectura de `FeatureEngine` está diseñada para poder ampliar progresivamente este conjunto de variables.

---

## 2. Backtesting de estrategias

**Estado: 🟡 Base implementada — pendiente de validar con datos reales**

Ya existe un motor de backtesting (`src/backtest/engine.py`, `src/backtest/metrics.py`) y un script de ejecución (`backtest_run.py`) que reutiliza la señal ya validada en `robustness.py`.

Incluye, por ahora:

* Reglas de entrada por señal (Close[D] → entrada en Open[D+1], evitando look-ahead bias).
* Stop Loss y Take Profit fijos.
* Time exits.
* Position sizing simple (100% del capital disponible por operación).
* Arquitectura preparada para posiciones simultáneas (pensando en multi-activo).
* Curva de equity y métricas: CAGR, Sharpe, max drawdown, win rate, profit factor.
* Split Development / Out-of-Sample (como dos backtests independientes).

Pendiente:

* Comisiones y slippage reales.
* Position sizing basado en equity total (no en cash libre).
* Walk-forward analysis en vez de split fijo.
* Validación contra datos reales de AAPL (bloqueado por no poder ejecutar `pyarrow` en el entorno de análisis; pendiente correrlo en local).

---

## 3. Scanner de oportunidades

**Estado: 🔴 Pendiente**

El proyecto deberá ser capaz de aplicar las señales y condiciones investigadas sobre un universo de activos y detectar automáticamente aquellos que presentan oportunidades.

Conceptualmente:

```text
Market universe
      ↓
Data
      ↓
Features
      ↓
Signal conditions
      ↓
Candidate opportunities
      ↓
Ranking / filtering
```

El scanner no debería limitarse inicialmente a AAPL. AAPL se utiliza actualmente como activo de investigación y referencia.

---

## 4. Gestión del riesgo

**Estado: 🔴 Pendiente**

La plataforma deberá incorporar una capa explícita de gestión del riesgo.

Entre los objetivos futuros:

* Position sizing.
* Riesgo máximo por operación.
* Riesgo agregado de cartera.
* Stop Loss dinámicos.
* Control de exposición.
* Correlación entre posiciones.
* Drawdown limits.
* Volatilidad.
* Gestión del capital.

La existencia de un buen patrón estadístico no implica automáticamente que pueda convertirse en una estrategia operable. La gestión del riesgo deberá evaluarse como una capa independiente.

---

## 5. Análisis asistido por IA

**Estado: 🔴 Pendiente**

Una de las metas finales del proyecto es incorporar IA como herramienta de investigación y análisis.

La IA no debería sustituir automáticamente al análisis estadístico, sino actuar como una capa de asistencia sobre los datos y resultados generados por el sistema.

Posibles usos:

* Interpretación de resultados.
* Generación de hipótesis.
* Comparación de señales.
* Identificación de relaciones potenciales.
* Análisis de anomalías.
* Explicación de resultados estadísticos.
* Generación de informes.
* Asistencia en la investigación de estrategias.
* Análisis de resultados de backtests.
* Interfaz de consulta sobre el histórico de investigaciones.

La validación estadística deberá permanecer separada de la interpretación realizada por IA.

---

## 6. Evaluación y validación de señales

**Estado: 🟡 Parcialmente implementado**

Esta capa ya existe parcialmente mediante `event_study.py` y `robustness.py`, pero deberá crecer junto con el proyecto.

Actualmente incluye:

* Baseline.
* Forward returns.
* Development / OOS.
* Sensibilidad de parámetros.
* MAE / MFE.
* Stop / Take Profit.
* Robust regions.

En fases posteriores deberá incorporar progresivamente:

* Walk-forward analysis.
* Múltiples períodos OOS.
* Múltiples activos.
* Diferentes regímenes de mercado.
* Costes de transacción.
* Slippage.
* Test de estabilidad temporal.
* Control de múltiples comparaciones / data mining.
* Validación cruzada temporal cuando sea apropiada.

---

# Visión general

El objetivo final puede resumirse como:

```text
                    MARKET DATA
                         │
                         ▼
                DATA VALIDATION
                         │
                         ▼
                  FEATURE ENGINE
                         │
                         ▼
              PRICE / VOLUME ANALYSIS
                         │
                         ▼
                 EVENT STUDIES
                         │
                         ▼
              SIGNAL DISCOVERY
                         │
                         ▼
             SIGNAL VALIDATION
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         BACKTESTING             SCANNER
              │                     │
              └──────────┬──────────┘
                         ▼
                  RISK MANAGEMENT
                         │
                         ▼
                    PORTFOLIO
                         │
                         ▼
                    AI LAYER
                         │
                         ▼
              ANALYSIS / ASSISTANCE
```

La prioridad actual es **validar el motor de backtesting con datos reales y cerrar la capa de investigación antes de pasar al scanner o a la gestión del riesgo**.

---

## Estado actual resumido

| Área                       | Estado                       |
| -------------------------- | ----------------------------- |
| Datos y proveedores        | 🟢 Implementado               |
| Validación de datos        | 🟢 Implementado (no conectado al pipeline aún) |
| Feature engineering        | 🟢 Implementado               |
| Análisis de precio/volumen | 🟢 En desarrollo avanzado     |
| Event studies               | 🟢 Implementado               |
| Robustez / sensibilidad    | 🟢 Implementado               |
| Validación OOS              | 🟢 Implementado inicialmente  |
| Backtesting                 | 🟡 Base implementada, pendiente de validar |
| Scanner                     | 🔴 Pendiente                  |
| Gestión del riesgo          | 🔴 Pendiente                  |
| IA                          | 🔴 Pendiente                  |
| Portfolio / ejecución       | 🔴 Pendiente                  |

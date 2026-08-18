# Quantitative Market Research Platform

## Estado del proyecto

> **Estado actual: En desarrollo — fase de investigación cuantitativa**

Este proyecto pretende convertirse en una plataforma de análisis cuantitativo de mercados capaz de estudiar datos históricos, detectar oportunidades, evaluar estrategias y asistir en el proceso de investigación mediante IA.

Actualmente se ha construido la **base de investigación cuantitativa** y se está trabajando en la validación de las primeras hipótesis.

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

### Lo que todavía NO está implementado

* [ ] Backtesting completo de estrategias.
* [ ] Scanner automático de oportunidades.
* [ ] Gestión del riesgo.
* [ ] Análisis asistido por IA.
* [ ] Pipeline completo para múltiples activos.
* [ ] Evaluación sistemática de costes de transacción y slippage.
* [ ] Sistema completo de generación y seguimiento de señales.

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

**Estado: 🔴 Pendiente**

Una vez identificadas y validadas hipótesis mediante event studies, el proyecto deberá permitir convertirlas en estrategias y realizar backtests completos.

Esto deberá incluir, entre otros:

* Reglas de entrada.
* Reglas de salida.
* Stop Loss.
* Take Profit.
* Time exits.
* Position sizing.
* Capital inicial.
* Operaciones simultáneas.
* Comisiones.
* Slippage.
* Equity curve.
* Drawdown.
* Métricas de rendimiento y riesgo.

El backtesting deberá mantener las mismas convenciones temporales utilizadas durante la investigación para evitar look-ahead bias.

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

La prioridad actual es **seguir construyendo y validando correctamente la capa de investigación antes de pasar a automatizar estrategias o señales**.

---

## Estado actual resumido

| Área                       | Estado                       |
| -------------------------- | ---------------------------- |
| Datos y proveedores        | 🟢 Implementado              |
| Validación de datos        | 🟢 Implementado              |
| Feature engineering        | 🟢 Implementado              |
| Análisis de precio/volumen | 🟢 En desarrollo avanzado    |
| Event studies              | 🟢 Implementado              |
| Robustez / sensibilidad    | 🟢 Implementado              |
| Validación OOS             | 🟢 Implementado inicialmente |
| Backtesting                | 🔴 Pendiente                 |
| Scanner                    | 🔴 Pendiente                 |
| Gestión del riesgo         | 🔴 Pendiente                 |
| IA                         | 🔴 Pendiente                 |
| Portfolio / ejecución      | 🔴 Pendiente                 |

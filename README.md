# Trading AI — Investigación Cuantitativa y Screener de Valor + Calidad

Repo: [github.com/unaidelpozo95-commits/trading-ai](https://github.com/unaidelpozo95-commits/trading-ai)

---

## Pendiente / roadmap

### ✅ Resuelto recientemente
- Cron dividido en dos fases: cálculo a las 22:00, envío del email a las 7:00 (con `CRON_TZ=Europe/Madrid` para no depender de la zona horaria del sistema)
- Top 5 mayores subidas / Top 5 mayores caídas del día, con precio objetivo incluido
- Precio objetivo por P/E mediano del sector (tabla principal y top movers)
- Ratio Deuda/Patrimonio (D/E), con aviso de que varía mucho por sector (bancos/financieras tienen D/E alto de forma normal)
- `DataValidator` conectado en `update_prices_daily.py` — valida cada ticker tras actualizarlo (fechas duplicadas, orden cronológico, OHLC inconsistente, valores negativos), sin bloquear el proceso
- `AnomalyDetector` conectado en `value_quality_screener.py` — nueva sección "Anomalías de datos de hoy" (movimientos de precio ≥15% o volumen ≥5x la media)
- Envío del email a varios destinatarios a la vez (`EMAIL_TO` separado por comas)
- Reorganización del repo: todo lo que no es producción diaria (investigación, backtests, descubrimiento de estrategias) vive en `research/`

### 🔧 Pendiente de verdad
- **HTML del informe más cuidado/bonito** para poder compartirlo con otras personas — el actual ya es robusto (tras resolver que Gmail rompía las tablas), pero sigue siendo bastante básico visualmente
- **Optimizar la descarga de precios por lotes** — se intentó con `yf.download` en lotes, dio error "possibly delisted; no timezone found" en casi todos los tickers; revertido a ticker-a-ticker (lento pero funcional). Diagnóstico de la causa real pendiente
- **Universo internacional**: CSVs ya convertidos (Frankfurt, ASX, Hong Kong, Tokio, IBEX35 — este último desactualizado, composición de ~2015) aparcados en `data/tickers/ignore/`. El filtro de Valor+Calidad **no funciona fuera de EEUU** porque SEC EDGAR solo cubre empresas que reportan a ese regulador — haría falta una fuente de fundamentales por país
- **PEAD** (Post-Earnings Announcement Drift) — diagnóstico de datos construido (`research/pead_data_check.py`), nunca ejecutado
- **Trend-following** — señal a 120 días prometedora en el análisis preliminar, pero con aviso de solapamiento de ventanas sospechoso; sin backtest real de confirmación
- **Factor de Calidad (ROE) como tercera pieza** de la cartera combinada AAPL+Reversión (80/20) — nunca se llegó a probar esa correlación
- **Revenues en SEC EDGAR** con cobertura irregular (problema conocido de múltiples nombres de tag XBRL)
- **Métricas adicionales para el screener**, mencionadas pero no implementadas: FCF Yield (flujo de caja libre / precio), consistencia del ROE en varios años (ya tenemos el histórico descargado, solo falta usarlo), PEG ratio, Piotroski F-Score

---

## Qué es esto

Este proyecto empezó como una búsqueda de estrategias de trading sistemático capaces de batir al mercado. Tras una investigación extensa y rigurosa (resumida más abajo), la conclusión honesta fue que ese objetivo, con los datos y recursos disponibles, no es realista — ni siquiera la mayoría de fondos profesionales lo consiguen de forma consistente.

El proyecto **pivotó** hacia algo con un objetivo distinto y más alcanzable: una **herramienta diaria automatizada de análisis Valor + Calidad** que escanea un universo de empresas, calcula ratios fundamentales (P/E, P/B, ROE, D/E) de forma transparente, detecta anomalías de mercado, y envía un informe por email — pensada como apoyo a la propia toma de decisiones, no como una máquina de generar señales de compra.

Hay dos partes en este repo:

1. **La investigación** (`research/`, `src/backtest/`, `src/research/`) — el histórico completo de hipótesis probadas, con lo que sobrevivió y lo que se descartó. No está en producción, pero documenta por qué se tomó cada decisión.
2. **El screener en producción** (raíz del repo: `value_quality_screener.py`, `run_daily_pipeline.py`, `send_email_report.py`, etc.) — lo que corre de verdad todos los días en el servidor.

---

## Estructura del repo

```
trading-ai/
├── src/
│   ├── data/
│   │   ├── providers/yahoo.py       # descarga de precios (Yahoo Finance)
│   │   └── validator.py             # DataValidator + AnomalyDetector
│   ├── features/engine.py           # FeatureEngine: retornos, RVOL, medias, ATR...
│   ├── backtest/                    # motor de backtesting (single-asset y multi-asset)
│   └── research/                    # sistema de descubrimiento automático de estrategias
├── research/                        # TODO lo que no es producción diaria — invocar con
│                                     # `python -m research.nombre_script`, no directamente
├── templates/
│   ├── report_shell.html            # estructura general del email (editable)
│   ├── report_row.html              # fila de cada empresa en la tabla principal
│   ├── movers_row.html              # fila de cada mover (con precio objetivo)
│   └── anomaly_row.html             # fila de cada anomalía detectada
├── data/
│   ├── tickers/                     # CUALQUIER CSV aquí (no en subcarpetas) se carga automáticamente
│   │   └── ignore/                  # mercados aparcados — no se cargan (ej. internacionales)
│   ├── raw/yahoo/                   # precios descargados (parquet)
│   ├── sec_fundamentals/            # fundamentales descargados de SEC EDGAR
│   └── strategies/                  # estrategias validadas por el sistema de descubrimiento
├── .env                             # credenciales de email (NUNCA se sube a git)
├── .env.example                     # plantilla sin credenciales (sí se sube)
├── ticker_universe.py               # carga/fusiona tickers desde data/tickers/*.csv
├── update_prices_daily.py           # actualización incremental de precios + validación de calidad
├── fetch_sec_fundamentals.py        # descarga fundamentales (SEC EDGAR)
├── value_quality_screener.py        # el screener en sí (P/E, P/B, ROE, D/E, movers, anomalías)
├── send_email_report.py             # envío del informe por Gmail (varios destinatarios)
└── run_daily_pipeline.py            # orquestador — un solo comando para todo
```

---

## Historia de la investigación

Todo lo que sigue se hizo con un método consistente: separar datos en **Development** (para explorar) y **Out-of-sample** (para confirmar), y más adelante ir un paso más allá con un split de **tres tramos** (Train / Validación / Test) donde el tramo Test se mira **una sola vez** y se acepta el resultado sea cual sea. Esa disciplina fue la que permitió detectar y corregir varios errores metodológicos serios por el camino (ver más abajo).

### Fase 1 — Momentum/breakout: ¿AAPL es único?

Señal original: `return_1d ≥ 2%`, `rvol_20 ≥ 2.0`, `distance_high_20 ≥ -5%`, con salida por stop/target/tiempo.

- **AAPL**: señal genuina y robusta — 22 trades, Sharpe 0.98, drawdown -5.37%, se mantiene en dev y OOS.
- Probado en otros 13 tickers (MSFT, GOOGL, AMZN, NVDA, TSLA, META, BRK-B, JPM, JNJ, AVGO...): **ninguno pasó los filtros**. El caso NVDA parecía prometedor en un momento (alpha OOS +12-14%) pero resultó ser beta del rally de IA 2023-2025, no señal real.
- **Conclusión**: de 14 tickers probados con rigor, **solo AAPL tiene una señal de momentum validada**. No generaliza a megacaps por defecto.

### Fase 2 — Ranking cruzado (cross-sectional) y reversión

En vez de umbrales fijos por ticker, se rankeó diariamente un universo de tickers por percentil de momentum+volumen+distancia a máximos, comparando contra la media del universo.

- El **top** del ranking (líderes) no mostró ventaja consistente.
- El **fondo** del ranking (rezagados) sí mostró una reversión positiva y significativa, que se **fortaleció** al ampliar el universo de 11 a 40 tickers (t-stats de 3.07 a 4.92 en ambos períodos).
- El primer backtest real (long-only) **no batió** a comprar y mantener la cesta.
- Con rebalanceo **long-short periódico** (cada 20 días) tampoco hubo ventaja consistente.
- La clave fue cambiar a rebalanceo **continuo/solapado** (cohorte nueva cada día): ahí apareció el primer resultado positivo y consistente del proyecto (Sharpe Dev 0.34, OOS 0.78).
- Al añadir **fricciones realistas** (comisión + slippage + coste de préstamo), el Sharpe cayó a negativo con holding corto — pero un barrido de holding period mostró que **alargar el holding a 30-60 días** recupera la rentabilidad neta. Mejor punto: **holding=40 días** (Sharpe Dev 0.21, OOS 0.53).
- **Rentabilidad final real** (con fricciones, holding 40d): CAGR ~1-3% — modesto, por debajo de la letra del Tesoro. **Decisión en su momento: no llevarlo a producción como sistema aislado** (más adelante sí se usó como pieza de una cartera combinada, ver Fase 6).

### Fase 3 — Ideas descartadas

- **Anomalía de baja volatilidad**: resultado inicial muy significativo, pero en la dirección *opuesta* a la literatura académica. Al investigar, se descubrió que **AMD+NVDA+TSLA concentraban el 77.5%** del exceso de retorno — era el rally de IA disfrazado de "factor de volatilidad", no un patrón generalizable. Descartado.
- **Trend-following** (Close > SMA200): resultado mixto, con una señal aparentemente fuerte a 120 días que resultó estar inflada por solapamiento de ventanas (N efectivo independiente ~24, no miles). Quedó sin backtest real de confirmación — **pendiente, no descartado del todo**.
- **PEAD** (Post-Earnings Announcement Drift): se construyó un script de diagnóstico de datos de earnings pero nunca se ejecutó — **pendiente**, a retomar en el futuro.

### Fase 4 — El S&P 500 completo y la lección de *selection bias*

Se amplió el sistema de descubrimiento automático a los 505 tickers del S&P 500, exigiendo que cada ticker validado tuviera buen t-stat **tanto en Dev como en OOS**.

- Resultado inicial: **42 tickers validados**, con un backtest de cartera que daba un CAGR de **50-73%** — sospechosamente bueno.
- **Se detectó un error metodológico serio**: exigir que el t-stat fuera bueno en Dev *y* en OOS a la vez convertía la selección en un criterio que usaba el propio OOS — invalidando su uso como prueba honesta de fuera de muestra (*selection bias*/*look-ahead*). Además, los ganadores estaban concentrados en energía/materias primas (rally de 2021-2022) — el mismo patrón de concentración temática que ya se había visto con la IA.
- **Corrección**: se rehizo el descubrimiento dejando 2023+ completamente fuera del proceso de selección (un holdout genuinamente virgen). Resultado: de 42 tickers **bajó a solo 6**, y el backtest honesto sobre esos 6 mostró que **más del 99% del beneficio neto venía de un solo ticker** (EL) — el resto plano o negativo. Es decir: sin el sesgo, no había ninguna cartera de patrones independientes real.
- **Esta es la lección metodológica más importante de todo el proyecto**: buscar en un espacio muy grande de combinaciones garantiza encontrar "algo" que parezca funcionar, sin que eso signifique que sea real.

### Fase 5 — Factores académicos con disciplina real

En vez de seguir ampliando el universo de búsqueda (lo cual solo aumenta el riesgo de falsos positivos), se cambió de método: usar factores con **respaldo académico**, con parámetros **fijos de la literatura** (sin barrido), y un split de **tres tramos** — Train / Validación / Test — donde el Test se mira una única vez.

- **Momentum 12-1** (Jegadeesh-Titman, 1993 — retorno de 12 meses saltando el último mes, top 30%): **validado de forma limpia** — incluso más fuerte en el test (t=5.60) que en la validación (t=3.25). El primer hallazgo del proyecto que sobrevive una prueba genuinamente pre-registrada sin ningún ajuste posterior.
  - Backtest real (long-short, holding ~1 mes, con fricciones): positivo sin fricciones, pero **se vuelve negativo con fricciones reales** (CAGR -1.41%). Siguiendo la disciplina, se aceptó este resultado sin retocar el holding period para "salvarlo".
- **Cercanía al máximo de 52 semanas** (George-Hwang, 2004, top 30%): **descartado correctamente** — ya venía débil en validación y salió negativo y significativo en el test.
- **Calidad / ROE** (`NetIncomeLoss / StockholdersEquity`, top 30%, datos de SEC EDGAR): **validado de forma limpia y a gran escala** sobre los 505 tickers del S&P 500 — significancia que *crece* en el test (t=6.32) frente a la validación (t=3.45).
  - Backtest real (long-short, holding ~1 año, con fricciones): **sigue positivo tras fricciones** (CAGR +0.34%, Sharpe 0.12) — a diferencia del momentum. El ROE solo se actualiza una vez al año, así que el turnover natural es mucho menor y sobrevive mejor a los costes. En solitario, sin embargo, el Sharpe es económicamente insignificante.

### Fase 6 — Cartera combinada

Se combinó **AAPL (momentum)** con la **reversión cross-sectional (holding 40d)**:

- Correlación entre ambas: **~0.008**, prácticamente nula — lógico, dado que son estrategias con lógica de mercado opuesta.
- Con reparto 50/50 la mezcla no siempre batía a AAPL solo. Un barrido de pesos mostró que el punto óptimo está en **~20% reversión / 80% AAPL**: el Sharpe combinado supera a AAPL solo en **los tres períodos a la vez** (Full 1.03 vs 0.98, Dev 0.86 vs 0.84, OOS 1.35 vs 1.25), con menor drawdown en OOS.
- Es el primer resultado del proyecto que mejora de forma consistente sobre el mejor componente individual, en todos los períodos — diversificación real, no casualidad de un solo tramo.
- El factor de Calidad (ROE) quedó pendiente de probar como tercera pieza de esta cartera (nunca se llegó a ejecutar esa comprobación — ver roadmap).

### Fase 7 — Pivote: de "batir al mercado" a herramienta práctica

Tras agotar razonablemente las vías de investigación con los datos y recursos disponibles, el foco cambió a construir algo útil de verdad: un **screener diario de Valor + Calidad** (ver siguiente sección). No busca batir al mercado — ayuda a **encontrar candidatos** para el propio análisis del usuario, con total transparencia sobre por qué aparece cada empresa.

---

## Hallazgos que sobreviven (resumen ejecutivo)

| Hallazgo | Estado | Notas |
|---|---|---|
| AAPL momentum/breakout | ✅ Validado, robusto | El único hallazgo de momentum verdaderamente sólido |
| Reversión cross-sectional (40 tickers, holding 40d) | ✅ Validado, económicamente modesto en solitario | CAGR 1-3% con fricciones |
| Cartera AAPL + Reversión (80/20) | ✅ Mejor resultado del proyecto | Mejora consistente sobre AAPL solo en todos los períodos |
| Momentum 12-1 (Jegadeesh-Titman) | ⚠️ Estadísticamente real, no operable | No sobrevive fricciones en su horizonte natural |
| Calidad/ROE | ⚠️ Estadísticamente real, económicamente marginal en solitario | Sobrevive fricciones, pero Sharpe insuficiente solo; pendiente probar en la cartera combinada |
| Anomalía de volatilidad | ❌ Descartado | Concentración en 3 tickers (AMD/NVDA/TSLA), no es un factor real |
| S&P 500 scan (42→6 tickers) | ❌ Descartado | Selection bias — sin sesgo, era esencialmente una acción con suerte |
| Trend-following, PEAD | ⏸️ Pendiente | Nunca se llegó a confirmar ni a descartar del todo |

---

## Sistema actual en producción: Screener de Valor + Calidad

### Qué hace

Cada día laborable, el pipeline en dos fases:

**Fase de cálculo (22:00):**
1. **Actualiza precios** de forma incremental (`update_prices_daily.py`) — solo pide a Yahoo los días nuevos desde la última descarga, y valida la calidad de cada ticker con `DataValidator` (fechas duplicadas, OHLC inconsistente, etc. — sin bloquear el proceso, solo lo deja registrado).
2. **Refresca fundamentales** (`fetch_sec_fundamentals.py`) — solo para tickers cuyo dato tenga más de 25 días o sea nuevo.
3. **Corre el screener** (`value_quality_screener.py`) — calcula P/E, P/B, ROE y D/E, filtra por ROE mínimo, detecta el Top 5 subidas/Top 5 caídas del día (con precio objetivo incluido), detecta anomalías de precio/volumen con `AnomalyDetector`, y genera un ranking transparente con explicación en lenguaje llano de por qué aparece cada empresa (pura aritmética, sin IA ni caja negra).

**Fase de envío (7:00):**
4. **Envía el informe por email** (`send_email_report.py`) — HTML con tabla estilizada, nombre de empresa junto al ticker, movers, anomalías, y el CSV completo adjunto. Soporta varios destinatarios (`EMAIL_TO` separado por comas).

### Universo de tickers — dinámico

Cualquier CSV que metas en `data/tickers/` (con columna `ticker` o `Symbol`, y opcionalmente `Name` y `Sector`) se fusiona automáticamente con el resto. Los CSV dentro de subcarpetas (ej. `data/tickers/ignore/`) se ignoran a propósito — es la forma de aparcar un mercado sin borrarlo.

### Fuentes de datos

- **Precios**: Yahoo Finance (gratuito, vía `yfinance`).
- **Fundamentales**: SEC EDGAR (`data.sec.gov`, oficial y gratuito, con histórico desde ~2009 para la mayoría de grandes empresas de EEUU). Solo cubre empresas que reportan ante la SEC — no sirve para mercados internacionales.

### Despliegue

Corre en un servidor Linux (Ubuntu) del usuario, con cron (zona horaria Madrid vía `CRON_TZ`):

```
CRON_TZ=Europe/Madrid
0 22 * * 1-5 cd /home/unai/trading-ai && /home/unai/trading-ai/.venv/bin/python run_daily_pipeline.py --calculate-only --top 30 --min-roe 0.15 >> data/pipeline_log.txt 2>&1
0 7 * * 1-5 cd /home/unai/trading-ai && /home/unai/trading-ai/.venv/bin/python run_daily_pipeline.py --send-only >> data/pipeline_log.txt 2>&1
```

---

## Instalación y uso

```bash
git clone <repo>
cd trading-ai
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # pandas, requests, yfinance, etc.
```

1. Crea la carpeta de tickers y mete al menos un CSV:
   ```bash
   mkdir -p data/tickers
   # copia tu CSV (columna 'ticker' o 'Symbol', opcionalmente 'Name' y 'Sector') a data/tickers/
   ```

2. Configura el email (Gmail, requiere contraseña de aplicación — ver `.env.example`):
   ```bash
   cp .env.example .env
   # edita .env con tu email real, la contraseña de aplicación, y los destinatarios (separados por comas si son varios)
   ```

3. Primera ejecución (descarga completa, puede tardar):
   ```bash
   python run_daily_pipeline.py --top 30 --min-roe 0.15
   ```

4. Automatiza con cron (ver sección de despliegue arriba).

Los scripts de investigación (`research/`) se invocan como módulo, siempre desde la raíz del repo:
```bash
python -m research.discover_strategy_for_ticker --from-file data/tickers/sp500.csv
```

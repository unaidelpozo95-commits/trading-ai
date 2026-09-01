# Roadmap — Trading AI

## Fase 1: Pulido del proyecto actual (corto plazo)

Antes de abrir líneas nuevas, cerrar los cabos sueltos del screener Valor+Calidad ya en producción:

- [ ] **Email a múltiples destinatarios** — `send_email_report.py` solo envía a una dirección; ampliarlo para enviar a varias.
- [ ] **Diagnosticar la descarga por lotes** — `update_prices_daily.py` falla ("possibly delisted; no timezone found") al usar `yf.download` con varios tickers por llamada. Revertido a ticker-a-ticker (funcional pero lento, ~4h con miles de tickers). Investigar si es `threads=True`, tamaño de lote, versión de `yfinance` o rate limit.
- [ ] **Decidir si el factor Calidad entra en la cartera combinada** — comprobar su correlación con la cartera AAPL (momentum) + Reversión cross-sectional (80/20 ya validada). Si la correlación es baja, evaluar añadirlo como tercera pieza diversificadora aunque sea débil en solitario (mismo patrón que la reversión).
- [ ] *(Opcional, menor prioridad)* Conectar `DataValidator`/`AnomalyDetector` (ya existen en `validator.py`) al pipeline de los scripts de investigación, que hoy no pasan por ellos.

---

## Fase 2: Insider trading tracker (Form 4, SEC EDGAR) — medio plazo

Reutiliza el pipeline de EDGAR ya construido para fundamentales.

- [ ] Extender el fetcher de SEC EDGAR para leer Form 4 (compras/ventas de insiders) en vez de solo XBRL de balances.
- [ ] Definir la señal: "cluster buying" (varios insiders distintos comprando en una ventana corta) como hipótesis principal, con justificación en literatura académica.
- [ ] Aplicar la misma disciplina que en el resto del proyecto: split Train/Validación/Test, parámetros fijos sin barrido, Test se mira una sola vez.
- [ ] Backtest real con fricciones antes de decidir si pasa a producción.

## Fase 3: Seguimiento de 13F institucional — medio plazo

- [ ] Fuente de datos: 13F trimestrales (SEC EDGAR, mismo API base que Form 4).
- [ ] Señal candidata: entradas/salidas fuertes de fondos de calidad (concentración, activismo) en una posición.
- [ ] Misma disciplina de validación que en Fase 1. Señal más lenta (trimestral) — ajustar expectativas de frecuencia de trading.

## Fase 4: Cripto — funding rate / basis arbitrage — medio-largo plazo

- [ ] Investigar APIs de exchanges (Binance/Bybit u otros) para funding rate de perpetuos y precio spot.
- [ ] Estrategia base: long spot + short perpetuo cuando el funding es muy positivo (delta-neutral, no depende de dirección).
- [ ] Modelar costes reales: comisiones, spread, riesgo de contraparte/exchange, gestión de márgenes.
- [ ] Script de monitorización diaria/intradía de oportunidades, con o sin ejecución automática (empezar solo con alertas).

## Fase 5: Screener como producto (newsletter de pago) — largo plazo

Cambio de modelo de negocio: en vez de buscar batir al mercado con capital propio, vender la información.

- [ ] Definir formato del informe (ya existe la base: email diario del screener Valor+Calidad).
- [ ] Elegir plataforma de suscripción/pago (Substack, Beehiiv, Gumroad, etc.) y flujo de alta de nuevos suscriptores.
- [ ] Adaptar `run_daily_pipeline.py` para generar salida apta para envío masivo (no solo a tu email).
- [ ] Validar la propuesta de valor con un grupo piloto antes de monetizar.

## Fase 6: Apuestas deportivas / mercados de predicción — largo plazo

- [ ] Elegir mercado inicial (liga menor con menos eficiencia, o mercado de predicción tipo Polymarket/Kalshi).
- [ ] Pipeline de scraping de cuotas/odds.
- [ ] Modelo de valor esperado (value betting) con misma disciplina de validación.
- [ ] Revisar marco regulatorio y de liquidez antes de operar con capital real.

---

*Orden de prioridad acordado: Fase 1 (pulido) → Fase 2 → Fase 3 → Fase 4 → Fase 5 → Fase 6.*

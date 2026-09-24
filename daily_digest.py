"""
Resumen diario con IA local (Ollama) — SOLO si hay algo que contar.

Flujo:
  1. Guarda el snapshot de hoy (para poder comparar mañana).
  2. Detecta novedades reales comparando con ayer (novelty_detector.py
     — pura lógica, sin IA).
  3. Si NO hay ninguna novedad: escribe "SKIP" en
     data/email_decision.txt — send_email_report.py no enviará nada
     hoy.
  4. Si SÍ hay novedades: le pide a un modelo local (vía Ollama) que
     las redacte en un resumen breve y legible. El modelo NUNCA
     calcula nada — solo redacta a partir de hechos ya verificados,
     para minimizar el riesgo de que invente datos. Si Ollama falla
     o no está disponible, se cae a una lista simple de los hechos en
     bruto (no se pierde la información, solo pierde la redacción
     bonita).
  5. Escribe "SEND" en data/email_decision.txt, y el resumen en
     data/daily_digest.html (una caja que send_email_report.py añade
     al principio del email).

Requiere Ollama corriendo en local (http://localhost:11434) con el
modelo descargado:
    ollama pull llama3.1
"""

import html
import os

import requests

from novelty_detector import save_todays_snapshot, detect_novelties


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1"  # 8B, buen equilibrio calidad/velocidad para 16GB RAM en CPU
OLLAMA_TIMEOUT_SECONDS = 120

DECISION_PATH = "data/email_decision.txt"
DIGEST_PATH = "data/daily_digest.html"

PROMPT_TEMPLATE = """Eres un asistente que redacta resúmenes financieros muy breves para un inversor particular que ya conoce su cartera de seguimiento.

Se te dan HECHOS ya verificados y calculados sobre lo detectado HOY, incluyendo el top movers del día con sus métricas de valor/calidad (P/E, P/B, ROE, D/E, FCF Yield, precio objetivo). Redáctalos de forma breve, clara y legible en español, empresa por empresa — para cada mover, comenta en una frase si su valor/calidad lo hace parecer una oportunidad tras una caída, o si una subida parece ya haber agotado el recorrido según esas métricas (P/E y precio objetivo altos = ya no tan barata; ROE alto y D/E bajo = fundamentales sólidos). Agrupa el resto de hechos (entradas/salidas de la lista de calidad, cambios de P/E o D/E) de forma breve al final.

REGLAS ESTRICTAS:
- NO inventes ningún dato, cifra o empresa que no aparezca en los hechos de abajo.
- NO des recomendaciones de compra ni de venta explícitas ("compra", "vende") — describe lo que dicen los números (barata/cara, sólida/endeudada, por encima/debajo de su objetivo) y deja la decisión al lector.
- NO añadas contexto de mercado que no esté en los hechos.
- Si un mover no tiene fundamentales disponibles, dilo brevemente en vez de omitirlo.
- Sé conciso: máximo 250 palabras.

HECHOS DE HOY:
{facts_bullets}

Resumen:"""


def call_ollama(facts: list) -> str:
    """Devuelve el resumen redactado por el modelo, o None si Ollama
    falla por cualquier motivo (no está corriendo, timeout, modelo no
    descargado, etc.) — el llamador debe tener un plan B."""

    facts_bullets = "\n".join(f"- {f}" for f in facts)
    prompt = PROMPT_TEMPLATE.format(facts_bullets=facts_bullets)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"AVISO: Ollama no disponible o falló ({e}) — se usará la lista de hechos en bruto.")
        return None


def build_digest_html(facts: list, narrative: str = None) -> str:
    """Caja HTML con el resumen (o la lista en bruto si no hay
    narrativa de la IA), para insertar al principio del email."""

    if narrative:
        body = f'<p style="margin: 0; color: #1a1a1a; font-size: 13px; line-height: 1.7;">{html.escape(narrative)}</p>'
    else:
        items = "".join(f'<li style="margin-bottom: 4px;">{html.escape(f)}</li>' for f in facts)
        body = f'<ul style="margin: 0; padding-left: 18px; color: #1a1a1a; font-size: 13px; line-height: 1.7;">{items}</ul>'

    return f"""
    <tr>
      <td style="padding: 18px 28px; background-color: #fffbeb; border-bottom: 2px solid #f59e0b;">
        <span style="font-size: 14px; font-weight: 700; color: #92400e;">📌 Resumen del día</span>
        <div style="margin-top: 8px;">{body}</div>
      </td>
    </tr>
    """


def main():

    print("Guardando snapshot de hoy...")
    save_todays_snapshot()

    print("Detectando novedades respecto a ayer...")
    facts = detect_novelties()

    if not facts:
        print("Sin novedades reales hoy — no se enviará email.")
        with open(DECISION_PATH, "w") as f:
            f.write("SKIP")
        if os.path.exists(DIGEST_PATH):
            os.remove(DIGEST_PATH)
        return

    print(f"{len(facts)} novedades detectadas:")
    for fact in facts:
        print(f"  - {fact}")

    print()
    print(f"Pidiendo a Ollama ({OLLAMA_MODEL}) que redacte el resumen...")
    narrative = call_ollama(facts)

    if narrative:
        print("Resumen generado por IA:")
        print(narrative)
    else:
        print("Sin resumen de IA — se usará la lista de hechos en bruto en el email.")

    digest_html = build_digest_html(facts, narrative)

    with open(DIGEST_PATH, "w") as f:
        f.write(digest_html)

    with open(DECISION_PATH, "w") as f:
        f.write("SEND")

    print()
    print(f"Guardado en {DIGEST_PATH}. Hoy SÍ se enviará email.")


if __name__ == "__main__":
    main()

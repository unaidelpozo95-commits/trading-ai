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

from novelty_detector import save_todays_snapshot, detect_novelties_split


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1"  # 8B, buen equilibrio calidad/velocidad para 16GB RAM en CPU
OLLAMA_TIMEOUT_SECONDS = 120

DECISION_PATH = "data/email_decision.txt"
DIGEST_MOVERS_PATH = "data/daily_digest_movers.html"
DIGEST_NOVELTIES_PATH = "data/daily_digest_novelties.html"
OLD_DIGEST_PATH = "data/daily_digest.html"  # formato anterior; se borra

PROMPT_MOVERS = """Eres un asistente que redacta resúmenes financieros muy breves para un inversor particular que ya conoce su cartera de seguimiento.

Se te dan HECHOS ya verificados y calculados sobre los top movers de HOY (primero las caídas, luego las subidas), cada uno con sus métricas de valor/calidad (puntuación combinada 0-100 con su desglose Valor/Calidad, P/E, P/B, ROE, D/E, FCF Yield, PEG, Piotroski F-Score, precio objetivo). Cada métrica ya viene con su etiqueta (barata/cara, deuda alta/baja, genera/quema caja...) y cada hecho termina con una "Lectura global" ya calculada con reglas fijas. Redáctalos de forma breve y legible en español, empresa por empresa, en el mismo orden (primero las caídas, luego las subidas) — usa y reformula esas etiquetas y esa lectura global (no las decidas tú ni las contradigas), diciendo básicamente si, a la vista de esos fundamentales, una caída pinta a oportunidad o una subida ya se ha comido el recorrido.

REGLAS ESTRICTAS:
- NO inventes ningún dato, cifra, etiqueta o empresa que no aparezca en los hechos de abajo.
- NO cambies ni reinterpretes la "Lectura global" que ya viene calculada — solo redáctala con tus palabras.
- NO des recomendaciones de compra ni de venta explícitas ("compra", "vende") — describe lo que dicen los números y deja la decisión al lector.
- NO añadas contexto de mercado que no esté en los hechos.
- Una o dos frases por empresa. Máximo 300 palabras.

HECHOS DE HOY:
{facts_bullets}

Resumen:"""

PROMPT_NOVELTIES = """Eres un asistente que redacta resúmenes financieros muy breves para un inversor particular que ya conoce su lista de seguimiento de empresas de valor y calidad.

Se te dan HECHOS ya verificados y calculados sobre las NOVEDADES de HOY respecto a ayer en esa lista: empresas que entran o salen, cambios de P/E o de deuda/patrimonio, cambios de la puntuación combinada Valor+Calidad y cruces del precio objetivo. Las métricas ya vienen etiquetadas (barata/cara, deuda alta/baja...) y las entradas/salidas traen una "Lectura global" ya calculada. Redáctalos de forma breve y legible en español, agrupando lo parecido (entradas y salidas, luego cambios), usando y reformulando esas etiquetas sin decidirlas tú.

REGLAS ESTRICTAS:
- NO inventes ningún dato, cifra, etiqueta o empresa que no aparezca en los hechos de abajo.
- NO cambies ni reinterpretes la "Lectura global" que ya viene calculada.
- NO des recomendaciones de compra ni de venta explícitas ("compra", "vende").
- NO añadas contexto de mercado que no esté en los hechos.
- Máximo 200 palabras.

HECHOS DE HOY:
{facts_bullets}

Resumen:"""


def call_ollama(facts: list, prompt_template: str) -> str:
    """Devuelve el resumen redactado por el modelo, o None si Ollama
    falla por cualquier motivo (no está corriendo, timeout, modelo no
    descargado, etc.) — el llamador debe tener un plan B."""

    facts_bullets = "\n".join(f"- {f}" for f in facts)
    prompt = prompt_template.format(facts_bullets=facts_bullets)

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


def build_digest_html(title: str, facts: list, narrative: str = None) -> str:
    """Caja HTML con el resumen (o la lista en bruto si no hay
    narrativa de la IA), para insertar en su sitio del email."""

    if narrative:
        body = f'<p style="margin: 0; color: #1a1a1a; font-size: 13px; line-height: 1.7;">{html.escape(narrative).replace(chr(10), "<br>")}</p>'
    else:
        items = "".join(f'<li style="margin-bottom: 4px;">{html.escape(f)}</li>' for f in facts)
        body = f'<ul style="margin: 0; padding-left: 18px; color: #1a1a1a; font-size: 13px; line-height: 1.7;">{items}</ul>'

    return f"""
    <tr>
      <td style="padding: 16px 28px; background-color: #fffbeb; border-top: 1px solid #f59e0b; border-bottom: 1px solid #f59e0b;">
        <span style="font-size: 14px; font-weight: 700; color: #92400e;">{html.escape(title)}</span>
        <div style="margin-top: 8px;">{body}</div>
      </td>
    </tr>
    """


def write_section(path: str, title: str, facts: list, prompt_template: str) -> None:
    """Redacta (Ollama, con fallback a lista) y guarda una sección; si no
    hay hechos borra el fichero para que el email no la muestre."""

    if not facts:
        if os.path.exists(path):
            os.remove(path)
        return

    print(f"{title}: {len(facts)} hechos")
    for fact in facts:
        print(f"  - {fact}")

    print(f"Pidiendo a Ollama ({OLLAMA_MODEL}) que redacte «{title}»...")
    narrative = call_ollama(facts, prompt_template)
    if narrative:
        print(narrative)
    else:
        print("Sin resumen de IA — se usará la lista de hechos en bruto.")

    with open(path, "w") as f:
        f.write(build_digest_html(title, facts, narrative))


def main():

    print("Guardando snapshot de hoy...")
    save_todays_snapshot()

    print("Detectando novedades respecto a ayer...")
    mover_facts, other_facts = detect_novelties_split()

    if os.path.exists(OLD_DIGEST_PATH):
        os.remove(OLD_DIGEST_PATH)

    if not mover_facts and not other_facts:
        print("Sin novedades reales hoy — no se enviará email.")
        with open(DECISION_PATH, "w") as f:
            f.write("SKIP")
        for path in (DIGEST_MOVERS_PATH, DIGEST_NOVELTIES_PATH):
            if os.path.exists(path):
                os.remove(path)
        return

    write_section(DIGEST_MOVERS_PATH, "📌 Top movers: qué dicen sus fundamentales", mover_facts, PROMPT_MOVERS)
    write_section(DIGEST_NOVELTIES_PATH, "📌 Resumen: novedades en calidad y valor", other_facts, PROMPT_NOVELTIES)

    with open(DECISION_PATH, "w") as f:
        f.write("SEND")

    print()
    print("Guardado. Hoy SÍ se enviará email.")


if __name__ == "__main__":
    main()

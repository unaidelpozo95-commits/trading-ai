"""
Diagnóstico de edinet-tools — QUÉ campos hay disponibles de verdad.

edinet-tools confirma en su documentación: net_income_owners,
net_assets_owners/net_assets_total, roe, net_sales,
operating_cash_flow, accounting_standard.

Lo que NECESITAMOS pero NO está confirmado en la documentación: EPS,
acciones en circulación, pasivo total, CapEx. Antes de construir el
fetcher completo (fetch_edinet_fundamentals.py) a ciegas asumiendo
nombres de campo, este script comprueba con UNA empresa real (Toyota,
7203, elegida porque es grande y estable, buen caso de prueba) qué
campos existen de verdad.

Requiere:
    pip install edinet-tools
    export EDINET_API_KEY=tu_clave   (gratuita, ver
        https://disclosure2.edinet-fsa.go.jp/)

USO:
    python edinet_data_check.py
    python edinet_data_check.py 6758   # otro ticker (Sony), sin ".T"
"""

import sys

try:
    import edinet_tools
except ImportError:
    raise SystemExit(
        "Falta la librería: pip install edinet-tools"
    )


TEST_TICKER = sys.argv[1] if len(sys.argv) > 1 else "7203"  # Toyota por defecto


print()
print(f"Buscando la empresa {TEST_TICKER} (esto funciona sin API key)...")

try:
    entity = edinet_tools.entity(TEST_TICKER)
except Exception as e:
    print(f"ERROR buscando la empresa: {e}")
    raise SystemExit(1)

print(f"Encontrada: {entity.name} ({entity.edinet_code})")

print()
print("Buscando informes anuales (Securities Report, doc_type=120) de los últimos 5 años...")
print("(esto SÍ necesita EDINET_API_KEY configurada)")

try:
    docs = entity.documents(doc_type="120", days=1825)
except Exception as e:
    print(f"ERROR obteniendo documentos: {e}")
    print("Comprueba que la variable de entorno EDINET_API_KEY está configurada.")
    raise SystemExit(1)

print(f"Encontrados: {len(docs)} informes")

if not docs:
    print("Sin informes — no se puede seguir con el diagnóstico.")
    raise SystemExit(1)

print()
print("=" * 70)
print("Parseando el más reciente...")
print("=" * 70)

doc = docs[0]

try:
    report = doc.parse()
except Exception as e:
    print(f"ERROR parseando el informe: {e}")
    raise SystemExit(1)

print()
print("CAMPOS TIPADOS DISPONIBLES (report.fields()):")
print("-" * 70)
try:
    for field in report.fields():
        print(f"  {field}")
except Exception as e:
    print(f"  (no se pudo listar: {e})")

print()
print("=" * 70)
print("COMPROBANDO LOS CAMPOS QUE NECESITAMOS PARA EL SCREENER")
print("=" * 70)

NEEDED = {
    "Beneficio neto": ["net_income_owners", "net_income_total", "net_income"],
    "Patrimonio neto": ["net_assets_owners", "net_assets_total", "stockholders_equity"],
    "ROE": ["roe"],
    "Ingresos": ["net_sales", "revenue"],
    "Flujo de caja operativo": ["operating_cash_flow"],
    "EPS (beneficio por acción)": ["eps", "earnings_per_share", "eps_basic", "eps_diluted"],
    "Acciones en circulación": ["shares_outstanding", "shares_issued", "total_shares_outstanding"],
    "Pasivo total": ["total_liabilities", "liabilities_total", "liabilities"],
    "CapEx": ["capital_expenditures", "capex", "purchase_of_property_plant_equipment"],
}

for label, candidate_names in NEEDED.items():
    found = None
    for name in candidate_names:
        value = getattr(report, name, None)
        if value is not None:
            found = (name, value)
            break
    if found:
        print(f"✓ {label}: encontrado como '{found[0]}' = {found[1]}")
    else:
        print(f"✗ {label}: NINGUNO de {candidate_names} existe o tiene valor")

print()
print("=" * 70)
print("VOLCADO COMPLETO (report.to_dict()) — por si algo se llama distinto")
print("=" * 70)
try:
    full_dict = report.to_dict()
    for key, value in full_dict.items():
        print(f"  {key}: {value}")
except Exception as e:
    print(f"  (no se pudo volcar: {e})")

print()
print("=" * 70)
print("Si algún campo necesario salió con ✗ arriba, busca en el volcado")
print("completo si existe con otro nombre, y pégame este resultado para")
print("ajustar fetch_edinet_fundamentals.py con los nombres reales.")
print("=" * 70)

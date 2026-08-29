"""
Envía el informe diario del screener por email (Gmail SMTP).

Lee las credenciales desde un archivo .env en la raíz del repo (NO se
sube a git — ver .gitignore). Crea .env con este contenido, con tus
datos reales:

    GMAIL_ADDRESS=tu_correo@gmail.com
    GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
    EMAIL_TO=tu_correo@gmail.com

La GMAIL_APP_PASSWORD es una "contraseña de aplicación" de Google
(no tu contraseña normal) — se genera en:
https://myaccount.google.com/apppasswords
(requiere tener activada la verificación en 2 pasos)

USO:
    python send_email_report.py
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


ENV_PATH = ".env"

REPORT_TXT = "data/value_quality_screener_report.txt"
REPORT_CSV = "data/value_quality_screener_report.csv"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def load_env(path: str = ENV_PATH) -> dict:

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No se encontró {path}. Créalo en la raíz del repo con:\n"
            f"  GMAIL_ADDRESS=tu_correo@gmail.com\n"
            f"  GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx\n"
            f"  EMAIL_TO=tu_correo@gmail.com"
        )

    env = {}

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()

    return env


def build_email(env: dict) -> MIMEMultipart:

    today = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart()
    msg["From"] = env["GMAIL_ADDRESS"]
    msg["To"] = env["EMAIL_TO"]

    if os.path.exists(REPORT_TXT):
        with open(REPORT_TXT) as f:
            body = f.read()
        msg["Subject"] = f"Screener Valor+Calidad — {today}"
    else:
        body = (
            "No se encontró el informe (data/value_quality_screener_report.txt).\n"
            "Revisa el log del pipeline para ver si algún paso falló."
        )
        msg["Subject"] = f"Screener Valor+Calidad — {today} (SIN INFORME)"

    msg.attach(MIMEText(body, "plain"))

    if os.path.exists(REPORT_CSV):
        with open(REPORT_CSV, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename=screener_{today}.csv",
        )
        msg.attach(part)

    return msg


def send_email(env: dict, msg: MIMEMultipart) -> None:

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(env["GMAIL_ADDRESS"], env["GMAIL_APP_PASSWORD"])
        server.send_message(msg)


def main():

    print("Cargando credenciales desde .env...")
    env = load_env()

    required = ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "EMAIL_TO"]
    missing = [k for k in required if k not in env]

    if missing:
        raise ValueError(f"Faltan estas claves en .env: {missing}")

    print("Construyendo email...")
    msg = build_email(env)

    print(f"Enviando a {env['EMAIL_TO']}...")
    send_email(env, msg)

    print("Email enviado correctamente.")


if __name__ == "__main__":
    main()

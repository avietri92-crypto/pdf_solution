import io
import os
import re

import pdfplumber
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI()
sicurezza = HTTPBearer()

API_TOKEN = os.environ["API_TOKEN"]
MAX_MB = int(os.environ.get("MAX_MB", "40"))               # dimensione massima del file
MAX_PAGINE = int(os.environ.get("MAX_PAGINE", "200"))      # pagine lette al massimo
MIN_CARATTERI = 30                                         # sotto questa soglia la pagina è "senza testo"
LEGGIBILI = re.compile(r"[A-Za-zÀ-ÿ0-9\s.,;:'\"()€%/\-–_]")


def controlla_token(credenziali: HTTPAuthorizationCredentials = Depends(sicurezza)):
    if credenziali.credentials != API_TOKEN:
        raise HTTPException(401, "Token non valido")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/estrai_testo", dependencies=[Depends(controlla_token)])
def estrai_testo(file: UploadFile = File(...)):
    dati = file.file.read()
    if len(dati) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File oltre {MAX_MB} MB")
    if b"%PDF" not in dati[:1024]:
        raise HTTPException(400, "Il file non è un PDF (se è un .p7m, va prima aperto)")

    pagine_testo = []
    senza_testo = []
    try:
        with pdfplumber.open(io.BytesIO(dati)) as pdf:
            totale = len(pdf.pages)
            for numero, pagina in enumerate(pdf.pages[:MAX_PAGINE], start=1):
                testo = pagina.extract_text() or ""
                if len(testo.strip()) < MIN_CARATTERI:
                    senza_testo.append(numero)
                pagine_testo.append(testo)
                pagina.close()   # libera la memoria della pagina
    except Exception as errore:
        raise HTTPException(400, f"PDF protetto o danneggiato: {errore}")

    lette = len(pagine_testo)
    testo = "\n\n".join(pagine_testo)

    if lette == 0 or len(senza_testo) == lette:
        tipo = "scansionato"
    elif senza_testo:
        tipo = "misto"
    else:
        tipo = "digitale"

    caratteri = len(testo)
    leggibilita = round(len(LEGGIBILI.findall(testo)) / caratteri, 3) if caratteri else 0

    return {
        "testo": testo,
        "tipo": tipo,                          # digitale | misto | scansionato
        "pagine": totale,
        "pagine_lette": lette,
        "pagine_senza_testo": senza_testo,     # numeri delle pagine da leggere con OCR
        "leggibilita": leggibilita,            # da 0 a 1: sotto 0.85 il testo è "a simboli"
        "troncato": totale > lette,
    }

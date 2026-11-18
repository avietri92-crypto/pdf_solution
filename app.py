import io
import os
import re

import pdfplumber
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI()
sicurezza = HTTPBearer()

API_TOKEN = os.environ["API_TOKEN"]
MAX_MB = int(os.environ.get("MAX_MB", "40"))
MAX_PAGINE = int(os.environ.get("MAX_PAGINE", "200"))
MIN_CARATTERI = 30        # sotto questa soglia la pagina è "senza testo"
MIN_ITALIANO = 0.08       # quota minima di parole comuni italiane per considerare la pagina leggibile

PAROLE_COMUNI = {
    "di", "e", "il", "la", "lo", "le", "gli", "i", "un", "una", "che", "per", "del", "della",
    "dei", "delle", "degli", "dello", "al", "alla", "ai", "alle", "in", "nel", "nella", "con",
    "non", "si", "da", "dal", "dalla", "o", "a", "è", "su", "sono", "come", "ed", "art",
}
PAROLA = re.compile(r"[a-zàèéìòù]+")


def controlla_token(credenziali: HTTPAuthorizationCredentials = Depends(sicurezza)):
    if credenziali.credentials != API_TOKEN:
        raise HTTPException(401, "Token non valido")


def pagina_leggibile(testo):
    """True se il testo della pagina sembra italiano vero, False se è vuoto o codificato."""
    if len(testo.strip()) < MIN_CARATTERI:
        return False
    if testo.count("(cid:") > 5:
        return False
    parole = PAROLA.findall(testo.lower())
    if len(parole) < 10:
        return False
    comuni = sum(1 for p in parole if p in PAROLE_COMUNI)
    return comuni / len(parole) >= MIN_ITALIANO


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

    pagine_buone = []
    da_ocr = []
    try:
        with pdfplumber.open(io.BytesIO(dati)) as pdf:
            totale = len(pdf.pages)
            for numero, pagina in enumerate(pdf.pages[:MAX_PAGINE], start=1):
                testo = pagina.extract_text() or ""
                if pagina_leggibile(testo):
                    pagine_buone.append(testo)
                else:
                    da_ocr.append(numero)
                pagina.close()
    except Exception as errore:
        raise HTTPException(400, f"PDF protetto o danneggiato: {errore}")

    lette = min(totale, MAX_PAGINE)
    if not da_ocr:
        tipo = "digitale"          # tutto leggibile: si usa il testo
    elif len(da_ocr) == lette:
        tipo = "da_ocr"            # niente di leggibile: va tutto all'OCR
    else:
        tipo = "misto"             # alcune pagine vanno all'OCR

    return {
        "testo": "\n\n".join(pagine_buone),   # solo le pagine leggibili
        "tipo": tipo,                          # digitale | misto | da_ocr
        "pagine": totale,
        "pagine_lette": lette,
        "pagine_da_ocr": da_ocr,               # scansionate o con testo codificato
        "troncato": totale > lette,
    }

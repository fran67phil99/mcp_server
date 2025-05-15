from fastapi import FastAPI
from fastapi.responses import JSONResponse
import json
import os
import csv # Importa il modulo csv
import pandas as pd # Se usi pandas per il CSV

app = FastAPI()

# Percorsi ai file dati all'interno del container
# La WORKDIR del Dockerfile è /app, e i file sono copiati lì.
STAGISTI_JSON_PATH = "stagisti.json" # Equivalente a /app/stagisti.json
MAUDEN_CSV_PATH = "mauden_employees.csv" # Equivalente a /app/mauden_employees.csv

@app.get("/stagisti")
async def get_stagisti():
    try:
        # Verifica se il file esiste prima di aprirlo
        if not os.path.exists(STAGISTI_JSON_PATH):
            return {"error": f"File stagisti non trovato in {STAGISTI_JSON_PATH}"}
        with open(STAGISTI_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        return {"error": f"Errore nel leggere o processare stagisti.json: {str(e)}"}

@app.get("/dati-csv")
async def get_dati_csv():
    try:
        if not os.path.exists(MAUDEN_CSV_PATH):
            return {"error": f"File CSV dei dipendenti non trovato in {MAUDEN_CSV_PATH}"}
        # Esempio con pandas, assicurati che pandas sia in requirements_dataset.txt
        df = pd.read_csv(MAUDEN_CSV_PATH)
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": f"Errore nel leggere o processare mauden_employees.csv: {str(e)}"}

# Blocco per avviare il server se eseguito direttamente (opzionale, utile per test)
if __name__ == "__main__":
    import uvicorn
    print("Avvio Dataset Server su http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
# filepath: c:\Users\fran6\Documents\Mauden\MCP_server\dataset.Dockerfile
FROM python:3.10-slim
WORKDIR /app

# Crea un file requirements specifico per dataset_server se non l'hai già fatto
# Esempio: requirements_dataset.txt
# fastapi
# uvicorn[standard]
# pandas (se dataset_server.py usa pandas per leggere il CSV)
COPY requirements_dataset.txt .
RUN pip install --no-cache-dir -r requirements_dataset.txt

COPY dataset_server.py .

# Copia i file dati nella directory di lavoro /app del container
COPY stagisti.json .
COPY mauden_employees.csv .
COPY history_data/ ./history_data/
# Se i file sono in una sottodirectory 'data_files' localmente:
# COPY data_files/stagisti.json .
# COPY data_files/mauden_employees.csv .

EXPOSE 8000
CMD ["uvicorn", "dataset_server:app", "--host", "0.0.0.0", "--port", "8000"]
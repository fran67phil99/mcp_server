# 1. Immagine Base
# Partiamo da un'immagine Python ufficiale. La versione "slim" è più leggera.
# Assicurati che la versione di Python corrisponda a quella del tuo ambiente di sviluppo.
FROM python:3.10-slim

# 2. Imposta la Directory di Lavoro
# Definisce la directory di lavoro all'interno del container.
# Tutti i comandi successivi (COPY, RUN, CMD) saranno eseguiti in questo contesto.
WORKDIR /app

# 3. Copia il file delle dipendenze
# Copia prima requirements.txt. Docker memorizza in cache questo layer.
# Se requirements.txt non cambia, Docker riutilizzerà il layer dell'installazione delle dipendenze,
# velocizzando le build successive.
COPY requirements.txt requirements.txt

# 4. Installa le Dipendenze
# Installa i pacchetti Python specificati in requirements.txt.
# --no-cache-dir riduce la dimensione dell'immagine non salvando la cache di pip.
# --upgrade pip assicura che pip sia aggiornato.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copia il Codice dell'Applicazione
# Copia tutto il contenuto della directory corrente (dove si trova il Dockerfile)
# nella directory di lavoro /app del container.
# Questo includerà la tua directory 'frontend' e altri file.
COPY . .

# 6. Esponi la Porta
# Informa Docker che il container ascolterà sulla porta specificata al runtime.
# La tua applicazione Flask in frontend-application.py è configurata per girare sulla porta 5000.
# Se usi Gunicorn, potresti voler cambiare questa porta (es. 8080) e il comando CMD.
EXPOSE 5000

# 8. Comando di Avvio
# Specifica il comando da eseguire quando il container viene avviato.

# Opzione B: Usare Gunicorn (RACCOMANDATO per produzione)
# Gunicorn è un server WSGI Python più robusto per la produzione.
# --bind 0.0.0.0:5000 : Gunicorn ascolterà su tutte le interfacce sulla porta 5000.
# --workers 1 : Numero di processi worker. Per SocketIO con eventlet/gevent, spesso 1 è sufficiente
#               a meno che tu non abbia carichi molto elevati e una strategia di scaling orizzontale.
# --worker-class eventlet : Fondamentale per Flask-SocketIO per gestire le connessioni WebSocket.
#                           Assicurati che 'eventlet' (o 'gevent') sia in requirements.txt.
# --timeout 3600 : Timeout per i worker (in secondi). Aumentato per supportare connessioni lunghe di Socket.IO.
# frontend.frontend-application:app : Percorso al modulo e all'istanza dell'app Flask.
#                                     'frontend' è la directory, 'frontend-application' è il file .py,
#                                     'app' è la variabile Flask (app = Flask(__name__)).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--worker-class", "eventlet", "--timeout", "3600", "frontend-application:app"]
import asyncio
import sys
import os
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
from dotenv import load_dotenv
from contextlib import redirect_stdout
import io
import traceback
import threading
import atexit
from typing import Dict, List, Any, Optional

# Carica le variabili d'ambiente SUBITO
load_dotenv()

# Definisci la variabile globale per la chiave API OpenAI
OPENAI_API_KEY_GLOBAL: Optional[str] = os.getenv('OPENAI_API_KEY') # Leggi la chiave OpenAI
if not OPENAI_API_KEY_GLOBAL:
    print("ATTENZIONE CRITICA: OPENAI_API_KEY non caricata da .env all'avvio!", file=sys.stderr)
else:
    print(f"OPENAI_API_KEY caricata all'avvio: {'*'*len(OPENAI_API_KEY_GLOBAL[:-4])}{OPENAI_API_KEY_GLOBAL[-4:]}")

# Importa la classe MCPClient dal modulo principale
try:
    from mcp_client import MCPClient # Dovrebbe funzionare direttamente ora
except ImportError as e:
    print(f"Errore: Impossibile importare MCPClient da mcp_client.py (nella stessa directory): {e}", file=sys.stderr)
    # La classe fittizia rimane come fallback
    class MCPClient:
        def __init__(self, *args, **kwargs): print("ERRORE: Classe MCPClient Fittizia.", file=sys.stderr)
        async def initialize_connections(self, *args, **kwargs): raise NotImplementedError("MCPClient non caricato.")
        async def call_openai_with_tools(self, *args, **kwargs): raise NotImplementedError("MCPClient non caricato.")
        async def reset_conversation(self, *args, **kwargs): raise NotImplementedError("MCPClient non caricato.")
        async def close_connections(self, *args, **kwargs): pass
        async def cleanup(self, *args, **kwargs): pass

# --- Gestione Event Loop Asyncio Dedicato ---
asyncio_loop = None
loop_thread = None

def start_asyncio_loop():
    global asyncio_loop
    try:
        asyncio_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(asyncio_loop)
        print("Starting dedicated asyncio event loop...")
        asyncio_loop.run_forever()
    finally:
        if asyncio_loop and asyncio_loop.is_running():
             asyncio_loop.close()
        print("Asyncio event loop stopped.")

def stop_asyncio_loop():
    if asyncio_loop and asyncio_loop.is_running():
        print("Stopping asyncio event loop...")
        asyncio_loop.call_soon_threadsafe(asyncio_loop.stop)
    if loop_thread:
        print("Waiting for asyncio thread to join...")
        loop_thread.join(timeout=5)
        if loop_thread.is_alive():
             print("Warning: Asyncio thread did not join cleanly.")
        else:
             print("Asyncio thread joined.")

loop_thread = threading.Thread(target=start_asyncio_loop, daemon=True, name="AsyncioLoopThread")
loop_thread.start()
atexit.register(stop_asyncio_loop)
# --- Fine Gestione Event Loop ---

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chatbot-secret-key')
socketio = SocketIO(app, cors_allowed_origins="*")

mcp_client_status: Dict[str, Dict[str, Any]] = {}

def load_mcp_server_configs() -> List[Dict[str, Any]]:
    # mcp_servers.json è nella stessa directory di questo script (frontend/)
    # All'interno del container, questo script è in /app/frontend/
    script_dir = os.path.dirname(os.path.abspath(__file__)) # Sarà /app/frontend
    config_file_path = os.path.join(script_dir, "mcp_servers.json") # /app/frontend/mcp_servers.json
    
    print(f"Tentativo di caricamento configurazione server da: {config_file_path}") # Log per debug
    try:
        with open(config_file_path, "r") as f:
            config = json.load(f)
            return config.get("available_mcp_servers", [])
    except FileNotFoundError:
        print(f"ERRORE: File '{config_file_path}' non trovato.", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print(f"ERRORE: Errore nel decodificare '{config_file_path}'. Assicurati che sia JSON valido.", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Errore caricando la configurazione dei server MCP da '{config_file_path}': {e}", file=sys.stderr)
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get_available_mcp_servers') # O un evento socketio
def get_available_mcp_servers():
    servers = load_mcp_server_configs()
    # Rimuovi l'URL se non vuoi esporlo direttamente al client non autenticato,
    # anche se per la connessione MCP potrebbe essere necessario.
    # Per ora lo lasciamo, ma valuta la sicurezza.
    return jsonify(servers)

# ...oppure, come evento Socket.IO al momento della connessione del client:
@socketio.on('request_server_list') # Il client emetterà questo evento
def handle_request_server_list():
    session_id = request.sid
    servers = load_mcp_server_configs()
    print(f"Invio lista server disponibili a {session_id}")
    emit('available_servers', {'servers': servers}, room=session_id)

@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    print(f"Client connected: {session_id}")
    mcp_client_status[session_id] = {'client': None, 'status': 'disconnected'}
    emit('status', {'message': 'Connesso al server frontend. Pronto a inizializzare i client MCP.'})

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    print(f"Client disconnected: {session_id}")
    client_data = mcp_client_status.pop(session_id, None)
    if client_data and client_data.get('client') and client_data.get('status') == 'connected': # Controlla lo stato 'connected'
        print(f"Avvio cleanup per MCP client {session_id}...")
        client = client_data['client']

        def run_async_cleanup():
            if not asyncio_loop: return
            # Usa close_connections o un metodo di cleanup generico se lo hai
            coro = client.close_connections() # Assumendo che close_connections faccia il cleanup necessario
            future = asyncio.run_coroutine_threadsafe(coro, asyncio_loop)
            try:
                future.result(timeout=10)
                print(f"Cleanup completato per MCP client {session_id}.")
            except TimeoutError:
                 print(f"Timeout durante cleanup per SID {session_id}.")
            except Exception as e:
                print(f"--- Errore durante cleanup per SID {session_id} (via run_coroutine_threadsafe) ---")
                traceback.print_exception(type(e), e, e.__traceback__)
        
        socketio.start_background_task(run_async_cleanup)
    else:
         print(f"Nessun client MCP attivo o connesso trovato per SID {session_id} da pulire.")

@socketio.on('initialize')
def initialize_mcp(data): # data ora conterrà { 'selected_server_ids': ['id1', 'id2'] }
    session_id = request.sid
    selected_server_ids = data.get('selected_server_ids', [])

    if not selected_server_ids:
        emit('error', {'message': 'Nessun server MCP selezionato per l\'inizializzazione.'})
        return

    current_status_info = mcp_client_status.get(session_id)
    # ... (logica di controllo stato esistente) ...

    all_server_configs = load_mcp_server_configs()
    if not all_server_configs:
        emit('error', {'message': 'Nessun server MCP configurato o errore nel caricamento della configurazione.'})
        return

    # Filtra i server_configs basati sugli ID selezionati
    server_configs_to_use = [
        config for config in all_server_configs if config['id'] in selected_server_ids
    ]

    if not server_configs_to_use:
        emit('error', {'message': 'Gli ID dei server selezionati non corrispondono a nessuna configurazione valida.'})
        return
    
    # Salva i server selezionati per questa sessione, se necessario per riferimento futuro
    if session_id in mcp_client_status:
        mcp_client_status[session_id]['selected_servers_config'] = server_configs_to_use

    try:
        # Passa solo i server selezionati al client MCP
        client = MCPClient(session_id=session_id, server_configs=server_configs_to_use, api_key=OPENAI_API_KEY_GLOBAL)
        mcp_client_status[session_id]['client'] = client
        mcp_client_status[session_id]['status'] = 'initializing'
    except Exception as e:
        # ... (gestione errore esistente) ...
        return

    num_servers_to_connect = len(server_configs_to_use)
    emit('status', {'message': f'Inizializzazione client MCP per {session_id}... Tentativo di connessione a {num_servers_to_connect} server(s) selezionati.'})
    print(f"Inizializzazione client MCP per {session_id}... Tentativo di connessione a {num_servers_to_connect} server(s): {[sc['name'] for sc in server_configs_to_use]}")

    # ... (il resto della logica run_async_connect_all rimane simile, usando 'client' e 'num_servers_to_connect') ...

    def run_async_connect_all():
        if not asyncio_loop:
            print("Errore: Event loop asyncio non disponibile.", file=sys.stderr)
            socketio.emit('error', {'message': 'Errore interno del server (event loop)'}, room=session_id)
            mcp_client_status[session_id]['status'] = 'failed'
            return
        try:
            coro = client.initialize_connections()
            future = asyncio.run_coroutine_threadsafe(coro, asyncio_loop)
            future.result() 

            if client.sessions: 
                connected_servers_count = len(client.sessions)
                print(f"MCP client {session_id} connesso con successo a {connected_servers_count} di {num_servers_to_connect} server(s).")
                mcp_client_status[session_id]['status'] = 'connected' 
                mcp_client_status[session_id]['connected_servers'] = connected_servers_count
                mcp_client_status[session_id]['total_tools'] = len(client.all_tools_for_llm)
                socketio.emit('mcp_initialized', {
                    'message': f'Chatbot inizializzato con {connected_servers_count} server(s) e {len(client.all_tools_for_llm)} tool disponibili (OpenAI).', # Messaggio aggiornato
                    'tools_available': len(client.all_tools_for_llm) > 0
                }, room=session_id)
            else:
                print(f"MCP client {session_id}: Nessuna sessione MCP attiva dopo il tentativo di connessione.", file=sys.stderr)
                mcp_client_status[session_id]['status'] = 'failed_connection'
                socketio.emit('error', {'message': 'Impossibile connettersi ai server MCP.'}, room=session_id)
        except Exception as e:
            print(f"--- Errore Connessione Multipla MCP per SID {session_id} ---", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            error_message = f'Errore durante la connessione ai server MCP: {type(e).__name__} - {str(e)}'
            socketio.emit('error', {'message': error_message}, room=session_id)
            mcp_client_status[session_id]['status'] = 'failed'
            # Non resettare a None, mantieni lo stato 'failed'
            # mcp_client_status[session_id] = None 

    socketio.start_background_task(run_async_connect_all)

@socketio.on('send_message')
def handle_send_message_event(data):
    session_id = request.sid
    user_message = data.get('message', '').strip()

    if not user_message:
        emit('error', {'message': 'Messaggio vuoto non inviato.'})
        return

    client_info = mcp_client_status.get(session_id)
    client: Optional[MCPClient] = None 
    current_status: Optional[str] = None

    if client_info:
        client = client_info.get('client')
        current_status = client_info.get('status')
    
    if not client or current_status != 'connected':
        log_status_message = current_status if current_status else 'N/A (client_info non trovato)'
        if not client:
            log_status_message = 'Client non trovato (None)'
        emit('error', {'message': 'Errore: MCP non inizializzato o connessione fallita. Clicca su "Inizializza".'})
        print(f"Tentativo di invio messaggio da SID {session_id} fallito. Stato: {log_status_message}")
        return
    
    emit('status', {'message': 'Elaborazione query in corso con OpenAI...'}) # Messaggio aggiornato
    print(f"Messaggio ricevuto da {session_id}: '{user_message}'. Inoltro a MCPClient (OpenAI).")

    def run_async_process():
        try:
            # Chiama il metodo adattato per OpenAI
            response_text = asyncio.run_coroutine_threadsafe(
                client.call_openai_with_tools(user_message), # Metodo aggiornato
                asyncio_loop
            ).result() 

            socketio.emit('new_message', {'sender': 'bot', 'text': response_text}, room=session_id)
        except Exception as e:
            print(f"--- Errore Elaborazione Query per SID {session_id} (OpenAI) ---", file=sys.stderr) # Log aggiornato
            traceback.print_exc(file=sys.stderr)
            error_message = f'Errore durante l\'elaborazione (OpenAI): {type(e).__name__} - {str(e)}' # Messaggio aggiornato
            socketio.emit('error', {'message': error_message}, room=session_id)
        finally:
             socketio.emit('status', {'message': 'Pronto per la prossima query.'}, room=session_id)

    socketio.start_background_task(run_async_process)

@socketio.on('reset_conversation')
def reset_conversation():
    session_id = request.sid
    client_info = mcp_client_status.get(session_id)
    client: Optional[MCPClient] = None
    current_status: Optional[str] = None

    if client_info:
        client = client_info.get('client')
        current_status = client_info.get('status')

    if not client or current_status != 'connected':
        emit('error', {'message': 'Errore: MCP non inizializzato.'})
        return

    emit('status', {'message': 'Reset della conversazione in corso...'})
    print(f"Reset conversazione per {session_id}")

    def run_async_reset():
        if not asyncio_loop:
            print("Errore: Event loop asyncio non disponibile.")
            socketio.emit('error', {'message': 'Errore interno del server (event loop)'}, room=session_id)
            socketio.emit('status', {'message': 'Errore interno.'}, room=session_id)
            return
        try:
            # Il metodo reset_conversation in MCPClient dovrebbe ora resettare self.chat_history
            coro = client.reset_conversation() 
            future = asyncio.run_coroutine_threadsafe(coro, asyncio_loop)
            future.result() 
            print(f"Conversazione resettata per {session_id}.")
            socketio.emit('status', {'message': 'Conversazione resettata.'}, room=session_id)
            socketio.emit('conversation_reset', room=session_id)
        except Exception as e:
            print(f"--- Errore Reset Conversazione per SID {session_id} ---")
            traceback.print_exception(type(e), e, e.__traceback__)
            error_message = f'Errore durante il reset: {type(e).__name__} - {str(e)}'
            socketio.emit('error', {'message': error_message}, room=session_id)
        finally:
             socketio.emit('status', {'message': 'Pronto.'}, room=session_id)

    socketio.start_background_task(run_async_reset)

if __name__ == '__main__':
    print("Avvio del server Flask-SocketIO...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
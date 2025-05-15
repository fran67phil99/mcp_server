# test_mcp_import.py
import inspect
import sys
print(f"Python sys.path: {sys.path}") # Stampa il sys.path per debug

try:
    print("Tentativo di importare ClientSession da mcp.base...")
    from mcp.base import ClientSession # <--- MODIFICA QUI
    
    print(f"Modulo di ClientSession (da mcp.base): {ClientSession.__module__}")
    print(f"File di ClientSession (da mcp.base): {inspect.getfile(ClientSession)}")
    print(f"Firma di ClientSession.__init__ (da mcp.base): {inspect.signature(ClientSession.__init__)}")

    try:
        session = ClientSession("test_id")
        print("Istanza di ClientSession (da mcp.base) creata con successo con solo client_id.")
    except TypeError as e:
        print(f"Errore durante l'istanza di ClientSession (da mcp.base): {e}")

except ImportError:
    print("ERRORE: Impossibile importare ClientSession da mcp.base.")
    print("Questo suggerisce che la libreria FastMCP non è installata correttamente o non fornisce mcp.base come previsto.")
    print("Provo a importare ClientSession da mcp (potrebbe essere quella sbagliata)...")
    try:
        from mcp import ClientSession as RootClientSession
        print(f"Modulo di RootClientSession (da mcp): {RootClientSession.__module__}")
        print(f"File di RootClientSession (da mcp): {inspect.getfile(RootClientSession)}")
        print(f"Firma di RootClientSession.__init__ (da mcp): {inspect.signature(RootClientSession.__init__)}")
        try:
            root_session = RootClientSession("test_id")
        except TypeError as e_root:
            print(f"Errore durante l'istanza di RootClientSession (da mcp): {e_root}")

    except ImportError:
        print("ERRORE: Impossibile importare ClientSession anche da mcp.")
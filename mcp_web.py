from typing import Any, Dict, List
import httpx
from mcp.server.fastmcp import FastMCP
import sys
import uvicorn
import os

# Inizializza il server MCP
mcp = FastMCP("stagisti-mcp", "0.1.0")

# Endpoint del dataset server - leggilo da una variabile d'ambiente
DATASET_API_BASE = os.getenv("DATASET_API_BASE_URL", "http://127.0.0.1:8000") # Default per test locali

@mcp.tool()
async def get_stagisti_mcp() -> Dict[str, Any]:
    """Recupera la lista degli stagisti di Mauden dal dataset server tramite REST API."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{DATASET_API_BASE}/stagisti")
            response.raise_for_status()
            data = response.json()

            # Controllo errore più robusto
            if not data or ("error" in data and isinstance(data, dict) and data.get("error")):
                raise ValueError("Errore o risposta vuota dal server dataset (/stagisti): " + str(data))

            # Assicura che venga restituito un dizionario, in linea con il type hint
            if isinstance(data, list):
                return {"stagisti_list": data} # Avvolgi la lista in un dizionario
            elif not isinstance(data, dict):
                # Se non è una lista né un dizionario (improbabile per JSON valido ma per sicurezza)
                return {"result": data}
            # Se è già un dizionario (e non un errore), restituiscilo direttamente
            return data

        except httpx.RequestError as exc:
             print(f"Errore HTTPX durante la chiamata a {exc.request.url!r} per /stagisti: {exc}", file=sys.stderr)
             raise ValueError(f"Errore di rete nel contattare il server dataset (/stagisti): {exc}") from exc
        except Exception as e:
             print(f"Errore generico in get_stagisti_mcp: {e}", file=sys.stderr)
             raise ValueError(f"Errore imprevisto in get_stagisti_mcp: {e}") from e

@mcp.tool()
async def get_dati_csv_mcp() -> Dict[str, Any]:
    """Recupera i dati di tutti i dipendenti di Mauden dal dataset server tramite REST API (originati da CSV)."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{DATASET_API_BASE}/dati-csv")
            response.raise_for_status()
            data = response.json()
            # Controllo errore più robusto
            if not data or ("error" in data and isinstance(data, dict) and data.get("error")):
                raise ValueError("Errore o risposta vuota dal server dataset (/dati-csv): " + str(data))
            
            # Assicurati che venga restituito un dizionario
            if not isinstance(data, dict):
                 return {"csv_data_result": data}
            return data
        except httpx.RequestError as exc:
             print(f"Errore HTTPX durante la chiamata a {exc.request.url!r} per /dati-csv: {exc}", file=sys.stderr)
             raise ValueError(f"Errore di rete nel contattare il server dataset (/dati-csv): {exc}") from exc
        except Exception as e:
            print(f"Errore generico in get_dati_csv_mcp: {e}", file=sys.stderr)
            raise ValueError(f"Errore imprevisto durante il recupero dei dati CSV: {e}") from e


# Blocco main
if __name__ == "__main__":
    mcp_host = "0.0.0.0"
    mcp_port = 8080
    app_string = "mcp_web:mcp.sse_app"

    try:
        uvicorn.run(app_string, host=mcp_host, port=mcp_port, reload=False, log_level="debug")
    except Exception as e:
         print(f"Failed to start MCP server with Uvicorn: {e}", file=sys.stderr)
         import traceback
         traceback.print_exc(file=sys.stderr)
         sys.exit(1)

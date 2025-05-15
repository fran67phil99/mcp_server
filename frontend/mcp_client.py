import asyncio
import sys
import traceback
from typing import List, Dict, Optional, Any, Coroutine, AsyncGenerator
from contextlib import AsyncExitStack
import json # Aggiunto per la gestione degli argomenti dei tool OpenAI

from fastmcp.client.client import Client as FastMCPUpstreamClient
from fastmcp.client.transports import SSETransport
import mcp.types

# Import per OpenAI
import openai # Rimosso google.generativeai e google.genai.types

# Funzione helper (invariata)
def mcp_schema_to_openapi(mcp_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not mcp_schema or 'properties' not in mcp_schema or not mcp_schema.get('properties'):
        return {"type": "object", "properties": {}}
    return {
        "type": mcp_schema.get("type", "object"),
        "properties": mcp_schema.get("properties", {}),
        "required": mcp_schema.get("required", [])
    }

class MCPClient:
    def __init__(self, session_id: str, server_configs: List[Dict[str, str]], api_key: Optional[str] = None):
        self.user_session_id = session_id
        self.server_configs = server_configs
        self.sessions: Dict[str, FastMCPUpstreamClient] = {}
        self.all_tools_for_llm: List[Dict[str, Any]] = [] # Modificato per il formato OpenAI
        self.tool_to_server_map: Dict[str, str] = {}
        self.exit_stack = AsyncExitStack()
        self.openai_api_key = api_key # Rinominato per chiarezza
        
        self.openai_client: Optional[openai.AsyncOpenAI] = None
        self.chat_history: List[Dict[str, Any]] = [] # Per mantenere la history della chat per OpenAI

        if self.openai_api_key:
            self.openai_client = openai.AsyncOpenAI(api_key=self.openai_api_key)
            print(f"MCPClient {self.user_session_id}: Client OpenAI inizializzato.")
        else:
            print(f"MCPClient {self.user_session_id}: ATTENZIONE - Chiave API OpenAI NON configurata.", file=sys.stderr)
        
        # Non inizializziamo un modello specifico qui, lo faremo al momento della chiamata
        # o in initialize_connections se necessario per configurare i tool globalmente.

    async def initialize_connections(self):
        # await self.exit_stack.aclose() # Può causare problemi se chiamato prima di enter_async_context
        self.exit_stack = AsyncExitStack() 
        self.sessions = {}
        self.all_tools_for_llm = []
        self.tool_to_server_map = {}
        self.chat_history = [] # Resetta la history se si reinizializzano le connessioni

        if not self.server_configs:
            print(f"MCPClient {self.user_session_id}: Nessuna configurazione server MCP fornita.", file=sys.stderr)
            return

        if not self.openai_client:
            print(f"MCPClient {self.user_session_id}: Client OpenAI non inizializzato (manca API key?). Impossibile procedere.", file=sys.stderr)
            return

        for server_config in self.server_configs:
            server_id = server_config['id']
            server_url = server_config['url'] 
            server_name = server_config.get("name", server_id)

            print(f"MCPClient {self.user_session_id}: Tentativo connessione a '{server_name}' ({server_url})...")
            try:
                transport = SSETransport(url=server_url)
                mcp_upstream_client = FastMCPUpstreamClient(transport=transport)
                await self.exit_stack.enter_async_context(mcp_upstream_client)
                self.sessions[server_id] = mcp_upstream_client
                print(f"MCPClient {self.user_session_id}: Connesso a '{server_name}'. In attesa di ottenere i tool...")

                tools_list_from_server: List[mcp.types.Tool] = await mcp_upstream_client.list_tools()
                
                if tools_list_from_server:
                    print(f"MCPClient {self.user_session_id}: Ricevuti {len(tools_list_from_server)} tool da '{server_name}'.")
                    self._aggregate_tools_for_openai(tools_list_from_server, server_id, server_name)
                else:
                    print(f"MCPClient {self.user_session_id}: Nessun tool ricevuto da '{server_name}'.")
            except Exception as e:
                print(f"MCPClient {self.user_session_id}: Errore durante la connessione/configurazione per '{server_name}' ({server_url}): {e}", file=sys.stderr)
                traceback.print_exc()
        
        if not self.sessions:
            print(f"MCPClient {self.user_session_id}: Nessuna connessione ai server MCP riuscita.", file=sys.stderr)
        else:
            print(f"MCPClient {self.user_session_id}: Tool OpenAI aggregati finali: {len(self.all_tools_for_llm)} tool.")
            # Non c'è una "chat_session" da inizializzare come in Gemini; la history è gestita manualmente.

    def _aggregate_tools_for_openai(self, tools_from_server: List[mcp.types.Tool], server_id: str, server_name: str):
        for tool_obj in tools_from_server:
            tool_name = tool_obj.name
            if not tool_name:
                print(f"AVVISO: Tool da '{server_name}' senza nome: {tool_obj}", file=sys.stderr)
                continue

            parameters_schema_dict: Optional[Dict[str, Any]] = None
            if tool_obj.inputSchema:
                parameters_schema_dict = tool_obj.inputSchema 

            openapi_params = mcp_schema_to_openapi(parameters_schema_dict)

            # Formato tool per OpenAI
            openai_tool_definition = {
                "type": "function",
                "function": {
                    "name": f"{server_id}__{tool_name}", # Nome univoco per OpenAI
                    "description": tool_obj.description or f"Tool {tool_name} from server {server_name}",
                    "parameters": openapi_params
                }
            }
            self.all_tools_for_llm.append(openai_tool_definition)
            self.tool_to_server_map[openai_tool_definition["function"]["name"]] = server_id
            print(f"MCPClient {self.user_session_id}: Aggregato tool OpenAI: {openai_tool_definition['function']['name']}")

    async def call_openai_with_tools(self, prompt: str, model_name: str = "gpt-4.1-2025-04-14") -> str: # Rinominato e modificato
        if not self.openai_client:
            print(f"MCPClient {self.user_session_id}: Client OpenAI non inizializzato.", file=sys.stderr)
            return "Errore: Client OpenAI non inizializzato."

        # Aggiungi il prompt dell'utente alla history
        self.chat_history.append({"role": "user", "content": prompt})
        
        print(f"MCPClient {self.user_session_id}: Invio prompt a OpenAI: '{prompt}' con {len(self.all_tools_for_llm)} tools.")

        try:
            while True: # Ciclo per gestire le chiamate ai tool
                print(f"MCPClient {self.user_session_id}: Chiamata a OpenAI. History attuale: {len(self.chat_history)} messaggi.")
                completion = await self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=self.chat_history,
                    tools=self.all_tools_for_llm if self.all_tools_for_llm else None, # Invia i tool solo se ce ne sono
                    tool_choice="auto" if self.all_tools_for_llm else None
                )
                
                response_message = completion.choices[0].message
                self.chat_history.append(response_message.model_dump(exclude_none=True)) # Aggiungi la risposta dell'assistente alla history

                if response_message.tool_calls:
                    print(f"MCPClient {self.user_session_id}: OpenAI ha richiesto {len(response_message.tool_calls)} chiamate ai tool.")
                    tool_responses_for_openai = []
                    for tool_call in response_message.tool_calls:
                        function_name = tool_call.function.name
                        function_args_str = tool_call.function.arguments
                        try:
                            function_args = json.loads(function_args_str)
                        except json.JSONDecodeError:
                            print(f"MCPClient {self.user_session_id}: Errore nel decodificare gli argomenti JSON per {function_name}: {function_args_str}", file=sys.stderr)
                            tool_responses_for_openai.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"error": "Invalid arguments JSON", "details": function_args_str})
                            })
                            continue
                        
                        print(f"MCPClient {self.user_session_id}: Tool richiesto: {function_name} con argomenti: {function_args}")

                        original_server_id = self.tool_to_server_map.get(function_name)
                        if not original_server_id:
                            print(f"MCPClient {self.user_session_id}: Errore: Tool '{function_name}' non mappato.", file=sys.stderr)
                            tool_responses_for_openai.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"error": f"Tool '{function_name}' non mappato a un server MCP."})
                            })
                            continue

                        mcp_upstream_service_client = self.sessions.get(original_server_id)
                        if not mcp_upstream_service_client:
                            print(f"MCPClient {self.user_session_id}: Errore: Server MCP '{original_server_id}' non trovato.", file=sys.stderr)
                            tool_responses_for_openai.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"error": f"Server MCP '{original_server_id}' per il tool '{function_name}' non trovato."})
                            })
                            continue
                        
                        actual_tool_name = function_name.split("__", 1)[1] if "__" in function_name else function_name
                        
                        try:
                            tool_mcp_response_content: list[mcp.types.Content] = await mcp_upstream_service_client.call_tool(
                                name=actual_tool_name, 
                                arguments=function_args
                            )
                            
                            tool_output_for_openai = ""
                            if tool_mcp_response_content and isinstance(tool_mcp_response_content[0], mcp.types.TextContent):
                                tool_output_for_openai = tool_mcp_response_content[0].text
                            elif tool_mcp_response_content: # Se non è TextContent, prova a serializzarlo
                                tool_output_for_openai = str(tool_mcp_response_content[0]) 
                            else:
                                tool_output_for_openai = "Il tool non ha restituito contenuto."
                            
                            print(f"MCPClient {self.user_session_id}: Risultato tool '{actual_tool_name}': {tool_output_for_openai}")
                            tool_responses_for_openai.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"result": tool_output_for_openai}) # OpenAI si aspetta una stringa, spesso JSON.
                            })
                        except Exception as tool_exc:
                            print(f"MCPClient {self.user_session_id}: Errore durante la chiamata al tool MCP '{actual_tool_name}': {tool_exc}", file=sys.stderr)
                            traceback.print_exc()
                            tool_responses_for_openai.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"error": f"Eccezione durante l'esecuzione del tool: {str(tool_exc)}"})
                            })
                    
                    # Aggiungi tutte le risposte dei tool alla history
                    for tool_response in tool_responses_for_openai:
                        self.chat_history.append(tool_response)
                    # Continua il ciclo per inviare le risposte dei tool a OpenAI
                
                elif response_message.content:
                    final_text = response_message.content
                    print(f"MCPClient {self.user_session_id}: Risposta finale da OpenAI: {final_text}")
                    return final_text
                else:
                    # Caso inatteso (es. no content e no tool_calls)
                    print(f"MCPClient {self.user_session_id}: Risposta inattesa da OpenAI: {response_message.model_dump_json(indent=2)}", file=sys.stderr)
                    return "Errore: Risposta inattesa da OpenAI."

        except openai.APIError as e: # Gestione specifica degli errori OpenAI
            print(f"MCPClient {self.user_session_id}: Errore API OpenAI: {e}", file=sys.stderr)
            traceback.print_exc()
            # Rimuovi gli ultimi messaggi (prompt e tentativi di risposta) se c'è un errore API
            if self.chat_history and self.chat_history[-1]["role"] == "user":
                 self.chat_history.pop() # Rimuovi il prompt dell'utente che ha causato l'errore
            return f"Si è verificato un errore API OpenAI: {e}"
        except Exception as e:
            print(f"MCPClient {self.user_session_id}: Errore generico durante la chiamata a OpenAI o la gestione dei tool: {e}", file=sys.stderr)
            traceback.print_exc()
            return f"Si è verificato un errore generico: {e}"

    async def close_connections(self):
        print(f"MCPClient {self.user_session_id}: Chiusura di tutte le connessioni MCP...")
        try:
            await self.exit_stack.aclose()
        except RuntimeError as e:
            if "Attempted to exit cancel scope in a different task" in str(e):
                print(f"MCPClient {self.user_session_id}: Errore gestito durante aclose (anyio cancel scope): {e}", file=sys.stderr)
            else:
                raise
        except Exception as e:
            print(f"MCPClient {self.user_session_id}: Eccezione generica durante aclose: {e}", file=sys.stderr)
            traceback.print_exc()
        finally:
            self.sessions = {} # Assicurati che le sessioni siano pulite
            print(f"MCPClient {self.user_session_id}: Connessioni MCP chiuse (o tentativo di chiusura completato).")

    async def reset_conversation(self):
        """Resetta la history della chat per la sessione corrente con OpenAI."""
        self.chat_history = []
        print(f"MCPClient {self.user_session_id}: History della chat OpenAI resettata.")
        # Non c'è una "chat_session" da resettare come in Gemini,
        # la history è gestita manualmente.
        # Non è necessario restituire nulla o fare altro per OpenAI in questo caso.

    # Questi metodi potrebbero non essere più direttamente applicabili o necessitano di una riscrittura completa
    # per l'approccio di OpenAI che gestisce la history in modo diverso.
    async def send_message_to_gemini(self, message_text: str, current_tools_for_llm: List[Dict[str, Any]], current_tool_config: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"message": "send_message_to_gemini (ora obsoleto) needs to be adapted or removed for OpenAI"} 

    async def process_tool_response(self, tool_call_id: str, function_name: str, response_data: Dict[str, Any], is_error: bool) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"message": "process_tool_response (ora obsoleto) needs to be adapted or removed for OpenAI"}

    async def close_all_sessions(self): # Sembra un duplicato di close_connections
        await self.close_connections()
        pass
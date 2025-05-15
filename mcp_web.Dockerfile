# filepath: c:\Users\fran6\Documents\Mauden\MCP_server\stage_mcp\mcp_web.Dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements_mcp_web.txt . 
RUN pip install --no-cache-dir -r requirements_mcp_web.txt
COPY mcp_web.py . 
EXPOSE 8080
# Il DATASET_API_BASE dovrà puntare al container del dataset server
# Lo passeremo come variabile d'ambiente o lo modificheremo per usare il nome del servizio Docker
CMD ["uvicorn", "mcp_web:mcp.sse_app", "--host", "0.0.0.0", "--port", "8080"]
# Claude Code Remote MCP Setup

Use this setup when team members should use the central VM RAG/MCP without cloning `aem-guides-dataset-studio`.

## Architecture

```text
Claude Code on user machine
  -> HTTP MCP JSON-RPC
  -> http://10.42.46.78:4502/mcp
  -> nginx
  -> http://127.0.0.1:8001/mcp
  -> Dataset Studio backend + Chroma/RAG on VM
```

Port `8001` is the backend service port and may not be reachable from user laptops. Port `4502` is already the public VM web port, so nginx should proxy `/mcp` to the backend.

## VM nginx proxy

Add this to the VM nginx server block that listens on `4502`:

```nginx
location = /mcp {
    proxy_pass http://127.0.0.1:8001/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    proxy_buffering off;
}

location /mcp/ {
    proxy_pass http://127.0.0.1:8001/mcp/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    proxy_buffering off;
}
```

Then run:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart aem-backend.service
```

## Smoke tests from VM

```bash
curl -s http://127.0.0.1:8001/mcp/health
curl -s http://127.0.0.1:8001/mcp
```

## Smoke tests from user machine

```powershell
curl http://10.42.46.78:4502/mcp/health
curl http://10.42.46.78:4502/mcp
```

Expected response includes:

```json
{
  "status": "ok",
  "tools": [
    "ask_dita_expert",
    "guides_test_plan_generator",
    "generate_dita_ot_output",
    "upload_mcp_generated_data_to_aem",
    "check_rag_status"
  ]
}
```

## Claude Code MCP config

Use this config on team machines:

```json
{
  "mcpServers": {
    "aem-guides-dataset-studio": {
      "type": "http",
      "url": "http://10.42.46.78:4502/mcp",
      "headers": {
        "Authorization": "Bearer dev-bypass"
      }
    }
  }
}
```

Restart Claude Code after changing MCP config.


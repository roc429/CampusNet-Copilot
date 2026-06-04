"""NetBox MCP Server — 桥接 NetBox REST API 到 MCP 协议。"""
import os, json, httpx
from mcp.server.fastmcp import FastMCP

NETBOX_URL = os.getenv("NETBOX_URL", "http://localhost:8000")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "")
HOST = os.getenv("NETBOX_MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("NETBOX_MCP_PORT", "7001"))

mcp = FastMCP(name="NetBoxMCP", host=HOST, port=PORT)

@mcp.tool(description="查询 NetBox 设备列表")
async def netbox_get_devices(limit: int = 10) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{NETBOX_URL}/api/dcim/devices/?limit={limit}", headers={"Authorization": f"Token {NETBOX_TOKEN}"})
        return {"ok": True, "devices": r.json().get("results", [])} if r.status_code == 200 else {"ok": False, "error": r.text}

@mcp.tool(description="查询 NetBox 站点")
async def netbox_get_sites(limit: int = 10) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{NETBOX_URL}/api/dcim/sites/?limit={limit}", headers={"Authorization": f"Token {NETBOX_TOKEN}"})
        return {"ok": True, "sites": r.json().get("results", [])} if r.status_code == 200 else {"ok": False, "error": r.text}

if __name__ == "__main__":
    mcp.run(transport="sse")

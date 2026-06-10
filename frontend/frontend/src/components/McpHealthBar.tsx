import { useCallback, useEffect, useState } from 'react'
import { fetchMcpHealth, type McpServerHealth } from '../api/agentApi'
import { usePolling } from './monitor-screen/usePolling'
import './McpHealthBar.css'

export default function McpHealthBar() {
  const [servers, setServers] = useState<McpServerHealth[]>([])
  const [ok, setOk] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchMcpHealth()
      setOk(data.ok)
      setServers(data.servers ?? [])
      setError(data.error ?? null)
    } catch (e) {
      setOk(false)
      setError(e instanceof Error ? e.message : 'MCP 健康检查失败')
      setServers([])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  usePolling(load, 15000)

  const connected = servers.filter((s) => s.connected).length
  const total = servers.length

  return (
    <div className="mcp-health">
      <div className="mcp-health__summary">
        <span className="mcp-health__title">MCP 工具总线</span>
        <span className={`mcp-health__badge ${ok ? 'mcp-health__badge--ok' : 'mcp-health__badge--err'}`}>
          {ok === null ? '检测中' : ok ? `${connected}/${total || 5} 在线` : '离线'}
        </span>
        {error ? <span className="mcp-health__err">{error}</span> : null}
      </div>
      <div className="mcp-health__servers">
        {(servers.length > 0
          ? servers
          : (['campus', 'prometheus', 'grafana', 'timesfm', 'netbox'] as const).map(
              (name): McpServerHealth => ({
                server_name: name,
                connected: false,
              }),
            )
        ).map((s) => (
          <div
            key={s.server_name}
            className={`mcp-health__chip ${s.connected ? 'mcp-health__chip--on' : 'mcp-health__chip--off'}`}
            title={s.tools?.join(', ') ?? s.server_name}
          >
            <span className="mcp-health__dot" aria-hidden="true" />
            {s.server_name}
            {typeof s.tool_count === 'number' ? ` (${s.tool_count})` : ''}
          </div>
        ))}
      </div>
    </div>
  )
}

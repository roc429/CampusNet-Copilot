import { useCallback, useEffect, useState } from 'react'
import ItemWrap from '../ItemWrap'
import { fetchPortDetails, type PortDetailItem } from '../monitorScreenApi'

export default function AlarmRanking() {
  const [items, setItems] = useState<PortDetailItem[]>([])

  const load = useCallback(async () => {
    const res = await fetchPortDetails()
    if (res.success) setItems(res.data)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <ItemWrap title="端口实时明细表" className="ms-port-detail-panel">
      <div className="ms-data-table-wrap">
        <table className="ms-data-table">
          <thead>
            <tr>
              <th>端口</th>
              <th>状态</th>
              <th>速率</th>
              <th>负载</th>
              <th>丢包</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.portId}>
                <td>{row.portId}</td>
                <td>
                  <span
                    className={`ms-data-table__status ms-data-table__status--${row.status === 'Up' ? 'up' : 'down'}`}
                  >
                    {row.status}
                  </span>
                </td>
                <td>{row.rateMbps.toFixed(2)} Mbps</td>
                <td>{row.loadPct.toFixed(2)}%</td>
                <td>{row.lossPct.toFixed(4)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ItemWrap>
  )
}

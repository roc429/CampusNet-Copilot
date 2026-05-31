import { useCallback, useEffect, useState } from 'react'
import DigitalFlop from '../DigitalFlop'
import ItemWrap from '../ItemWrap'
import { fetchPartitionLoad, type PartitionLoadItem } from '../monitorScreenApi'

const PARTITION_STYLES = [
  { ringClass: 'ms-ring--lan', color: '#1890FF' },
  { ringClass: 'ms-ring--lv', color: '#26A69A' },
  { ringClass: 'ms-ring--huang', color: '#FFB800' },
] as const

export default function UserOverview() {
  const [items, setItems] = useState<PartitionLoadItem[]>([])

  const load = useCallback(async () => {
    const res = await fetchPartitionLoad()
    if (res.success) setItems(res.data)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <ItemWrap title="分区负载对比" className="ms-partition-panel">
      <ul className="ms-device-overview ms-device-overview--triple">
        {items.map((item, index) => {
          const style = PARTITION_STYLES[index % PARTITION_STYLES.length]
          return (
            <li key={item.name}>
              <DigitalFlop
                value={item.value}
                display={`${item.value}%`}
                color={style.color}
                ringClass={style.ringClass}
              />
              <p>{item.name}</p>
            </li>
          )
        })}
      </ul>
    </ItemWrap>
  )
}

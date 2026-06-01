type Props = {
  value: number
  color: string
  ringClass: string
  display?: string
}

export default function DigitalFlop({ value, color, ringClass, display }: Props) {
  return (
    <div className={`ms-digital-flop ${ringClass}`}>
      <span className="ms-digital-flop__num" style={{ color }}>
        {display ?? value}
      </span>
    </div>
  )
}

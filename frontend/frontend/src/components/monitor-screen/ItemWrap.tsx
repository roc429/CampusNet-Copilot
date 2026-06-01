import type { ReactNode } from 'react'
import titleZuo from '../../assets/monitor-screen/img/titles/zuo.png'
import BorderBox13 from './BorderBox13'

type Props = {
  title: string
  children: ReactNode
  className?: string
  contentClassName?: string
}

export default function ItemWrap({
  title,
  children,
  className = '',
  contentClassName = '',
}: Props) {
  return (
    <div className={`ms-item-wrap lr_titles ${className}`.trim()}>
      <BorderBox13>
        {title ? (
          <div className="item_title">
            <div className="item_title__zuo" style={{ backgroundImage: `url(${titleZuo})` }} />
            <span className="title-inner">&nbsp;&nbsp;{title}&nbsp;&nbsp;</span>
            <div
              className="item_title__you"
              style={{ backgroundImage: `url(${titleZuo})` }}
            />
          </div>
        ) : null}
        <div
          className={
            title
              ? `item_title_content ${contentClassName}`.trim()
              : `item_title_content_def ${contentClassName}`.trim()
          }
        >
          {children}
        </div>
      </BorderBox13>
    </div>
  )
}

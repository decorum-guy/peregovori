import { createContext, useContext } from 'react'
import convergence from './assets/brand/convergence.svg'
import dialogue from './assets/brand/dialogue.svg'
import commonCourse from './assets/brand/common-course.svg'
import nextMove from './assets/brand/next-move.svg'

export const logoConcepts = [
  { id: 'convergence', name: 'Сближение', src: convergence, description: 'Две разные позиции встречаются в одной точке.', recommended: true },
  { id: 'dialogue', name: 'Диалог', src: dialogue, description: 'Две реплики складываются в общий разговор.', recommended: false },
  { id: 'common-course', name: 'Общий курс', src: commonCourse, description: 'Разные линии образуют пространство для решения.', recommended: false },
  { id: 'next-move', name: 'Следующий ход', src: nextMove, description: 'Поворот от противостояния к конкретному действию.', recommended: false },
] as const

export type LogoVariant = typeof logoConcepts[number]['id']
export const BrandVariantContext = createContext<LogoVariant>('convergence')

export function LineMark({ compact = false, variant }: { compact?: boolean; variant?: LogoVariant }) {
  const selected = useContext(BrandVariantContext)
  const concept = logoConcepts.find((item) => item.id === (variant || selected)) || logoConcepts[0]
  return <img className={`line-mark${compact ? ' line-mark--compact' : ''}`} src={concept.src} alt="" aria-hidden="true" />
}

import { createContext, useContext } from 'react'
import convergence from './assets/brand/convergence.svg'
import dialogue from './assets/brand/dialogue.svg'
import nextMove from './assets/brand/next-move.svg'

export const logoConcepts = [
  { id: 'convergence', name: 'Сближение', src: convergence, description: 'Две разные позиции встречаются в одной точке.' },
  { id: 'dialogue', name: 'Диалог', src: dialogue, description: 'Две реплики складываются в общий разговор.' },
  { id: 'next-move', name: 'Следующий ход', src: nextMove, description: 'Поворот от противостояния к конкретному действию.' },
] as const

export type LogoVariant = typeof logoConcepts[number]['id']
export const DEFAULT_LOGO: LogoVariant = 'next-move'
export const BrandVariantContext = createContext<LogoVariant>(DEFAULT_LOGO)

export function LineMark({ compact = false, variant }: { compact?: boolean; variant?: LogoVariant }) {
  const selected = useContext(BrandVariantContext)
  const concept = logoConcepts.find((item) => item.id === (variant || selected)) || logoConcepts.find((item) => item.id === DEFAULT_LOGO)!
  return <img className={`line-mark${compact ? ' line-mark--compact' : ''}`} src={concept.src} alt="" aria-hidden="true" />
}

import { FormEvent, useRef, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { AppConfig, GameScreen, Session, Settings, SetupScreen } from './App'
import { BrandVariantContext, LineMark, LogoVariant, logoConcepts } from './BrandMark'
import './design-preview.css'

type View = 'chat' | 'review' | 'logos' | 'setup'
const views: { id: View; label: string }[] = [
  { id: 'logos', label: 'Логотипы' }, { id: 'setup', label: 'Настройки' },
  { id: 'chat', label: 'Чат' }, { id: 'review', label: 'Разбор' },
]

const exampleSettings: Settings = {
  scenario: 'conflict_then_negotiation', conflict_type: 'personal', difficulty: 'medium',
  student_side: 'protect', sphere: 'work', custom_topic: '', player_name: '', engine_id: 'premium',
}
const config: AppConfig = {
  premium_model_id: 'anthropic/claude-opus-5.5', premium_model_label: 'Claude Opus 5.5',
  provider_mode: 'test_mock', generation_available: true, generation_unavailable_reason: null,
  engines: [
    { id: 'premium', label: 'Claude Opus 5.5', enabled: true },
    { id: 'lora', label: 'Qwen · Дообученная', enabled: false, reason: 'Модель сейчас не подключена.' },
  ], notice: 'Пример интерфейса',
}

const turns = [
  ['opponent', 'Ты опять не готова помочь. Для тебя команда вообще важна?'],
  ['player', 'Команда важна. После 19:00 я недоступна. Давай обсудим варианты без оценок моей лояльности.'],
  ['opponent', 'Подрядчик приедет в 19:30. Кто тогда примет работу?'],
  ['player', 'До 18:30 подготовлю документы и чек-лист. Марина сможет встретить подрядчика?'],
  ['opponent', 'Да, но ей понадобится список того, что нужно проверить.'],
  ['player', 'Хорошо, пришлю его вам обоим до 18:30. Если будут вопросы, обсудим их до моего ухода.'],
  ['opponent', 'Договорились. Я свяжусь с Мариной и подтвержу время.'],
] as const

const exampleSession: Session = {
  id: 'design-example', created_at: '2026-10-14T10:00:00+03:00', status: 'active', debrief_status: 'not_requested',
  settings: exampleSettings,
  case: {
    scenario: 'conflict_then_negotiation', conflict_type: 'personal', title: 'Дополнительная смена',
    context: 'Руководитель просит остаться вечером для приёмки подрядчика. У вас уже есть планы, а разговор перешёл к оценке вашей лояльности команде.',
    student_role: 'Координатор проекта', student_goal: null,
    negotiation_topic: 'Кто примет подрядчика вечером и как подготовить передачу работы.',
    player_conflict_goal: 'Чтобы отказ от дополнительной смены обсуждался без сомнений в моей лояльности команде.',
    known_facts: ['Подрядчик приезжает в 19:30.', 'Вы можете подготовить документы до 18:30.', 'Марина участвует в проекте и знакома с подрядчиком.'],
    participants: [],
  },
  opponent: { name: 'Алексей', role: 'Руководитель проекта' },
  engine: { id: 'premium', model_id: 'anthropic/claude-opus-5.5', label: 'Claude Opus 5.5' },
  provider_mode: 'test_mock', source: 'test_mock',
  messages: turns.map(([speaker, text], index) => ({
    id: `example-${index}`, speaker, text, created_at: '2026-10-14T10:00:00+03:00', delivery_status: 'sent',
  })),
  debrief: null,
}

const exampleReport = {
  summary: 'Разговор начался с упрёка в нелояльности. Вы обозначили границу по времени и вернули обсуждение к задаче: кто встретит подрядчика. В конце появился конкретный план передачи работы.',
  strengths: [
    { quote: 'Давай обсудим варианты без оценок моей лояльности.', explanation: 'Вы назвали нежелательный способ разговора и предложили продолжить обсуждение задачи, сохранив возможность договориться.' },
    { quote: 'До 18:30 подготовлю документы и чек-лист.', explanation: 'Вы предложили посильный вклад с понятным сроком. Это помогло перейти от оценки отношений к организации работы.' },
  ],
  risks: [
    { quote: 'Марина сможет встретить подрядчика?', explanation: 'Вариант предложен как вопрос, а не как обещание от имени Марины. Для завершения договорённости ещё нужно получить её подтверждение.' },
  ],
  next_step: 'Уточните, кто подтвердит участие Марины и кому подрядчик сообщит о задержке. Затем коротко зафиксируйте ответственных и сроки.',
  example_phrase: 'Я пришлю чек-лист до 18:30. Сможешь подтвердить с Мариной время встречи? Если подрядчик задержится, кому он позвонит?',
}

export default function DesignPreview() {
  const params = new URLSearchParams(window.location.search)
  const [view, setView] = useState<View>(() => views.find((item) => item.id === params.get('view'))?.id || 'chat')
  const [logo, setLogo] = useState<LogoVariant>(() => logoConcepts.find((item) => item.id === params.get('logo'))?.id || 'convergence')
  const [settings, setSettings] = useState(exampleSettings)
  const [session, setSession] = useState(exampleSession)
  const [draft, setDraft] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(true)
  const conversationRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  function updateLocation(nextView: View, nextLogo = logo) {
    setView(nextView)
    setLogo(nextLogo)
    const query = new URLSearchParams({ view: nextView, logo: nextLogo })
    window.history.replaceState(null, '', `/design-preview?${query}`)
  }

  function send(event: FormEvent) {
    event.preventDefault()
    if (!draft.trim()) return
    setSession((current) => ({ ...current, messages: [...current.messages,
      { id: crypto.randomUUID(), speaker: 'player', text: draft.trim(), created_at: '', delivery_status: 'sent' },
      { id: crypto.randomUUID(), speaker: 'opponent', text: 'Давайте уточним этот пункт и зафиксируем, кто отвечает за следующий шаг.', created_at: '', delivery_status: 'sent' },
    ] }))
    setDraft('')
    window.requestAnimationFrame(() => endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }))
  }

  const displayedSession = view === 'review' ? { ...session, status: 'reviewed' as const, debrief_status: 'complete' as const, debrief: exampleReport } : session

  return (
    <BrandVariantContext.Provider value={logo}>
      <main className="design-preview">
        <nav className="preview-toolbar" aria-label="Примеры дизайна">
          <span>Пример дизайна <span className="preview-synthetic">· синтетические данные</span></span>
          <div>{views.map((item) => <button key={item.id} type="button" aria-pressed={view === item.id} onClick={() => {
            if (item.id === 'chat') setSession((current) => ({ ...current, status: 'active', debrief: null, debrief_status: 'not_requested' }))
            updateLocation(item.id)
          }}>{item.label}</button>)}</div>
        </nav>
        <div className="app-shell app-shell--preview">
          {view === 'logos' ? (
            <section className="logo-gallery">
              <header><p className="eyebrow">ЛИНИЯ РЕШЕНИЯ</p><h1>Четыре направления для знака</h1><p>Выберите вариант, затем посмотрите его в настройках, чате и разборе.</p></header>
              <div className="logo-concepts" role="group" aria-label="Варианты логотипа">
                {logoConcepts.map((concept) => <button className={`logo-concept${logo === concept.id ? ' selected' : ''}`} key={concept.id} type="button" aria-pressed={logo === concept.id} onClick={() => updateLocation('logos', concept.id)}>
                  <span className="logo-concept-top"><strong>{concept.name}</strong>{concept.recommended && <span className="logo-recommendation">Предлагаю этот</span>}</span>
                  <span className="logo-wordmark"><LineMark variant={concept.id} /><span>Линия решения</span></span>
                  <span className="logo-concept-description">{concept.description}</span>
                  <span className="logo-small-example"><LineMark variant={concept.id} compact /><span>В небольшом размере</span></span>
                </button>)}
              </div>
              <button className="button button-primary" onClick={() => updateLocation('setup')}>Посмотреть в интерфейсе <ArrowRight size={17} /></button>
            </section>
          ) : view === 'setup' ? (
            <SetupScreen settings={settings} config={config} action={null} error="" notice="" currentEngine={config.engines[0]} checkingModels={false}
              onRefreshModels={() => {}} onUpdate={(key, value) => setSettings((current) => ({ ...current, [key]: value }))}
              onRandomize={() => setSettings(exampleSettings)} onClearError={() => {}}
              onStart={(event) => { event?.preventDefault(); setSession({ ...exampleSession, settings: { ...exampleSettings, player_name: settings.player_name } }); updateLocation('chat') }} />
          ) : (
            <GameScreen key={view} config={config} session={displayedSession} preview action={null} error="" draft={draft} setDraft={setDraft}
              onDraftEdited={() => {}} detailsOpen={detailsOpen} setDetailsOpen={setDetailsOpen} hasNewMessage={false}
              conversationRef={conversationRef} endRef={endRef} onConversationScroll={() => {}} onSend={send}
              onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !window.matchMedia('(max-width: 767px)').matches) { event.preventDefault(); send(event) } }}
              onRetry={() => {}} onFinish={() => setSession((current) => ({ ...current, status: 'finished' }))}
              onSkip={() => setSession((current) => ({ ...current, status: 'finished_without_review' }))}
              onDebrief={() => updateLocation('review')}
              onPlayAgain={() => { setSession(exampleSession); updateLocation('setup') }} onClearError={() => {}} />
          )}
        </div>
      </main>
    </BrandVariantContext.Provider>
  )
}

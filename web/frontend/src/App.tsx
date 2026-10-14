import { FormEvent, KeyboardEvent, SelectHTMLAttributes, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowRight, Check, ChevronDown, CircleAlert, MessageCircle, RotateCcw, Send, Sparkles, X } from 'lucide-react'
import { LineMark } from './BrandMark'
import { Language, LanguageContext, LanguageSwitch, catalogUrl, errorText, preferredLanguage, rememberLanguage, sessionKey, settingsKey, useI18n } from './i18n'

type Scenario = 'conflict_only' | 'negotiation_only' | 'conflict_then_negotiation'
type ConflictType = 'personal' | 'public' | 'mixed'
type Difficulty = 'easy' | 'medium' | 'hard' | 'extra_hard' | 'impossible'
type StudentSide = 'protect' | 'pressure'
type EngineId = 'premium' | 'lora'
type SessionStatus = 'active' | 'finished' | 'reviewed' | 'finished_without_review'

type Engine = { id: EngineId; label: string; enabled: boolean; reason?: string }
export type AppConfig = {
  language: Language
  premium_model_id: string
  premium_model_label: string
  provider_mode: 'openrouter' | 'test_mock' | 'unconfigured'
  generation_available: boolean
  generation_unavailable_reason: string | null
  engines: Engine[]
  notice: string
}
export type Settings = {
  language: Language
  scenario: Scenario
  conflict_type: ConflictType
  difficulty: Difficulty
  student_side: StudentSide
  sphere: 'work' | 'family' | 'study' | 'friends' | 'custom'
  custom_topic: string
  player_name: string
  engine_id: EngineId
}
type PublicParticipant = { name: string; role: string }
type PublicCase = {
  scenario: Scenario
  conflict_type: ConflictType | 'none'
  title: string
  context: string
  student_role: string
  student_goal: string | null
  negotiation_topic: string | null
  player_conflict_goal: string | null
  known_facts: string[]
  participants: PublicParticipant[]
}
type ChatMessage = {
  id: string
  request_id?: string
  speaker: 'player' | 'opponent'
  text: string
  created_at: string
  delivery_status: 'sent' | 'pending' | 'failed' | 'cancelled'
}
type Point = { quote: string; explanation: string }
type Debrief = {
  summary: string
  strengths: Point[]
  risks: Point[]
  next_step: string
  example_phrase: string | null
}
export type Session = {
  id: string
  created_at: string
  status: SessionStatus
  debrief_status: 'not_requested' | 'pending' | 'failed' | 'complete'
  settings: Partial<Settings>
  case: PublicCase
  opponent: { name: string; role: string }
  engine: { id: EngineId; model_id: string; label?: string }
  provider_mode: 'openrouter' | 'test_mock' | 'unconfigured'
  source: 'openrouter' | 'accepted_train_fallback' | 'test_mock'
  messages: ChatMessage[]
  debrief: Debrief | null
}

const defaultSettings: Settings = {
  language: 'ru',
  scenario: 'conflict_then_negotiation',
  conflict_type: 'personal',
  difficulty: 'medium',
  student_side: 'protect',
  sphere: 'work',
  custom_topic: '',
  player_name: '',
  engine_id: 'premium',
}

const scenarioChoices: { value: Scenario; label: string; short: string }[] = [
  { value: 'conflict_only', label: 'Конфликт', short: 'Разговор о границах и отношениях' },
  { value: 'negotiation_only', label: 'Переговоры', short: 'Поиск рационального решения' },
  { value: 'conflict_then_negotiation', label: 'Конфликт + переговоры', short: 'Конфликт может вернуться к теме' },
]
const difficultyChoices: { value: Difficulty; label: string }[] = [
  { value: 'easy', label: 'Лёгкая' },
  { value: 'medium', label: 'Средняя' },
  { value: 'hard', label: 'Сложная' },
  { value: 'extra_hard', label: 'Очень сложная' },
  { value: 'impossible', label: 'Желаемый исход закрыт' },
]
const conflictChoices: { value: ConflictType; label: string }[] = [
  { value: 'personal', label: 'Личный' },
  { value: 'public', label: 'Публичный' },
  { value: 'mixed', label: 'Смешанный' },
]

class ApiError extends Error {
  code?: string
  constructor(message: string, code?: string) {
    super(message)
    this.code = code
  }
}

async function api<T>(url: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Не удалось подключиться к приложению. Проверьте соединение и попробуйте ещё раз.', 'network_error')
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(typeof payload.detail === 'string' ? payload.detail : 'Запрос не выполнен. Попробуйте ещё раз.', payload.code)
  }
  return payload as T
}

function readSavedSettings(language: Language): Settings {
  try {
    const value = localStorage.getItem(settingsKey(language))
    const saved = value ? JSON.parse(value) : {}
    // Migrate the old chat fallback that accidentally became a form value.
    return { ...defaultSettings, ...saved, language, engine_id: language === 'en' ? 'premium' : saved.engine_id || 'premium', player_name: saved.player_name === 'Вы' ? '' : saved.player_name || '' }
  } catch {
    return { ...defaultSettings, language }
  }
}

function describeError(error: unknown, language: Language): string {
  return errorText(error instanceof Error ? error.message : 'Что-то пошло не так. Попробуйте ещё раз.', error instanceof ApiError ? error.code : undefined, language)
}

function normalized(value: string | null | undefined): string {
  return (value || '').replace(/[\s.,;:!?«»"'()—–-]+/g, ' ').trim().toLocaleLowerCase('ru')
}

function meaningfullyDistinct(value: string | null, comparisons: Array<string | null>): boolean {
  const candidate = normalized(value)
  if (!candidate) return false
  const tokens = (text: string) => new Set(text.match(/[a-zа-яё0-9]{4,}/giu) || [])
  const candidateTokens = tokens(candidate)
  return comparisons.every((comparison) => {
    const other = normalized(comparison)
    if (!other) return true
    if (candidate === other || candidate.includes(other) || other.includes(candidate)) return false
    const otherTokens = tokens(other)
    const overlap = [...candidateTokens].filter((token) => otherTokens.has(token)).length
    const union = new Set([...candidateTokens, ...otherTokens]).size
    return overlap < 4 || overlap / Math.max(1, union) <= 0.68
  })
}

function SelectControl(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <span className="select-control"><select {...props} /><ChevronDown size={16} aria-hidden="true" /></span>
}

function ErrorNotice({ message, onClose, onRetry }: { message: string; onClose?: () => void; onRetry?: () => void }) {
  const { t } = useI18n()
  return (
    <div className="notice notice--error" role="alert">
      <CircleAlert size={18} aria-hidden="true" />
      <p>{message}</p>
      {onRetry && <button className="text-button" onClick={onRetry}>{t("Повторить")}</button>}
      {onClose && <button className="icon-button notice-close" aria-label={t("Закрыть сообщение")} onClick={onClose}><X size={16} /></button>}
    </div>
  )
}

export default function App() {
  const [language, setLanguage] = useState<Language>(preferredLanguage)
  useEffect(() => rememberLanguage(language), [language])
  return <LanguageContext.Provider value={language}><Application key={language} language={language} onLanguageChange={setLanguage} /></LanguageContext.Provider>
}

function Application({ language, onLanguageChange }: { language: Language; onLanguageChange: (language: Language) => void }) {
  const { t } = useI18n()
  const SESSION_KEY = sessionKey(language)
  const SETTINGS_KEY = settingsKey(language)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [configError, setConfigError] = useState('')
  const [checkingModels, setCheckingModels] = useState(false)
  const [settings, setSettings] = useState<Settings>(() => readSavedSettings(language))
  const [session, setSession] = useState<Session | null>(null)
  const [draft, setDraft] = useState('')
  const [draftRequestId, setDraftRequestId] = useState('')
  const [error, setError] = useState('')
  const [action, setAction] = useState<'starting' | 'sending' | 'finishing' | 'judging' | 'skipping' | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [notice, setNotice] = useState('')
  const conversationRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const pinnedToBottom = useRef(true)
  const [hasNewMessage, setHasNewMessage] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)

  const saveSession = useCallback((next: Session) => {
    setSession(next)
    localStorage.setItem(SESSION_KEY, next.id)
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...settings, ...next.settings, player_name: next.settings.player_name || '' }))
  }, [settings])

  useEffect(() => {
    let alive = true
    async function restore() {
      try {
        const loaded = await api<AppConfig>(`/api/config?language=${language}`)
        if (alive) {
          setConfig(loaded)
          setConfigError('')
        }
      } catch (err) {
        if (alive) setConfigError(describeError(err, language))
      }
      const sessionId = localStorage.getItem(SESSION_KEY)
      if (sessionId) {
        try {
          const saved = await api<Session>(`/api/sessions/${sessionId}`)
          if ((saved.settings.language || 'ru') !== language) throw new Error('Saved game language mismatch')
          if (alive) {
            setSession(saved)
            setSettings((current) => ({ ...current, ...saved.settings, engine_id: saved.engine.id }))
          }
        } catch {
          localStorage.removeItem(SESSION_KEY)
        }
      }
      if (alive) setRestoring(false)
    }
    void restore()
    return () => { alive = false }
  }, [])

  const refreshModels = useCallback(async (manual = false) => {
    if (manual) setCheckingModels(true)
    try {
      setConfig(await api<AppConfig>(`/api/config?language=${language}${manual ? '&refresh=true' : ''}`))
      setConfigError('')
    } catch (err) {
      setConfigError(describeError(err, language))
      setConfig((current) => current && ({ ...current, engines: current.engines.map((engine) => engine.id === 'lora' ? { ...engine, enabled: false, reason: t("Не удалось проверить доступность модели.") } : engine) }))
    } finally {
      if (manual) setCheckingModels(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => void refreshModels(), 10000)
    return () => window.clearInterval(timer)
  }, [refreshModels])

  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  }, [settings])

  useEffect(() => {
    if (!session) return
    const player = session.messages.filter((message) => message.speaker === 'player')
    const last = player[player.length - 1]
    if (last?.delivery_status === 'failed') setDraftRequestId(last.request_id || '')
    if (last?.delivery_status === 'sent' && last.request_id === draftRequestId) setDraftRequestId('')
  }, [session, draftRequestId])

  useEffect(() => {
    if (!session || !conversationRef.current) return
    if (pinnedToBottom.current) {
      endRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'end' })
      setHasNewMessage(false)
    } else {
      setHasNewMessage(true)
    }
  }, [session?.messages.length, session?.status])

  const currentEngine = useMemo(() => config?.engines.find((engine) => engine.id === settings.engine_id), [config, settings.engine_id])

  function updateSetting<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  function randomize() {
    const scenario = scenarioChoices[Math.floor(Math.random() * scenarioChoices.length)].value
    const next: Settings = {
      ...settings,
      scenario,
      difficulty: difficultyChoices[Math.floor(Math.random() * difficultyChoices.length)].value,
      sphere: (['work', 'family', 'study', 'friends', 'custom'] as Settings['sphere'][])[Math.floor(Math.random() * 5)],
      custom_topic: '',
    }
    if (scenario === 'negotiation_only') {
      next.conflict_type = 'personal'
      next.student_side = 'protect'
    } else {
      next.conflict_type = conflictChoices[Math.floor(Math.random() * conflictChoices.length)].value
      next.student_side = Math.random() < 0.5 ? 'protect' : 'pressure'
    }
    setSettings(next)
    setNotice(t("Настройки обновлены"))
    window.setTimeout(() => setNotice(''), 2200)
  }

  async function startGame(event?: FormEvent) {
    event?.preventDefault()
    if (action) return
    setError('')
    if (settings.sphere === 'custom' && !settings.custom_topic.trim()) {
      setError(t("Укажите вашу тему для сферы «Другое»."))
      return
    }
    setAction('starting')
    try {
      const payload: Record<string, unknown> = {
        language,
        scenario: settings.scenario,
        difficulty: settings.difficulty,
        sphere: settings.sphere,
        player_name: settings.player_name.trim() || null,
        engine_id: settings.engine_id,
      }
      if (settings.scenario !== 'negotiation_only') {
        payload.conflict_type = settings.conflict_type
        payload.student_side = settings.student_side
      }
      if (settings.sphere === 'custom') payload.custom_topic = settings.custom_topic.trim()
      const created = await api<Session>('/api/sessions', payload)
      saveSession(created)
      setError('')
      setDraft('')
      setDraftRequestId('')
      setDetailsOpen(true)
    } catch (err) {
      setError(describeError(err, language))
    } finally {
      setAction(null)
    }
  }

  async function refreshSession(sessionId: string) {
    try {
      const updated = await api<Session>(`/api/sessions/${sessionId}`)
      saveSession(updated)
      return updated
    } catch {
      return null
    }
  }

  async function sendMessage(text: string, requestId?: string) {
    if (!session || action || session.status !== 'active' || !text.trim()) return
    const stableId = requestId || draftRequestId || crypto.randomUUID()
    setAction('sending')
    setError('')
    setDraftRequestId(stableId)
    try {
      const updated = await api<Session>(`/api/sessions/${session.id}/message`, { text, request_id: stableId })
      saveSession(updated)
      setDraft('')
      setDraftRequestId('')
    } catch (err) {
      const updated = await refreshSession(session.id)
      if (updated?.messages.some((message) => message.request_id === stableId)) setDraft('')
      setError(describeError(err, language))
    } finally {
      setAction(null)
    }
  }

  async function handleComposerSubmit(event: FormEvent) {
    event.preventDefault()
    await sendMessage(draft)
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    const composing = (event.nativeEvent as globalThis.KeyboardEvent).isComposing
    if (event.key === 'Enter' && !event.shiftKey && !composing && !window.matchMedia('(max-width: 767px)').matches) {
      event.preventDefault()
      void sendMessage(draft)
    }
  }

  async function finishGame() {
    if (!session || (action && action !== 'sending') || session.status !== 'active') return
    setAction('finishing')
    setError('')
    try {
      const updated = await api<Session>(`/api/sessions/${session.id}/finish`, {})
      saveSession(updated)
    } catch (err) {
      setError(describeError(err, language))
    } finally {
      setAction(null)
    }
  }

  async function skipDebrief() {
    if (!session || action) return
    setAction('skipping')
    setError('')
    try {
      const updated = await api<Session>(`/api/sessions/${session.id}/skip-debrief`, {})
      saveSession(updated)
    } catch (err) {
      setError(describeError(err, language))
    } finally {
      setAction(null)
    }
  }

  async function requestDebrief() {
    if (!session || action || session.status === 'active') return
    setAction('judging')
    setError('')
    try {
      const updated = await api<Session>(`/api/sessions/${session.id}/debrief`, {})
      saveSession(updated)
    } catch (err) {
      await refreshSession(session.id)
      setError(describeError(err, language))
    } finally {
      setAction(null)
    }
  }

  function playAgain() {
    localStorage.removeItem(SESSION_KEY)
    setSession(null)
    setError('')
    setDraft('')
    setDraftRequestId('')
    setAction(null)
  }

  function onConversationScroll() {
    const element = conversationRef.current
    if (!element) return
    const atEnd = element.scrollHeight - element.scrollTop - element.clientHeight < 120
    pinnedToBottom.current = atEnd
    if (atEnd) setHasNewMessage(false)
  }

  if (restoring) return <div className="loading-screen"><LineMark /><span>{t("Открываем сессию…")}</span></div>

  return (
    <main className={`app-shell${config ? ` app-shell--${config.provider_mode}` : ''}`}>
      {config?.provider_mode === 'test_mock' && (
        <div className="mode-banner mode-banner--mock"><Sparkles size={16} />{" "}{t("Тестовый режим: ответы и кейсы смоделированы локально, Claude/GPT API не вызывается.")}</div>
      )}
      {config?.provider_mode === 'unconfigured' && (
        <div className="mode-banner mode-banner--setup"><CircleAlert size={16} />{" "}{t("API не подключён. Для настоящей генерации добавьте OPENROUTER_API_KEY на сервере; для локального теста задайте LLM_MODE=mock.")}</div>
      )}
      {configError && !config && <div className="mode-banner mode-banner--setup"><CircleAlert size={16} />{" "}{t("Не удалось загрузить конфигурацию приложения:")}{" "}{configError}</div>}

      {session ? (
        <GameScreen
          config={config}
          session={session}
          action={action}
          error={error}
          draft={draft}
          setDraft={setDraft}
          onDraftEdited={() => setDraftRequestId('')}
          detailsOpen={detailsOpen}
          setDetailsOpen={setDetailsOpen}
          hasNewMessage={hasNewMessage}
          conversationRef={conversationRef}
          endRef={endRef}
          onConversationScroll={onConversationScroll}
          onSend={handleComposerSubmit}
          onKeyDown={handleComposerKey}
          onRetry={(message) => void sendMessage(message.text, message.request_id)}
          onFinish={() => void finishGame()}
          onSkip={() => void skipDebrief()}
          onDebrief={() => void requestDebrief()}
          onPlayAgain={playAgain}
          onClearError={() => setError('')}
        />
      ) : (
        <SetupScreen
          settings={settings}
          config={config}
          action={action}
          error={error}
          notice={notice}
          currentEngine={currentEngine}
          checkingModels={checkingModels}
          onRefreshModels={() => void refreshModels(true)}
          onLanguageChange={onLanguageChange}
          onUpdate={updateSetting}
          onRandomize={randomize}
          onStart={startGame}
          onClearError={() => setError('')}
        />
      )}
    </main>
  )
}

export function SetupScreen({
  settings, config, action, error, notice, currentEngine, checkingModels, onRefreshModels, onLanguageChange, onUpdate, onRandomize, onStart, onClearError,
}: {
  settings: Settings
  config: AppConfig | null
  action: string | null
  error: string
  notice: string
  currentEngine?: Engine
  checkingModels: boolean
  onRefreshModels: () => void
  onLanguageChange?: (language: Language) => void
  onUpdate: <K extends keyof Settings>(key: K, value: Settings[K]) => void
  onRandomize: () => void
  onStart: (event?: FormEvent) => void
  onClearError: () => void
}) {
  const { language, t } = useI18n()
  const hasConflict = settings.scenario !== 'negotiation_only'
  const engineList = (config?.engines || [
    { id: 'premium' as const, label: 'Claude Opus 5.5', enabled: true },
    { id: 'lora' as const, label: t("Qwen · Дообученная"), enabled: false, reason: t("Модель сейчас не подключена.") },
  ]).map((engine) => language === 'en' && engine.id === 'lora' ? { ...engine, label: engine.label.replace(' · Дообученная', ' · Fine-tuned'), enabled: false, reason: t('Qwen доступна только для игры на русском.') } : engine)

  return (
    <div className="setup-page">
      <header className="setup-header">
        <a className="brand-lockup" href={catalogUrl(language)} aria-label={t("Линия решения — к каталогу игр")}>
          <LineMark />
          <p>{t("Линия решения")}</p>
        </a>
        <div className="setup-header-tools"><span className="independent-label">{t("Независимый концепт")}</span>{onLanguageChange && <LanguageSwitch onChange={onLanguageChange} />}</div>
      </header>

      <section className="setup-intro">
        <div>
          <p className="eyebrow intro-kicker">{t("КОНФЛИКТЫ И ПЕРЕГОВОРЫ")}</p>
          <h1>{t("Найдите следующий ход")}</h1>
          <p className="intro-copy">{t("Выберите ситуацию и попробуйте следующий ход в живом диалоге.")}</p>
        </div>
      </section>

      <form className="setup-card" onSubmit={(event) => void onStart(event)}>
        <div className="form-heading"><div><span className="step-kicker">{t("01 / НАСТРОЙКА")}</span><h2>{t("Настройка игры")}</h2></div><MessageCircle size={20} aria-hidden="true" /></div>

        <fieldset className="field-group scenario-fieldset">
          <legend>{t("Режим")}</legend>
          <div className="scenario-grid" role="radiogroup" aria-label={t("Режим игры")}>
            {scenarioChoices.map((choice) => (
              <label key={choice.value} className={`scenario-choice scenario-choice--${choice.value}${settings.scenario === choice.value ? ' selected' : ''}`}>
                <input type="radio" name="scenario" value={choice.value} checked={settings.scenario === choice.value} onChange={() => onUpdate('scenario', choice.value)} />
                <span className="choice-check"><Check size={13} /></span>
                <span className="scenario-label">{t(choice.label)}</span>
                <span className="scenario-short">{t(choice.short)}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="settings-grid">
          {hasConflict && <label className="field-group"><span>{t("Тип конфликта")}</span><SelectControl value={settings.conflict_type} onChange={(event) => onUpdate('conflict_type', event.target.value as ConflictType)}>{conflictChoices.map((choice) => <option value={choice.value} key={choice.value}>{t(choice.label)}</option>)}</SelectControl></label>}
          <label className="field-group"><span>{t("Сложность")}</span><SelectControl value={settings.difficulty} onChange={(event) => onUpdate('difficulty', event.target.value as Difficulty)}>{difficultyChoices.map((choice) => <option value={choice.value} key={choice.value}>{t(choice.label)}</option>)}</SelectControl>{settings.difficulty === 'impossible' && <small>{t("Одно желаемое условие объективно недостижимо; осмысленный разговор всё ещё возможен.")}</small>}</label>
          <label className="field-group"><span>{t("Сфера")}</span><SelectControl value={settings.sphere} onChange={(event) => onUpdate('sphere', event.target.value as Settings['sphere'])}><option value="work">{t("Работа")}</option><option value="family">{t("Семья")}</option><option value="study">{t("Учёба")}</option><option value="friends">{t("Друзья")}</option><option value="custom">{t("Другое")}</option></SelectControl></label>
          {hasConflict && <label className="field-group"><span>{t("Ваша сторона")}</span><SelectControl value={settings.student_side} onChange={(event) => onUpdate('student_side', event.target.value as StudentSide)}><option value="protect">{t("Защищаю границы")}</option><option value="pressure">{t("Оказываю давление")}</option></SelectControl></label>}
          {settings.sphere === 'custom' && <label className="field-group field-span"><span>{t("Ваша тема")}</span><textarea rows={2} required value={settings.custom_topic} maxLength={240} placeholder={t("Например, совместный проект или бытовая договорённость")} onChange={(event) => onUpdate('custom_topic', event.target.value)} /></label>}
          <label className="field-group field-span field-name"><span>{t("Ваше имя, необязательно")}</span><input type="text" maxLength={60} value={settings.player_name} placeholder={t("Как к вам обращаться?")} onChange={(event) => onUpdate('player_name', event.target.value)} /></label>
        </div>

        <fieldset className="field-group engine-fieldset">
          <legend>{t("Модель собеседника")}</legend>
          <div className="engine-grid" role="radiogroup" aria-label={t("Модель собеседника")}>
            {engineList.map((engine) => (
              <label key={engine.id} className={`engine-choice${settings.engine_id === engine.id ? ' selected' : ''}${!engine.enabled ? ' disabled' : ''}`} title={!engine.enabled ? engine.reason : undefined}>
                <input type="radio" name="engine" value={engine.id} checked={settings.engine_id === engine.id} disabled={!engine.enabled || (engine.id === 'lora' && checkingModels)} onChange={() => onUpdate('engine_id', engine.id)} />
                <span className="radio-dot" />
                <span className="engine-copy"><strong>{engine.label}</strong><small>{engine.id === 'premium' ? t("Серверная модель") : t("Локальная модель")}</small></span>
                {engine.id === 'lora' && <span className="soon-tag" role="status">{checkingModels ? t("Проверяем") : engine.enabled ? t("Доступна") : t("Недоступна")}</span>}
              </label>
            ))}
          </div>
          <button className="text-button" type="button" onClick={onRefreshModels} disabled={checkingModels}>{checkingModels ? t("Проверяем доступность…") : t("Обновить доступность")}</button>
          {language === 'en' && <p className="language-note">{t('Qwen доступна только для игры на русском.')}</p>}
        </fieldset>

        {error && <ErrorNotice message={error} onClose={onClearError} />}
        {notice && <p className="live-notice" role="status">{notice}</p>}
        {!config?.generation_available && config?.generation_unavailable_reason && <p className="setup-help"><CircleAlert size={16} /> {config.generation_unavailable_reason}</p>}

        <div className="setup-actions">
          <button className="button button-secondary random-button" type="button" onClick={onRandomize} disabled={!!action}><RotateCcw size={16} />{" "}{t("Случайно")}</button>
          <button className="button button-primary start-button" type="submit" disabled={!!action || !config?.generation_available || (settings.sphere === 'custom' && !settings.custom_topic.trim()) || (settings.engine_id === 'lora' && (!currentEngine?.enabled || checkingModels))}>
            {action === 'starting' ? <><span className="spinner" />{" "}{t("Готовим ситуацию…")}</> : <>{t("Начать игру")}{" "}<ArrowRight size={17} /></>}
          </button>
        </div>
      </form>
      <footer className="concept-footer">{t("Линия решения")}{" "}<span />{" "}{t("Независимый концепт для демонстрации")}</footer>
    </div>
  )
}

export function GameScreen({
  config, session, action, error, draft, setDraft, detailsOpen, setDetailsOpen, hasNewMessage, preview = false,
  onDraftEdited,
  conversationRef, endRef, onConversationScroll, onSend, onKeyDown, onRetry, onFinish, onSkip, onDebrief, onPlayAgain, onClearError,
}: {
  config: AppConfig | null
  session: Session
  action: string | null
  error: string
  draft: string
  setDraft: (value: string) => void
  onDraftEdited: () => void
  detailsOpen: boolean
  setDetailsOpen: (value: boolean) => void
  hasNewMessage: boolean
  preview?: boolean
  conversationRef: React.RefObject<HTMLDivElement>
  endRef: React.RefObject<HTMLDivElement>
  onConversationScroll: () => void
  onSend: (event: FormEvent) => void
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  onRetry: (message: ChatMessage) => void
  onFinish: () => void
  onSkip: () => void
  onDebrief: () => void
  onPlayAgain: () => void
  onClearError: () => void
}) {
  const { language, t } = useI18n()
  const playerName = session.settings.player_name?.trim() || t("Вы")
  const latestFailed = [...session.messages].reverse().find((message) => message.speaker === 'player' && message.delivery_status === 'failed')
  const loraEnabled = config?.engines.find((engine) => engine.id === 'lora')?.enabled
  const showOffer = session.status === 'finished' && !session.debrief
  const showDone = session.status === 'finished_without_review'
  const summary = session.case

  return (
    <div className="game-shell">
      <header className="game-header">
        <a className="back-link" href={catalogUrl(language)}><ArrowLeft size={16} />{" "}{t("К играм")}</a>
        <div className="game-title"><LineMark compact /><div><span className="eyebrow">{t("ЛИНИЯ РЕШЕНИЯ")}</span><h1>{summary.title}</h1></div></div>
        {session.status === 'active' ? <button className="finish-button" onClick={onFinish} disabled={action === 'finishing'}>{action === 'finishing' ? <><span className="spinner spinner--small" />{" "}{t("Завершаем…")}</> : <>{t("Завершить")}{" "}<X size={16} /></>}</button> : <span className="finished-pill">{t("Диалог завершён")}</span>}
      </header>

      {!preview && session.provider_mode === 'test_mock' && <div className="game-test-note"><Sparkles size={15} />{" "}{t("Тестовая симуляция: ответы не получены от")}{" "}{config?.premium_model_label || 'Claude/GPT'} API.</div>}
      {session.source === 'accepted_train_fallback' && <div className="fallback-note"><CircleAlert size={15} />{" "}{t("Резервный принятый TRAIN-кейс. Параметры выбранной сферы могли не примениться.")}</div>}
      {session.engine.id === 'lora' && !loraEnabled && <div className="fallback-note"><CircleAlert size={15} />{" "}{t("Подключённая модель недоступна; ответы не переключаются на другую модель.")}</div>}

      <div className={`game-layout${showOffer || showDone || session.debrief ? ' game-layout--final' : ''}`}>
        <CasePanel session={session} detailsOpen={detailsOpen} setDetailsOpen={setDetailsOpen} />

        <section className="chat-panel" aria-label={t("Игровой чат")}>
          {session.status === 'active' ? (
            <>
              <div className="chat-subheader"><div className="opponent-avatar" aria-hidden="true">{session.opponent.name.slice(0, 1)}</div><div><strong>{session.opponent.name}</strong><span>{session.opponent.role}</span></div><span className="chat-live"><i />{" "}{t("Диалог")}</span></div>
              <div className="conversation" ref={conversationRef} onScroll={onConversationScroll} aria-live="polite">
                {session.messages.map((message) => (
                  <article key={message.id} className={`message-row${message.speaker === 'player' ? ' message-row--player' : ''}`}>
                    <div className="message-inner">
                      <span className="message-speaker">{message.speaker === 'player' ? playerName : session.opponent.name}</span>
                      <div className={`message-bubble${message.speaker === 'player' ? ' message-bubble--player' : ''}${message.delivery_status === 'failed' ? ' message-bubble--failed' : ''}`}>{message.text}</div>
                      {message.speaker === 'player' && message.delivery_status === 'pending' && <span className="delivery-caption">{t("Собеседник отвечает…")}</span>}
                      {message.speaker === 'player' && message.delivery_status === 'failed' && <div className="retry-inline"><span>{t("Реплика сохранена")}</span><button className="text-button" onClick={() => onRetry(message)} disabled={!!action}><RotateCcw size={14} />{" "}{t("Повторить ответ")}</button></div>}
                      {message.speaker === 'player' && message.delivery_status === 'cancelled' && <span className="delivery-caption">{t("Сессия завершена до ответа")}</span>}
                    </div>
                  </article>
                ))}
                {action === 'sending' && !session.messages.some((message) => message.delivery_status === 'pending') && <div className="typing-note"><span className="spinner spinner--small" />{" "}{t("Собеседник отвечает…")}</div>}
                <div ref={endRef} />
              </div>
              {hasNewMessage && <button className="new-message-button" onClick={() => endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })}><ArrowDown size={15} />{" "}{t("Новое сообщение")}</button>}
              {error && <div className="chat-error"><ErrorNotice message={error} onClose={onClearError} onRetry={latestFailed ? () => onRetry(latestFailed) : undefined} /></div>}
              <form className="composer" onSubmit={(event) => void onSend(event)}>
                <textarea value={draft} onChange={(event) => { setDraft(event.target.value); if (!latestFailed) onDraftEdited() }} onKeyDown={onKeyDown} maxLength={4000} rows={2} placeholder={t("Напишите ответ…")} aria-label={t("Ваша реплика")} disabled={!!action || !!latestFailed} />
                <button className="send-button" type="submit" aria-label={t("Отправить реплику")} disabled={!!action || !!latestFailed || !draft.trim()}>{action === 'sending' ? <span className="spinner spinner--light" /> : <Send size={19} />}</button>
                <span className="composer-hint">{t("Enter — отправить · Shift + Enter — новая строка")}</span>
              </form>
            </>
          ) : showOffer ? (
            <div className="final-card offer-card">
              <div className="final-mark"><MessageCircle size={32} aria-hidden="true" /></div>
              <p className="eyebrow">{t("ДИАЛОГ ЗАВЕРШЁН")}</p>
              <h2>{t("Хотите получить разбор?")}</h2>
              <p>{t("Разбор опирается на реальные реплики и отмечает только то, что было видно в этом диалоге.")}</p>
              {session.debrief_status === 'failed' && error && <ErrorNotice message={error} onClose={onClearError} />}
              <div className="final-actions">
                <button className="button button-primary" onClick={onDebrief} disabled={!!action}>{action === 'judging' ? <><span className="spinner spinner--light" />{" "}{t("Разбираем диалог…")}</> : <>{t("Получить разбор")}{" "}<ArrowRight size={17} /></>}</button>
                <button className="button button-secondary" onClick={onSkip} disabled={!!action}>{action === 'skipping' ? <><span className="spinner" />{" "}{t("Завершаем…")}</> : t("Завершить без оценки")}</button>
              </div>
              <p className="final-footnote">{t("Учебные рекомендации независимого прототипа. Это не официальный балл.")}</p>
            </div>
          ) : session.debrief ? (
            <DebriefView report={session.debrief} messages={session.messages} onPlayAgain={onPlayAgain} />
          ) : showDone ? (
            <div className="final-card done-card"><div className="final-mark"><Check size={32} aria-hidden="true" /></div><p className="eyebrow">{t("ГОТОВО")}</p><h2>{t("Вы завершили диалог")}</h2><p>{t("Разбор не запрашивался. Если захотите продолжить, можно начать новую игру.")}</p><button className="button button-primary" onClick={onPlayAgain}>{t("Сыграть ещё")}{" "}<ArrowRight size={17} /></button></div>
          ) : (
            <div className="final-card"><p>{t("Сессия закрыта.")}</p><button className="button button-primary" onClick={onPlayAgain}>{t("Сыграть ещё")}</button></div>
          )}
        </section>
      </div>
      <footer className="game-footer"><span>{t("Независимый концепт для демонстрации")}</span><span>{preview ? t("Пример интерфейса · синтетические данные") : <>{session.engine.label || session.engine.model_id}{session.provider_mode === 'test_mock' ? t(" · тестовая симуляция") : ''}</>}</span></footer>
    </div>
  )
}

function CasePanel({ session, detailsOpen, setDetailsOpen }: { session: Session; detailsOpen: boolean; setDetailsOpen: (value: boolean) => void }) {
  const { t } = useI18n()
  const item = session.case
  const distinctStudentGoal = item.student_goal && meaningfullyDistinct(item.student_goal, [item.negotiation_topic, item.player_conflict_goal])
  return (
    <aside className="case-panel" aria-label={t("Публичная сводка кейса")}>
      <div className="case-primary">
        <div className="case-label-row"><span className="eyebrow">{t("СИТУАЦИЯ")}</span>{item.conflict_type !== 'none' && <span className="conflict-tag">{t(conflictChoices.find((choice) => choice.value === item.conflict_type)?.label || '')}</span>}</div>
        <h2>{item.title}</h2>
      </div>
      <div className="case-facts-primary">
        <div className="case-section"><span className="case-label">{t("Ваша роль")}</span><p>{item.student_role}</p></div>
        {item.negotiation_topic && <div className="case-section case-topic"><span className="case-label">{t("Тема на переговоры")}</span><p>{item.negotiation_topic}</p></div>}
        {item.player_conflict_goal && <div className="case-section case-goal"><span className="case-label">{t("Цель на конфликт")}</span><p>{item.player_conflict_goal}</p></div>}
        {distinctStudentGoal && <div className="case-section"><span className="case-label">{t("Ваша задача")}</span><p>{item.student_goal}</p></div>}
      </div>
      <details className="case-details" open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
        <summary>{t("Ситуация и факты")}{" "}<ChevronDown size={16} /></summary>
        <div className="case-secondary">
          <div className="case-section case-context"><span className="case-label">{t("Контекст")}</span><p>{item.context}</p></div>
          <div className="case-section"><span className="case-label">{t("Известные факты")}</span><ul>{item.known_facts.map((fact, index) => <li key={`${index}-${fact}`}>{fact}</li>)}</ul></div>
          {item.participants.length > 0 && <div className="case-section"><span className="case-label">{t("Участники")}</span><ul className="participants-list">{item.participants.map((person) => <li key={person.name}><strong>{person.name}</strong><span>{person.role}</span></li>)}</ul></div>}
        </div>
      </details>
    </aside>
  )
}

function DebriefView({ report, messages, onPlayAgain }: { report: Debrief; messages: ChatMessage[]; onPlayAgain: () => void }) {
  const { t } = useI18n()
  const [showHistory, setShowHistory] = useState(false)
  const quotes = [...report.strengths, ...report.risks].map((point) => point.quote)
  const evidenceMessages = messages.filter((message) => message.speaker === 'player' && quotes.some((quote) => message.text.includes(quote)))
  return (
    <div className="debrief-scroll">
      <div className="debrief-document">
        <div className="debrief-topline"><div><span className="eyebrow">{t("ПОСЛЕ ДИАЛОГА")}</span><h2>{t("Ваш разбор")}</h2></div></div>
        <p className="debrief-notice"><Sparkles size={15} />{" "}{t("Учебные рекомендации независимого прототипа")}</p>
        <section className="debrief-section"><h3>{t("Что произошло")}</h3><p>{report.summary}</p></section>
        {report.strengths.length > 0 && <section className="debrief-section"><h3><Check size={17} />{" "}{t("Сильные действия")}</h3><div className="evidence-list">{report.strengths.map((point, index) => <EvidencePoint key={`s-${index}`} point={point} kind="strength" />)}</div></section>}
        {report.risks.length > 0 && <section className="debrief-section"><h3>{t("Что можно изменить")}</h3><div className="evidence-list">{report.risks.map((point, index) => <EvidencePoint key={`r-${index}`} point={point} kind="risk" />)}</div></section>}
        <section className="debrief-section next-step-section"><h3>{t("Следующий ход")}</h3><p>{report.next_step}</p>{report.example_phrase && <blockquote><span>{t("Пример формулировки")}</span>{report.example_phrase}</blockquote>}</section>
        {evidenceMessages.length > 0 && <details className="history-details" open={showHistory} onToggle={(event) => setShowHistory(event.currentTarget.open)}><summary>{t("Посмотреть реплики из разбора")}{" "}<ChevronDown size={16} /></summary><div>{evidenceMessages.map((message) => <p className="history-quote" key={message.id}>{message.text}</p>)}</div></details>}
        <div className="debrief-actions"><button className="button button-primary" onClick={onPlayAgain}>{t("Сыграть ещё")}{" "}<ArrowRight size={17} /></button><span>{t("Раннее завершение не считается провалом.")}</span></div>
      </div>
    </div>
  )
}

function EvidencePoint({ point, kind }: { point: Point; kind: 'strength' | 'risk' }) {
  return <article className={`evidence-point evidence-point--${kind}`}><blockquote>{point.quote}</blockquote><p>{point.explanation}</p></article>
}

import { createContext, useContext } from 'react'

export type Language = 'ru' | 'en'
export const LANGUAGE_KEY = 'line-of-decision-language'
export const LanguageContext = createContext<Language>('ru')

const english: Record<string, string> = {
  'Конфликт': 'Conflict', 'Разговор о границах и отношениях': 'Boundaries and relationships',
  'Переговоры': 'Negotiation', 'Поиск рационального решения': 'Finding a practical solution',
  'Конфликт + переговоры': 'Conflict + negotiation', 'Конфликт может вернуться к теме': 'The conflict may return to the discussion',
  'Лёгкая': 'Easy', 'Средняя': 'Medium', 'Сложная': 'Hard', 'Очень сложная': 'Very hard', 'Желаемый исход закрыт': 'Outcome unattainable',
  'Личный': 'Private', 'Публичный': 'Public', 'Смешанный': 'Mixed',
  'Не удалось подключиться к приложению. Проверьте соединение и попробуйте ещё раз.': 'Cannot connect to the app. Check your connection and try again.',
  'Запрос не выполнен. Попробуйте ещё раз.': 'The request failed. Please try again.',
  'Что-то пошло не так. Попробуйте ещё раз.': 'Something went wrong. Please try again.',
  'Вы': 'You', 'Повторить': 'Retry', 'Закрыть сообщение': 'Dismiss message',
  'Не удалось проверить доступность модели.': 'Could not check model availability.', 'Настройки обновлены': 'Settings updated',
  'Укажите вашу тему для сферы «Другое».': 'Enter your topic for the Other setting.', 'Открываем сессию…': 'Opening your game…',
  'Тестовый режим: ответы и кейсы смоделированы локально, Claude/GPT API не вызывается.': 'Test mode: cases and replies are simulated locally; the Claude/GPT API is not called.',
  'API не подключён. Для настоящей генерации добавьте OPENROUTER_API_KEY на сервере; для локального теста задайте LLM_MODE=mock.': 'API not connected. Add OPENROUTER_API_KEY on the server for real generation, or set LLM_MODE=mock for a local test.',
  'Не удалось загрузить конфигурацию приложения:': 'Could not load the app configuration:',
  'Qwen · Дообученная': 'Qwen · Fine-tuned', 'Модель сейчас не подключена.': 'The model is not connected.',
  'Линия решения — к каталогу игр': 'Line of Decision — back to games', 'Линия решения': 'Line of Decision',
  'Независимый концепт': 'Independent concept', 'КОНФЛИКТЫ И ПЕРЕГОВОРЫ': 'CONFLICT AND NEGOTIATION',
  'Найдите следующий ход': 'Find your next move', 'Выберите ситуацию и попробуйте следующий ход в живом диалоге.': 'Choose a situation and try your next move in a live dialogue.',
  '01 / НАСТРОЙКА': '01 / SETUP', 'Настройка игры': 'Game setup', 'Режим': 'Mode', 'Режим игры': 'Game mode',
  'Тип конфликта': 'Conflict setting', 'Сложность': 'Difficulty',
  'Одно желаемое условие объективно недостижимо; осмысленный разговор всё ещё возможен.': 'One desired condition is objectively unattainable; a meaningful dialogue is still possible.',
  'Сфера': 'Setting', 'Работа': 'Work', 'Семья': 'Family', 'Учёба': 'Education', 'Друзья': 'Friends', 'Другое': 'Other',
  'Ваша сторона': 'Your side', 'Защищаю границы': 'Protecting my boundaries', 'Оказываю давление': 'Applying pressure',
  'Ваша тема': 'Your topic', 'Например, совместный проект или бытовая договорённость': 'For example, a shared project or a household agreement',
  'Ваше имя, необязательно': 'Your name, optional', 'Как к вам обращаться?': 'What should we call you?',
  'Модель собеседника': 'Conversation model', 'Серверная модель': 'Cloud model', 'Локальная модель': 'Local model', 'Наша дообученная модель': 'Our fine-tuned model',
  'Проверяем': 'Checking', 'Доступна': 'Available', 'Недоступна': 'Unavailable', 'Проверяем доступность…': 'Checking availability…',
  'Обновить доступность': 'Refresh availability', 'Случайно': 'Randomise', 'Готовим ситуацию…': 'Preparing your case…', 'Начать игру': 'Start game',
  'Независимый концепт для демонстрации': 'Independent demo concept', 'К играм': 'Back to games', 'ЛИНИЯ РЕШЕНИЯ': 'LINE OF DECISION',
  'Завершаем…': 'Finishing…', 'Завершить': 'Finish', 'Диалог завершён': 'Dialogue finished',
  'Тестовая симуляция: ответы не получены от': 'Test simulation: replies were not received from',
  'Резервный принятый TRAIN-кейс. Параметры выбранной сферы могли не примениться.': 'Accepted TRAIN fallback case. Your chosen setting may not have been applied.',
  'Подключённая модель недоступна; ответы не переключаются на другую модель.': 'The selected model is unavailable; replies will not switch to another model.',
  'Игровой чат': 'Game chat', 'Диалог': 'Dialogue', 'Собеседник отвечает…': 'Your counterpart is replying…',
  'Реплика сохранена': 'Your message is saved', 'Повторить ответ': 'Retry reply', 'Сессия завершена до ответа': 'The game ended before a reply arrived',
  'Новое сообщение': 'New message', 'Напишите ответ…': 'Write your reply…', 'Ваша реплика': 'Your reply', 'Отправить реплику': 'Send reply',
  'Enter — отправить · Shift + Enter — новая строка': 'Enter to send · Shift + Enter for a new line',
  'ДИАЛОГ ЗАВЕРШЁН': 'DIALOGUE FINISHED', 'Хотите получить разбор?': 'Would you like a review?',
  'Разбор опирается на реальные реплики и отмечает только то, что было видно в этом диалоге.': 'The review uses actual turns and discusses only what was observable in this dialogue.',
  'Разбираем диалог…': 'Reviewing your dialogue…', 'Получить разбор': 'Get review', 'Завершить без оценки': 'Finish without a review',
  'Учебные рекомендации независимого прототипа. Это не официальный балл.': 'Learning suggestions from an independent prototype. This is not an official grade.',
  'ГОТОВО': 'DONE', 'Вы завершили диалог': 'You have finished the dialogue',
  'Разбор не запрашивался. Если захотите продолжить, можно начать новую игру.': 'No review was requested. You can start another game whenever you are ready.',
  'Сыграть ещё': 'Play again', 'Сессия закрыта.': 'This game is closed.', 'Пример интерфейса · синтетические данные': 'Interface example · synthetic data',
  ' · тестовая симуляция': ' · test simulation', 'Публичная сводка кейса': 'Public case summary', 'СИТУАЦИЯ': 'SITUATION',
  'Ваша роль': 'Your role', 'Тема на переговоры': 'Negotiation topic', 'Цель на конфликт': 'Conflict goal', 'Ваша задача': 'Your task',
  'Ситуация и факты': 'Situation and facts', 'Контекст': 'Context', 'Известные факты': 'Known facts', 'Участники': 'Participants',
  'ПОСЛЕ ДИАЛОГА': 'AFTER THE DIALOGUE', 'Ваш разбор': 'Your review', 'Учебные рекомендации независимого прототипа': 'Learning suggestions from an independent prototype',
  'Что произошло': 'What happened', 'Сильные действия': 'What worked', 'Что можно изменить': 'What to change',
  'Следующий ход': 'Next move', 'Пример формулировки': 'Example wording', 'Посмотреть реплики из разбора': 'See the turns used in this review',
  'Раннее завершение не считается провалом.': 'Ending early is not failure.',
  'Язык игры': 'Game language', 'Qwen доступна только для игры на русском.': 'Qwen is available for Russian games only.',
  'Добавьте OPENROUTER_API_KEY в серверную среду.': 'Add OPENROUTER_API_KEY to the server environment.',
  'Пример дизайна': 'Design preview', 'синтетические данные': 'synthetic data', 'Примеры дизайна': 'Design examples',
  '· синтетические данные': '· synthetic data',
  'Давайте уточним этот пункт и зафиксируем, кто отвечает за следующий шаг.': 'Let us clarify this point and record who is responsible for the next step.',
  'Логотипы': 'Logos', 'Настройки': 'Setup', 'Чат': 'Chat', 'Разбор': 'Review', 'Три варианта знака': 'Three logo options',
  'Примерьте вариант в настройках, чате и разборе. Окончательный выбор — позже.': 'Try an option in setup, chat and review. The final choice comes later.',
  'Варианты логотипа': 'Logo options', 'В небольшом размере': 'At a small size', 'Посмотреть в интерфейсе': 'Try in the interface',
  'Сближение': 'Convergence', 'Две разные позиции встречаются в одной точке.': 'Two different positions meet at one point.',
  'Две реплики складываются в общий разговор.': 'Two turns become one conversation.', 'Поворот от противостояния к конкретному действию.': 'A turn from confrontation towards a concrete action.',
}

const errors: Record<string, string> = {
  network_error: 'Cannot connect to the app. Check your connection and try again.', ai_not_configured: 'Connect OpenRouter to start a real game.',
  provider_auth: 'OpenRouter rejected the credentials or model access. Check the server configuration.', provider_credits: 'The OpenRouter account has insufficient credits.',
  provider_timeout: 'The model did not reply in time. Please retry.', provider_rate_limit: 'The model is temporarily rate limited. Please try later.',
  proxy_auth: 'The proxy rejected authentication. Check the server proxy configuration.', proxy_unavailable: 'Could not connect through the proxy. Check its address and connection.',
  provider_unavailable: 'Could not connect to OpenRouter. Check the network and proxy.', provider_response: 'OpenRouter returned an error. Please retry.',
  provider_malformed: 'The model returned an empty or invalid response. Please retry.', provider_model_missing: 'The configured OpenRouter model or URL was not found.',
  lora_unavailable: 'Qwen is unavailable. Your message is saved; replies will not switch to another model.', lora_model_changed: 'The Qwen model or adapter changed. Restore the original checkpoint or start a new game.',
  engine_language_not_supported: 'English games require the OpenRouter model.', session_not_found: 'The saved game was not found.', session_finished: 'This game has finished.',
  session_active: 'Finish the dialogue before requesting a review.', debrief_pending: 'Your review is already being prepared.',
  message_too_long: 'Your message is too long. Shorten it and retry.', message_pending: 'This message is already being processed.',
  message_retry_required: 'Retry the reply to your saved message first.', request_id_conflict: 'This request ID was already used for a different message.',
  unsafe_roleplay_response: 'The reply failed the privacy check. Your message is saved; you can retry.', unsafe_judge_response: 'The review failed the privacy check. You can request it again.',
  invalid_judge_response: 'The review did not pass validation. You can request it again.', roleplayer_failed: 'Could not get a reply. Your message is saved; please retry.',
  judge_failed: 'Could not prepare the review. Please request it again.', case_generation_failed: 'Could not create a case. Check the API connection and retry.',
}

export const translate = (text: string, language: Language) => language === 'en' ? english[text] || text : text
export function useI18n() {
  const language = useContext(LanguageContext)
  return { language, t: (text: string) => translate(text, language) }
}
export function preferredLanguage(): Language {
  const query = new URLSearchParams(window.location.search).get('lang')
  if (query === 'ru' || query === 'en') return query
  try { return localStorage.getItem(LANGUAGE_KEY) === 'en' ? 'en' : 'ru' } catch { return 'ru' }
}
export function rememberLanguage(language: Language) {
  try { localStorage.setItem(LANGUAGE_KEY, language) } catch { /* URL keeps the choice when storage is unavailable. */ }
  const url = new URL(window.location.href)
  url.searchParams.set('lang', language)
  window.history.replaceState(null, '', url.pathname + url.search + url.hash)
  document.documentElement.lang = language
  document.title = language === 'en' ? 'Line of Decision — Conflict and negotiation' : 'Линия решения — Конфликты и переговоры'
}
export const catalogUrl = (language: Language) => `/games?lang=${language}`
export const sessionKey = (language: Language) => 'line-of-decision-session' + (language === 'en' ? '-en' : '')
export const settingsKey = (language: Language) => 'line-of-decision-settings' + (language === 'en' ? '-en' : '')
export function errorText(message: string, code: string | undefined, language: Language) {
  if (language === 'ru') return message
  return (code && errors[code]) || english[message] || (/[а-яё]/i.test(message) ? 'The request failed. Please try again.' : message)
}
export function LanguageSwitch({ onChange }: { onChange: (language: Language) => void }) {
  const { language, t } = useI18n()
  return <div className="language-switch" role="group" aria-label={t('Язык игры')}>{(['ru', 'en'] as const).map((value) => <button key={value} type="button" aria-pressed={language === value} onClick={() => onChange(value)}>{value.toUpperCase()}</button>)}</div>
}

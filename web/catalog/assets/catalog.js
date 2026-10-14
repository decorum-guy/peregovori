(() => {
  const copy = {
    ru: { title: 'Игры', subtitle: 'Выбери игру', initial: 'Л', name: 'Линия решения', description: 'Тренажёр конфликтов и переговоров с живым диалогом', play: 'Играть →', demo: 'Демо-версия' },
    en: { title: 'Games', subtitle: 'Choose a game', initial: 'L', name: 'Line of Decision', description: 'Conflict and negotiation practice with a live dialogue', play: 'Play →', demo: 'Demo version' },
  }
  function selectLanguage(lang) {
      if (!Object.hasOwn(copy, lang)) return
      document.documentElement.lang = lang
      document.querySelectorAll('[data-copy]').forEach((element) => { element.textContent = copy[lang][element.dataset.copy] })
      document.querySelectorAll('[data-lang]').forEach((item) => {
        const selected = item.dataset.lang === lang
        item.classList.toggle('is-on', selected)
        item.setAttribute('aria-pressed', String(selected))
      })
      document.title = lang === 'ru' ? 'Игры — Линия решения' : 'Games — Line of Decision'
      document.querySelector('.gh-card').href = '/games/line-decision?lang=' + lang
      try { localStorage.setItem('line-of-decision-language', lang) } catch { /* Keep the choice in the URL. */ }
      const url = new URL(window.location.href)
      url.searchParams.set('lang', lang)
      window.history.replaceState(null, '', url.pathname + url.search)
  }
  document.querySelectorAll('[data-lang]').forEach((button) => {
    button.addEventListener('click', () => selectLanguage(button.dataset.lang))
  })
  let saved = 'ru'
  try { saved = localStorage.getItem('line-of-decision-language') || 'ru' } catch { /* Default to Russian. */ }
  const query = new URLSearchParams(window.location.search).get('lang')
  selectLanguage(query === 'ru' || query === 'en' ? query : saved === 'en' ? 'en' : 'ru')
})()

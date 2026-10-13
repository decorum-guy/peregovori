(() => {
  const copy = {
    ru: { title: 'Игры', subtitle: 'Выбери игру', initial: 'Л', name: 'Линия решения', description: 'Тренажёр конфликтов и переговоров с живым диалогом', play: 'Играть →' },
    en: { title: 'Games', subtitle: 'Choose a game', initial: 'L', name: 'Line of Decision', description: 'Conflict and negotiation practice with a live dialogue in Russian', play: 'Play →' },
  }
  document.querySelectorAll('[data-lang]').forEach((button) => {
    button.addEventListener('click', () => {
      const lang = button.dataset.lang
      if (!copy[lang]) return
      document.documentElement.lang = lang
      document.querySelectorAll('[data-copy]').forEach((element) => { element.textContent = copy[lang][element.dataset.copy] })
      document.querySelectorAll('[data-lang]').forEach((item) => {
        const selected = item.dataset.lang === lang
        item.classList.toggle('is-on', selected)
        item.setAttribute('aria-pressed', String(selected))
      })
      document.title = lang === 'ru' ? 'Игры — Линия решения' : 'Games — Line of Decision'
    })
  })
})()

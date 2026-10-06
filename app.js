const items = [
  {id:'repair',title:'Изолированный ремонт',branch:'СИСТЕМА И ПРОВЕРКИ',x:17,y:57,color:'blue',good:'Исправление сначала живёт отдельно от стабильной версии. Можно посмотреть изменения и проверить результат, не рискуя рабочим Bossman.',next:'Я бы добавил наглядную историю: какая ошибка была, что поменялось, какие проверки прошли и почему кандидат приняли или отклонили.'},
  {id:'evolution',title:'Цикл самоулучшения',branch:'ПАМЯТЬ И ОБУЧЕНИЕ',x:27,y:39,color:'gold',good:'У цикла есть запуск, отчёт, пауза, остановка и продолжение. Развитие можно наблюдать, а контроль остаётся у владельца.',next:'Я бы показывал каждый шаг хронологией: найденная проблема, попытка, проверка и итог — с простым объяснением прогресса.'},
  {id:'v15',title:'Bossman 1.5',branch:'АГЕНТЫ И ОРКЕСТРАЦИЯ',x:38,y:26,color:'violet',good:'В одной панели собраны самоулучшение, автономность, наблюдения и входящие ремонты. Не нужно искать состояние по разным экранам.',next:'Я бы превратил панель в историю развития: что появилось, что проверено на практике и над чем Bossman работает сейчас.'},
  {id:'missions',title:'Миссии',branch:'ПРИЛОЖЕНИЯ И БИЗНЕС',x:11,y:43,color:'cyan',good:'Миссии превращают большое намерение в управляемую работу, а конструктор помогает собрать повторяемый сценарий.',next:'Я бы добавил дорожную карту миссии: этапы, участвующие агенты и понятный результат.'},
  {id:'agents',title:'Карта агентов',branch:'АГЕНТЫ И ОРКЕСТРАЦИЯ',x:45,y:20,color:'blue',good:'На карте видны реальные агенты и связи между ними, а не декоративная схема. Можно увидеть, как делится работа.',next:'Я бы добавил анимацию передачи задачи и подписи ролей: кто исследует, кто делает, кто проверяет.'},
  {id:'skills',title:'Навыки и MCP',branch:'НАВЫКИ',x:56,y:26,color:'gold',good:'Навыки можно создавать и переиспользовать, а инструменты MCP и их политики находятся рядом.',next:'Я бы показывал путь навыка: из какого опыта он вырос, как проверялся и где уже помог.'},
  {id:'models',title:'Маршрутизация моделей',branch:'ЛОКАЛЬНЫЕ МОДЕЛИ',x:67,y:36,color:'violet',good:'Есть отдельные инструменты выбора и сравнения моделей — основа для подбора подходящего исполнителя под задачу.',next:'Я бы объяснял выбор простыми словами: почему модель подходит, сколько займёт работа и какие есть альтернативы.'},
  {id:'browser',title:'Браузер',branch:'БРАУЗЕР И API',x:77,y:48,color:'cyan',good:'Агент работает в браузерной сессии, а человек может увидеть состояние страницы и перехватить управление.',next:'Я бы добавил понятный журнал браузерных шагов и удобный возврат к предыдущему этапу.'},
  {id:'telegram',title:'Telegram-консоль',branch:'ПЛАГИНЫ И КОННЕКТОРЫ',x:89,y:39,color:'blue',good:'Часть команд владельца доступна через Telegram — можно следить за работой и управлять циклом вдали от компьютера.',next:'Я бы сделал короткие уведомления о важных этапах с кнопками «отчёт», «пауза» и «продолжить».'},
  {id:'inbox',title:'Входящие ремонты',branch:'СИСТЕМА И ПРОВЕРКИ',x:91,y:57,color:'gold',good:'Очередь ошибок и кандидатов помогает не терять проблемы, а стабильная версия не меняется сама.',next:'Я бы добавил карточку «до и после»: причина, исправление, проверка и следующий шаг.'},
  {id:'forks',title:'Развилки задач',branch:'UX И CMD',x:25,y:66,color:'violet',good:'Задачу можно продолжить с контрольной точки, изменив инструкцию, агента или модель. Удобно исследовать разные пути.',next:'Я бы добавил сравнение ветвей: сколько занял каждый путь, что сработало лучше и какой результат сохранить.'},
];

const tree = document.querySelector('#tree');
const nodes = document.querySelector('#nodes');
const detail = document.querySelector('#detail');
document.querySelector('#count').textContent = `${items.length} направлений развития`;

function select(item, button) {
  nodes.querySelectorAll('.leaf.active,.leaf.preview-open').forEach((n) => n.classList.remove('active','preview-open'));
  button.classList.add('active');
  if (matchMedia('(hover:none),(pointer:coarse)').matches) button.classList.add('preview-open');
  detail.classList.remove('reveal');
  detail.innerHTML = `<div class="detail-body"><p class="eyebrow">${item.branch}</p><h2>${item.title}</h2><div class="chapter"><span>01</span><div><b>УЖЕ КРУТО</b><p>${item.good}</p></div></div><div class="chapter next"><span>02</span><div><b>ЧТО БЫ Я ДОБАВИЛ</b><p>${item.next}</p></div></div><div class="footnote">Это идея развития, а не обещание уже реализованной функции.</div></div>`;
  void detail.offsetWidth;
  detail.classList.add('reveal');
}

for (const item of items) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `leaf ${item.color}${item.x<23?' edge-left':''}${item.x>72?' edge-right':''}${item.y>55?' above':''}`;
  button.style.left = `${item.x}%`;
  button.style.top = `${item.y}%`;
  button.setAttribute('aria-label', `Посмотреть этап: ${item.title}`);
  button.innerHTML = `<span class="glyph">✦</span><span class="name">${item.title}</span><span class="preview"><b>${item.title}</b><small><strong>УЖЕ КРУТО</strong> ${item.good}</small><small class="idea"><strong>ДАЛЬШЕ</strong> ${item.next}</small></span>`;
  button.addEventListener('click', () => select(item, button));
  nodes.append(button);
}

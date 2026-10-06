function parseJsonScript(id) {
  const element = document.getElementById(id);
  if (!element) return null;
  try { return JSON.parse(element.textContent); } catch { return null; }
}

function initPurchaseFields() {
  const payment = document.getElementById('id_payment_method');
  const responsible = document.getElementById('id_responsible');
  if (!payment && !responsible) return;
  const vr = document.getElementById('modal-vr-box') || document.getElementById('vr-split-box');
  const installments = document.getElementById('modal-installment-box') || document.getElementById('installment-box');
  const person = document.getElementById('modal-person-box') || document.getElementById('person-name-box');
  const reimburse = document.getElementById('modal-reimburse-box') || document.getElementById('reimbursable-box');
  function sync() {
    const method = payment?.value;
    const other = responsible?.value === 'OTHER';
    vr?.classList.toggle('d-none', method !== 'VR' && method !== 'CREDIT_CARD');
    installments?.classList.toggle('d-none', method !== 'CREDIT_CARD');
    person?.classList.toggle('d-none', !other);
    reimburse?.classList.toggle('d-none', !other);
  }
  payment?.addEventListener('change', sync);
  responsible?.addEventListener('change', sync);
  sync();
}

function initTheme() {
  const root = document.documentElement;
  const buttons = document.querySelectorAll('[data-theme-toggle]');
  const labels = document.querySelectorAll('[data-theme-label]');
  const saved = localStorage.getItem('sf-theme') || 'dark';
  function apply(theme) {
    const resolved = theme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
    root.dataset.theme = resolved;
    labels.forEach((label) => { label.textContent = theme === 'system' ? 'Sistema' : theme === 'dark' ? 'Escuro' : 'Claro'; });
    localStorage.setItem('sf-theme', theme);
    window.dispatchEvent(new Event('sf-theme-change'));
  }
  apply(saved);
  buttons.forEach((button) => button.addEventListener('click', () => {
    const current = localStorage.getItem('sf-theme') || 'dark';
    apply(current === 'light' ? 'dark' : current === 'dark' ? 'system' : 'light');
  }));
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
    if ((localStorage.getItem('sf-theme') || 'dark') === 'system') apply('system');
  });
}

function initCharts() {
  if (typeof Chart === 'undefined') return;
  if (window.sfCharts) {
    window.sfCharts.forEach((chart) => chart.destroy());
  }
  window.sfCharts = [];
  const dashboard = parseJsonScript('dashboard-chart-data');
  const report = parseJsonScript('report-chart-data');
  if (!dashboard && !report) return;
  const dark = document.documentElement.dataset.theme === 'dark';
  const text = dark ? '#c7d0df' : '#667085';
  const grid = dark ? '#34445e' : '#e9edf3';
  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), 3);
  Chart.defaults.font.family = 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  Chart.defaults.color = text;
  Chart.defaults.animation.duration = 300;
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;
  const common = {
    responsive: true,
    maintainAspectRatio: false,
    devicePixelRatio: dpr,
    resizeDelay: 120,
    events: ['mousemove', 'mouseout', 'click', 'touchstart', 'touchmove'],
    interaction: { mode: 'nearest', intersect: true },
    layout: { padding: { top: 4, right: 8, bottom: 4, left: 4 } },
    plugins: {
      legend: { display: false },
      tooltip: { enabled: true, displayColors: true, backgroundColor: dark ? '#0b1220' : '#14213d', titleColor: '#fff', bodyColor: '#fff', borderColor: dark ? '#40506b' : '#263b68', borderWidth: 1, padding: 11, cornerRadius: 8, caretPadding: 8, titleFont: { weight: '700' }, bodyFont: { size: 12 } },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: text, font: { size: 11 }, maxRotation: 0 } },
      y: { grid: { color: grid }, ticks: { color: text, font: { size: 11 }, callback: (value) => money.format(value) } },
    },
  };
  const setCursor = (event, active) => { if (event.native?.target) event.native.target.style.cursor = active.length ? 'pointer' : 'default'; };
  const makeBar = (canvas, values, labels) => {
    if (!canvas) return;
    window.sfCharts.push(new Chart(canvas, { type: 'bar', data: { labels, datasets: [{ label: 'Valor', data: values, backgroundColor: ['#79b843', '#df6a65'], hoverBackgroundColor: ['#a9e873', '#f28a84'], borderRadius: 8, borderSkipped: false, barPercentage: .62, categoryPercentage: .62 }] }, options: { ...common, interaction: { mode: 'nearest', intersect: true }, plugins: { ...common.plugins, tooltip: { ...common.plugins.tooltip, callbacks: { title: (items) => items[0]?.label || '', label: (context) => `Valor: ${money.format(context.raw)}` } } }, onHover: setCursor } }));
  };
  const makeDonut = (canvas, labels, values) => {
    if (!canvas) return;
    const total = values.reduce((sum, value) => sum + value, 0);
    window.sfCharts.push(new Chart(canvas, { type: 'doughnut', data: { labels, datasets: [{ data: values, backgroundColor: ['#42661a', '#79b843', '#b7f36b', '#7390c9', '#df6a65', '#e7bb65'], hoverBackgroundColor: ['#668d32', '#a9e873', '#d5ff9f', '#9bb1df', '#f28a84', '#f4cf87'], hoverOffset: 8, borderWidth: 2, borderColor: dark ? '#172236' : '#fff' }] }, options: { ...common, cutout: '66%', interaction: { mode: 'nearest', intersect: true }, plugins: { ...common.plugins, legend: { display: true, position: 'bottom', labels: { color: text, boxWidth: 11, usePointStyle: true, padding: 14, font: { size: 11 } } }, tooltip: { ...common.plugins.tooltip, callbacks: { title: (items) => items[0]?.label || '', label: (context) => `Valor: ${money.format(context.raw)}`, afterLabel: (context) => `Participação: ${total ? ((context.raw / total) * 100).toFixed(1) : '0.0'}%` } } }, onHover: setCursor } }));
  };
  const makeLine = (canvas, labels, values) => {
    if (!canvas) return;
    window.sfCharts.push(new Chart(canvas, { type: 'line', data: { labels, datasets: [{ label: 'Saldo', data: values, borderColor: dark ? '#c6f584' : '#42661a', backgroundColor: dark ? 'rgba(198,245,132,.15)' : 'rgba(66,102,26,.10)', fill: true, tension: .35, pointRadius: 3, pointHoverRadius: 8, pointHoverBackgroundColor: dark ? '#fff' : '#14213d', pointHoverBorderColor: dark ? '#c6f584' : '#b7f36b', pointHoverBorderWidth: 3, borderWidth: 3 }] }, options: { ...common, interaction: { mode: 'index', intersect: false }, plugins: { ...common.plugins, tooltip: { ...common.plugins.tooltip, callbacks: { title: (items) => `Período: ${items[0]?.label || ''}`, label: (context) => `Saldo: ${money.format(context.parsed.y)}` } } }, onHover: setCursor } }));
  };
  if (dashboard) {
    makeBar(document.getElementById('chart-income-expense'), [dashboard.revenues, dashboard.expenses], ['Receitas', 'Despesas']);
    makeDonut(document.getElementById('chart-categories'), dashboard.category_labels, dashboard.category_values);
    makeLine(document.getElementById('chart-balance'), dashboard.balance_labels, dashboard.balance_values);
  }
  if (report) {
    makeBar(document.getElementById('report-income-expense'), [report.revenues, report.expenses], ['Receitas', 'Despesas']);
    makeDonut(document.getElementById('report-categories'), report.labels, report.values);
  }
}

document.addEventListener('DOMContentLoaded', () => { initPurchaseFields(); initTheme(); initCharts(); window.addEventListener('sf-theme-change', initCharts); });

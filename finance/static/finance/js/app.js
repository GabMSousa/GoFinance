function parseJsonScript(id) {
  const element = document.getElementById(id);
  if (!element) return null;
  try {
    const parsed = JSON.parse(element.textContent);
    return typeof parsed === 'string' ? JSON.parse(parsed) : parsed;
  } catch { return null; }
}

function initSecurityInteractions() {
  document.querySelectorAll('[data-confirm-submit]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirmSubmit)) event.preventDefault();
    });
  });
  const applyVrBadges = (id, selector, titleSelector) => {
    const indexes = parseJsonScript(id) || [];
    indexes.forEach((index) => {
      const row = document.querySelectorAll(selector)[index];
      if (!row) return;
      row.classList.add('vr-highlight');
      const title = row.querySelector(titleSelector);
      if (title && !title.querySelector('.vr-badge')) {
        title.insertAdjacentHTML('beforeend', '<span class="vr-badge">VR</span>');
      }
    });
  };
  applyVrBadges('vr-movement-indexes', '.movement-row', '.movement-main strong');
  applyVrBadges('vr-card-indexes', 'tbody tr', 'td strong');
  const money = (value) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value || 0));
  const movementDetails = parseJsonScript('movement-details') || [];
  document.querySelectorAll('.movement-row').forEach((row, index) => {
    const item = movementDetails[index];
    if (!item || Number(item.vr) <= 0) return;
    const target = row.querySelector('.movement-main');
    if (target && !target.querySelector('.movement-breakdown')) {
      target.insertAdjacentHTML('beforeend', `<span class="movement-breakdown">Total ${money(item.total)} · VR ${money(item.vr)} · Restante ${money(item.card)}</span>`);
    }
  });
  const cardDetails = parseJsonScript('vr-card-details') || [];
  document.querySelectorAll('tbody tr').forEach((row, index) => {
    const item = cardDetails[index];
    if (!item || Number(item.vr) <= 0) return;
    const target = row.querySelector('td:first-child');
    if (target && !target.querySelector('.movement-breakdown')) {
      target.insertAdjacentHTML('beforeend', `<div class="movement-breakdown">Total ${money(item.total)} · VR ${money(item.vr)} · Restante ${money(item.card)}</div>`);
    }
  });
}

function initPurchaseFields() {
  const payment = document.getElementById('id_payment_method');
  const responsible = document.getElementById('id_responsible');
  if (!payment && !responsible) return;
  const vr = document.getElementById('modal-vr-box') || document.getElementById('vr-split-box');
  const installments = document.getElementById('modal-installment-box') || document.getElementById('installment-box');
  const person = document.getElementById('modal-person-box') || document.getElementById('person-name-box');
  const reimburse = document.getElementById('modal-reimburse-box') || document.getElementById('reimbursable-box');
  const amountInput = document.getElementById('id_amount');
  const vrInput = document.getElementById('id_vr_amount');
  let remaining = vr?.querySelector('.vr-remaining');
  if (!remaining && amountInput?.dataset.totalWithVr === 'true' && vrInput) {
    remaining = document.createElement('div');
    remaining.className = 'form-text vr-remaining';
    remaining.setAttribute('aria-live', 'polite');
    vrInput.parentElement.appendChild(remaining);
  } else if (vr && !remaining) {
    remaining = document.createElement('div');
    remaining.className = 'form-text vr-remaining';
    remaining.setAttribute('aria-live', 'polite');
    vr.appendChild(remaining);
  }
  const parseAmount = (input) => Number(String(input?.value || '0').replace(',', '.')) || 0;
  const money = (value) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value || 0));
  const updateRemaining = () => {
    if (!remaining) return;
    const total = parseAmount(amountInput);
    const spent = Math.min(Math.max(parseAmount(vrInput), 0), total);
    remaining.textContent = `Restante: ${money(total - spent)}`;
  };
  function sync() {
    const method = payment?.value;
    const other = responsible?.value === 'OTHER';
    vr?.classList.remove('d-none');
    installments?.classList.toggle('d-none', method !== 'CREDIT_CARD');
    person?.classList.toggle('d-none', !other);
    reimburse?.classList.toggle('d-none', !other);
    updateRemaining();
  }
  payment?.addEventListener('change', sync);
  responsible?.addEventListener('change', sync);
  amountInput?.addEventListener('input', updateRemaining);
  vrInput?.addEventListener('input', updateRemaining);
  sync();
}

function initPurchasePeriod() {
  const form = document.querySelector('#purchaseFormPanel form');
  if (!form) return;
  const params = new URLSearchParams(window.location.search);
  const year = Number(params.get('year'));
  const month = Number(params.get('month'));
  if (!year || month < 1 || month > 12) return;
  // The dashboard period is only navigation state. Keep the real purchase
  // date entered by the user; the backend calculates the invoice from it.
  form.action = `${form.action.split('?')[0]}?year=${year}&month=${month}`;
  ['year', 'month'].forEach((part) => {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = `period_${part}`;
    input.value = part === 'year' ? year : month;
    form.appendChild(input);
  });
}

function initQuickPurchaseFeedback() {
  const errors = document.getElementById('quick-purchase-errors');
  const form = document.querySelector('#purchaseFormPanel form');
  if (!form) return;
  const submit = form.querySelector('button[type="submit"]');
  form.addEventListener('submit', () => {
    if (!submit || form.dataset.submitting === 'true') return;
    form.dataset.submitting = 'true';
    submit.disabled = true;
    submit.textContent = 'Salvando...';
  });
  if (!errors) return;
  form.prepend(errors);
  errors.classList.remove('d-none');
  document.getElementById('purchaseFormPanel')?.classList.add('show');
  const modal = document.getElementById('addModal');
  if (modal && window.bootstrap) bootstrap.Modal.getOrCreateInstance(modal).show();
}

function initTheme() {
  const root = document.documentElement;
  const buttons = document.querySelectorAll('[data-theme-toggle]');
  const labels = document.querySelectorAll('[data-theme-label]');
  const storageKey = 'sf-theme';
  const getSavedTheme = () => {
    try { return localStorage.getItem(storageKey) || 'dark'; } catch (error) { return 'dark'; }
  };
  const saveTheme = (theme) => {
    try { localStorage.setItem(storageKey, theme); } catch (error) { /* armazenamento indisponível */ }
  };
  function apply(theme) {
    const resolved = theme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
    root.dataset.theme = resolved;
    labels.forEach((label) => { label.textContent = theme === 'system' ? 'Sistema' : theme === 'dark' ? 'Escuro' : 'Claro'; });
    saveTheme(theme);
    window.dispatchEvent(new Event('sf-theme-change'));
  }
  apply(getSavedTheme());
  buttons.forEach((button) => button.addEventListener('click', () => {
    const current = getSavedTheme();
    apply(current === 'light' ? 'dark' : current === 'dark' ? 'system' : 'light');
  }));
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
    if (getSavedTheme() === 'system') apply('system');
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
    const colors = ['#0c7128', '#5f0e18', '#4dd2c8'];
    const hoverColors = ['#0ce93e', '#ff0020', '#83eee5'];
    window.sfCharts.push(new Chart(canvas, { type: 'bar', data: { labels, datasets: [{ label: 'Valor', data: values, backgroundColor: colors.slice(0, values.length), hoverBackgroundColor: hoverColors.slice(0, values.length), borderRadius: 8, borderSkipped: false, barPercentage: .62, categoryPercentage: .62 }] }, options: { ...common, interaction: { mode: 'nearest', intersect: true }, plugins: { ...common.plugins, tooltip: { ...common.plugins.tooltip, callbacks: { title: (items) => items[0]?.label || '', label: (context) => `Valor: ${money.format(context.raw)}` } } }, onHover: setCursor } }));
  };
  const makeDonut = (canvas, labels, values) => {
    if (!canvas) return;
    const total = values.reduce((sum, value) => sum + value, 0);
    window.sfCharts.push(new Chart(canvas, { type: 'doughnut', data: { labels, datasets: [{ data: values, backgroundColor: ['#0c7128', '#0c7128', '#0c7128', '#7390c9', '#5f0e18', '#e7bb65'], hoverBackgroundColor: ['#0ce93e', '#0ce93e', '#0ce93e', '#9bb1df', '#ff0020', '#f4cf87'], hoverOffset: 8, borderWidth: 2, borderColor: dark ? '#172236' : '#fff' }] }, options: { ...common, cutout: '66%', interaction: { mode: 'nearest', intersect: true }, plugins: { ...common.plugins, legend: { display: true, position: 'bottom', labels: { color: text, boxWidth: 11, usePointStyle: true, padding: 14, font: { size: 11 } } }, tooltip: { ...common.plugins.tooltip, callbacks: { title: (items) => items[0]?.label || '', label: (context) => `Valor: ${money.format(context.raw)}`, afterLabel: (context) => `Participação: ${total ? ((context.raw / total) * 100).toFixed(1) : '0.0'}%` } } }, onHover: setCursor } }));
  };
  const makeLine = (canvas, labels, values) => {
    if (!canvas) return;
    window.sfCharts.push(new Chart(canvas, { type: 'line', data: { labels, datasets: [{ label: 'Saldo', data: values, borderColor: '#0ce93e', backgroundColor: dark ? 'rgba(12,113,40,.22)' : 'rgba(12,113,40,.12)', fill: true, tension: .35, pointRadius: 3, pointHoverRadius: 8, pointHoverBackgroundColor: dark ? '#fff' : '#14213d', pointHoverBorderColor: '#0ce93e', pointHoverBorderWidth: 3, borderWidth: 3 }] }, options: { ...common, interaction: { mode: 'index', intersect: false }, plugins: { ...common.plugins, tooltip: { ...common.plugins.tooltip, callbacks: { title: (items) => `Período: ${items[0]?.label || ''}`, label: (context) => `Saldo: ${money.format(context.parsed.y)}` } } }, onHover: setCursor } }));
  };
  if (dashboard) {
    makeBar(document.getElementById('chart-income-expense'), [dashboard.revenues, dashboard.expenses, dashboard.investments], ['Entradas', 'Saídas', 'Aplicações']);
    makeDonut(document.getElementById('chart-categories'), dashboard.category_labels, dashboard.category_values);
    makeLine(document.getElementById('chart-balance'), dashboard.balance_labels, dashboard.balance_values);
  }
  if (report) {
    makeBar(document.getElementById('report-income-expense'), [report.revenues, report.expenses, report.investments], ['Entradas', 'Saídas', 'Aplicações']);
    makeDonut(document.getElementById('report-categories'), report.labels, report.values);
  }
}

document.addEventListener('DOMContentLoaded', () => { initPurchaseFields(); initPurchasePeriod(); initQuickPurchaseFeedback(); initTheme(); initSecurityInteractions(); initCharts(); window.addEventListener('sf-theme-change', initCharts); });

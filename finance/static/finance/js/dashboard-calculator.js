(function () {
  'use strict';

  const root = document.querySelector('[data-dashboard-calculator]');
  if (!root) return;

  const toggle = root.querySelector('[data-calculator-toggle]');
  const display = root.querySelector('[data-calculator-display]');
  let current = '0';
  let stored = null;
  let operator = null;
  let waitingForOperand = false;

  function render(value) {
    if (value === 'Erro' || value.endsWith(',')) {
      display.textContent = value;
      return;
    }
    const numeric = Number(value.replace(',', '.'));
    display.textContent = value.length > 16 && Number.isFinite(numeric)
      ? numeric.toLocaleString('pt-BR', { useGrouping: false, maximumFractionDigits: 2 })
      : value;
  }

  function clipboardValue() {
    return display.textContent === 'Erro' ? '' : display.textContent;
  }

  async function copyValue() {
    const value = clipboardValue();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
    } catch (error) {
      const helper = document.createElement('textarea');
      helper.value = value;
      helper.setAttribute('readonly', '');
      helper.style.position = 'fixed';
      helper.style.opacity = '0';
      document.body.appendChild(helper);
      helper.select();
      document.execCommand('copy');
      helper.remove();
    }
  }

  function parseClipboard(value) {
    const clean = value.trim().replace(/\s/g, '');
    if (!clean) return null;
    const normalized = clean.includes(',')
      ? clean.replace(/\./g, '').replace(',', '.')
      : clean;
    const numeric = Number(normalized);
    return Number.isFinite(numeric) ? String(numeric).replace('.', ',') : null;
  }

  async function pasteValue() {
    try {
      const parsed = parseClipboard(await navigator.clipboard.readText());
      if (parsed === null) return;
      current = parsed;
      waitingForOperand = false;
      render(current);
    } catch (error) {
      display.focus?.();
    }
  }

  function calculate(left, right, sign) {
    if (sign === '+') return left + right;
    if (sign === '\u2212') return left - right;
    if (sign === '\u00d7') return left * right;
    if (sign === '\u00f7') return right === 0 ? null : left / right;
    return right;
  }

  function digit(value) {
    if (waitingForOperand || current === 'Erro') {
      current = value;
      waitingForOperand = false;
    } else {
      current = current === '0' ? value : current + value;
    }
    render(current);
  }

  function decimal() {
    if (waitingForOperand || current === 'Erro') {
      current = '0,';
      waitingForOperand = false;
    } else if (!current.includes(',')) {
      current += ',';
    }
    render(current);
  }

  function chooseOperator(sign) {
    const value = Number(current.replace(',', '.'));
    if (Number.isNaN(value)) return;
    if (stored !== null && operator && !waitingForOperand) {
      const result = calculate(stored, value, operator);
      if (result === null) { current = 'Erro'; stored = null; operator = null; render(current); return; }
      stored = result;
      current = String(result).replace('.', ',');
    } else {
      stored = value;
    }
    operator = sign;
    waitingForOperand = true;
    render(current);
  }

  function equals() {
    if (stored === null || !operator) return;
    const result = calculate(stored, Number(current.replace(',', '.')), operator);
    current = result === null ? 'Erro' : String(result).replace('.', ',');
    stored = null;
    operator = null;
    waitingForOperand = true;
    render(current);
  }

  function clear() {
    current = '0'; stored = null; operator = null; waitingForOperand = false; render(current);
  }

  function toggleSign() {
    if (current === '0' || current === 'Erro') return;
    current = current.startsWith('-') ? current.slice(1) : `-${current}`;
    render(current);
  }

  function percent() {
    const value = Number(current.replace(',', '.'));
    if (!Number.isNaN(value)) {
      current = String(value / 100).replace('.', ',');
      render(current);
    }
  }

  toggle.addEventListener('click', function () {
    const open = root.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
  });

  document.addEventListener('click', function (event) {
    if (!root.classList.contains('is-open') || root.contains(event.target)) return;
    root.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
  });

  root.addEventListener('click', function (event) {
    const clipboardButton = event.target.closest('[data-calculator-clipboard]');
    if (clipboardButton) {
      event.preventDefault();
      if (clipboardButton.dataset.calculatorClipboard === 'copy') copyValue();
      else pasteValue();
      return;
    }
    const button = event.target.closest('[data-calculator-key]');
    if (!button) return;
    event.preventDefault();
    const action = button.dataset.calculatorKey;
    if (action === 'digit') digit(button.dataset.value);
    else if (action === 'decimal') decimal();
    else if (action === 'operator') chooseOperator(button.dataset.value);
    else if (action === 'equals') equals();
    else if (action === 'clear') clear();
    else if (action === 'sign') toggleSign();
    else if (action === 'percent') percent();
  });

  document.addEventListener('keydown', function (event) {
    if (!root.classList.contains('is-open')) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {
      event.preventDefault();
      copyValue();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'v') {
      event.preventDefault();
      pasteValue();
    }
  });
}());

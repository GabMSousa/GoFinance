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
    display.textContent = value.length > 16 ? Number(value.replace(',', '.')).toPrecision(12).replace('.', ',') : value;
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
}());

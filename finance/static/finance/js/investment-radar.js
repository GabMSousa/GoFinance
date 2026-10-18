(function () {
  const dataNode = document.getElementById('investment-radar-data');
  if (!dataNode) return;
  let data;
  try { data = JSON.parse(dataNode.textContent); } catch (error) { return; }
  const radar = document.querySelector('.investment-radar');
  if (!radar) return;
  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const principal = radar.querySelector('[data-radar-principal]');
  const percent = radar.querySelector('[data-radar-percent]');
  const months = radar.querySelector('[data-radar-months]');
  const gross = radar.querySelector('[data-radar-gross]');
  const net = radar.querySelector('[data-radar-net]');
  const finalValue = radar.querySelector('[data-radar-final]');
  const help = radar.querySelector('[data-radar-help]');
  const rate = Number(data.base_rate);
  const format = (value) => Number.isFinite(value) ? money.format(value) : 'Indisponível';
  function calculate() {
    const amount = Number(principal.value);
    const share = Number(percent.value);
    const term = Number(months.value);
    if (!Number.isFinite(rate) || amount <= 0 || share < 0 || term <= 0) {
      gross.textContent = net.textContent = finalValue.textContent = 'Indisponível';
      help.textContent = 'O CDI de referência ou os campos do simulador estão indisponíveis.';
      return;
    }
    const monthlyRate = Math.pow(1 + ((rate / 100) * (share / 100)), 1 / 12) - 1;
    const ending = amount * Math.pow(1 + monthlyRate, term);
    const grossGain = ending - amount;
    const days = term * 30;
    const tax = days <= 180 ? .225 : days <= 360 ? .20 : days <= 720 ? .175 : .15;
    if (gross) gross.textContent = format(grossGain);
    net.textContent = format(grossGain * (1 - tax));
    finalValue.textContent = format(amount + grossGain * (1 - tax));
    help.textContent = `Estimativa com IR regressivo de ${(tax * 100).toFixed(1).replace('.', ',')}% para renda fixa tributável; não é garantia.`;
  }
  [principal, percent, months].forEach((field) => field.addEventListener('input', calculate));
  calculate();
})();

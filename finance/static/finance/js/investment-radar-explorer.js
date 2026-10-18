(function () {
  const radar = document.querySelector('.investment-radar');
  const explorer = radar?.querySelector('[data-radar-explorer]');
  const dataNode = document.getElementById('investment-radar-data');
  if (!radar || !explorer || !dataNode) return;

  let data;
  try { data = JSON.parse(dataNode.textContent); } catch (error) { return; }

  const search = explorer.querySelector('[data-radar-search]');
  const sort = explorer.querySelector('[data-radar-sort]');
  const filters = [...explorer.querySelectorAll('[data-radar-filter]')];
  const results = explorer.querySelector('[data-radar-results]');
  const count = explorer.querySelector('[data-radar-result-count]');
  const syncStatus = explorer.querySelector('[data-radar-sync-status]');
  const sourceNote = explorer.querySelector('[data-radar-source-note]');
  const refreshButton = explorer.querySelector('[data-radar-refresh]');
  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const text = (value, fallback = 'NÃ£o informado') => value === undefined || value === null || value === '' ? fallback : String(value);
  const normalize = (value) => text(value, '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

  function updateIndicators() {
    const indicators = Array.isArray(data.indicators) ? data.indicators : [];
    radar.querySelectorAll('.radar-indicator').forEach((element, index) => {
      const indicator = indicators[index];
      if (!indicator) return;
      const value = element.querySelector('strong');
      const base = element.querySelector('small');
      value.textContent = indicator.available ? text(indicator.formatted) : 'IndisponÃ­vel';
      value.classList.toggle('is-unavailable', !indicator.available);
      base.textContent = indicator.date ? `Base ${indicator.date}` : 'Fonte indisponÃ­vel';
    });
    const offersMessage = radar.querySelector('.radar-offers p');
    if (offersMessage && data.offers_message) offersMessage.textContent = data.offers_message;
    if (sourceNote) sourceNote.textContent = Array.isArray(data.sources) && data.sources.length ? `Fontes: ${data.sources.map((source) => source.label).join(' · ')}` : 'Fonte oficial nÃ£o informada';
  }

  function matches(offer) {
    const query = normalize(search.value);
    const haystack = normalize([offer.name, offer.institution, offer.type, offer.return_type].join(' '));
    if (query && !haystack.includes(query)) return false;
    return filters.every((field) => !field.value || normalize(offer[field.dataset.radarFilter]) === normalize(field.value));
  }

  function offerValue(offer, key) {
    const value = Number(offer[key]);
    return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
  }

  function renderCard(offer) {
    const card = document.createElement('article');
    card.className = 'radar-offer-card';
    const heading = document.createElement('div');
    heading.className = 'radar-offer-heading';
    const title = document.createElement('strong');
    title.textContent = text(offer.name);
    const institution = document.createElement('span');
    institution.textContent = text(offer.institution);
    heading.append(title, institution);
    const summary = document.createElement('div');
    summary.className = 'radar-offer-summary';
    [[ 'Rentabilidade', offer.return_label || offer.return_type ], [ 'Liquidez', offer.liquidity ], [ 'Prazo', offer.term ], [ 'Aplicação mínima', offer.minimum ]].forEach(([label, value]) => {
      const item = document.createElement('div');
      const caption = document.createElement('span');
      caption.textContent = label;
      const content = document.createElement('strong');
      content.textContent = text(value);
      item.append(caption, content);
      summary.append(item);
    });
    const actions = document.createElement('div');
    actions.className = 'radar-offer-actions';
    const details = document.createElement('details');
    const detailsSummary = document.createElement('summary');
    detailsSummary.textContent = 'Detalhes';
    const detailsBody = document.createElement('div');
    detailsBody.className = 'radar-offer-details';
    [['Risco', offer.risk], ['Tributação', offer.tax], ['FGC', offer.fgc], ['Vencimento', offer.maturity], ['Verificado em', offer.verified_at]].forEach(([label, value]) => {
      const row = document.createElement('p');
      row.innerHTML = `<span>${label}</span>`;
      const strong = document.createElement('strong');
      strong.textContent = text(value);
      row.append(strong);
      detailsBody.append(row);
    });
    details.append(detailsSummary, detailsBody);
    actions.append(details);
    if (offer.source_url) {
      const source = document.createElement('a');
      source.className = 'radar-source-link';
      source.href = offer.source_url;
      source.target = '_blank';
      source.rel = 'noopener noreferrer';
      source.textContent = offer.source_label || 'Fonte oficial';
      actions.append(source);
    }
    if (offer.simulation) {
      const select = document.createElement('button');
      select.type = 'button';
      select.className = 'radar-select-offer';
      select.textContent = 'Usar no simulador';
      select.addEventListener('click', () => {
        const simulation = offer.simulation;
        const fields = {
          principal: simulation.amount,
          percent: simulation.percent_cdi,
          months: simulation.months,
        };
        Object.entries(fields).forEach(([key, value]) => {
          const field = radar.querySelector(`[data-radar-${key}]`);
          if (field && value !== undefined) field.value = value;
          field?.dispatchEvent(new Event('input', { bubbles: true }));
        });
      });
      actions.append(select);
    }
    card.append(heading, summary, actions);
    return card;
  }

  function render() {
    const offers = (Array.isArray(data.offers) ? data.offers : []).filter(matches);
    const mode = sort.value;
    offers.sort((left, right) => mode === 'name' ? text(left.name).localeCompare(text(right.name), 'pt-BR') : offerValue(left, mode) - offerValue(right, mode));
    count.textContent = `${offers.length} resultado${offers.length === 1 ? '' : 's'}`;
    results.replaceChildren();
    if (!offers.length) {
      const empty = document.createElement('div');
      empty.className = 'radar-empty';
      const title = document.createElement('strong');
      title.textContent = 'Nenhuma oferta verificável encontrada';
      const message = document.createElement('p');
      message.textContent = data.offers_message || 'Consulte as condições diretamente no aplicativo da instituição.';
      empty.append(title, message);
      results.append(empty);
      return;
    }
    offers.forEach((offer) => results.append(renderCard(offer)));
  }

  async function refresh(force) {
    const url = radar.dataset.radarRefreshUrl;
    if (!url || refreshButton.disabled) return;
    refreshButton.disabled = true;
    syncStatus.textContent = 'atualizando...';
    try {
      const response = await fetch(`${url}?refresh=${force ? '1' : '0'}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('radar unavailable');
      data = await response.json();
      updateIndicators();
      syncStatus.textContent = data.sync_state || 'atualizado';
      render();
    } catch (error) {
      syncStatus.textContent = 'indisponivel';
    } finally {
      refreshButton.disabled = false;
    }
  }

  [search, sort, ...filters].forEach((field) => field?.addEventListener('input', render));
  [sort, ...filters].forEach((field) => field?.addEventListener('change', render));
  refreshButton?.addEventListener('click', () => refresh(true));
  updateIndicators();
  render();

  const refreshWhenVisible = () => refresh(false);
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) refreshWhenVisible(); }, { threshold: .1 });
    observer.observe(radar);
  }
  window.setInterval(() => {
    if (!document.hidden && radar.getBoundingClientRect().top < window.innerHeight && radar.getBoundingClientRect().bottom > 0) refreshWhenVisible();
  }, 300000);
})();

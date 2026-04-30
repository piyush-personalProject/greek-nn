// static/js/greeks_ui.js

// Global state
let ws = null;
let currentPortfolio = 'FX-PORTFOLIO-01';
let ladderChart = null;
let currentGreeks = {
    delta: 0, gamma: 0, vega: 0, theta: 0, rho: 0
};
let currentHeadlines = [];
let showingImpact = false;
let currentImpactData = null;

// ==================== Initialization ====================

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing...');
    try {
        initializeWebSocket();
    } catch (e) {
        console.error('WebSocket init error:', e);
    }
    try {
        initializeEventListeners();
    } catch (e) {
        console.error('Event listeners init error:', e);
    }
    try {
        loadInitialData();
    } catch (e) {
        console.error('Initial data load error:', e);
    }
    try {
        initializeChart();
    } catch (e) {
        console.error('Chart init error:', e);
    }
});

// ==================== WebSocket Connection ====================

function initializeWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/greeks`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        updateConnectionStatus(true);
        console.log('WebSocket connected');
    };
    
    ws.onclose = () => {
        updateConnectionStatus(false);
        console.log('WebSocket disconnected. Reconnecting in 3s...');
        setTimeout(initializeWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
}

function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('wsStatus');
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('.status-text');
    
    if (connected) {
        dot.classList.remove('disconnected');
        dot.classList.add('connected');
        text.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        dot.classList.add('disconnected');
        text.textContent = 'Disconnected';
    }
}

function handleWebSocketMessage(data) {
    if (data.type === 'tick') {
        updateGreeksFromTick(data);
        updateTimestamp(data.timestamp);
    } else if (data.type === 'trade_added') {
        showAlert('success', 'Trade Added', `New trade ${data.trade_id} has been added`);
        loadPortfolioPositions();
        loadGreeks();
    } else if (data.type === 'trade_removed') {
        showAlert('info', 'Trade Removed', `Trade ${data.trade_id} has been removed`);
        loadPortfolioPositions();
        loadGreeks();
    }
}

function updateGreeksFromTick(data) {
    if (data.total_greeks) {
        currentGreeks = data.total_greeks;
        updateGreeksDisplay(data.total_greeks);
    }
    
    if (data.spot_rates) {
        updateSpotRatesDisplay(data.spot_rates);
    }
}

// ==================== Event Listeners ====================

function initializeEventListeners() {
    // Portfolio selector
    document.getElementById('portfolioSelect').addEventListener('change', (e) => {
        currentPortfolio = e.target.value;
        loadGreeks();
        loadTimeLadder();
        loadPortfolioPositions();
    });
    
    // Greek type selector for ladder
    document.getElementById('ladderGreekSelect').addEventListener('change', () => {
        loadTimeLadder();
    });
    
    // Add trade button
    document.getElementById('addTradeBtn').addEventListener('click', () => {
        openTradeModal();
    });
    
    // Close modal
    document.getElementById('closeModalBtn').addEventListener('click', () => {
        closeTradeModal();
    });
    
    // Trade form
    document.getElementById('tradeForm').addEventListener('submit', handleTradeSubmit);
    
    // Click outside modal to close
    document.getElementById('tradeModal').addEventListener('click', (e) => {
        if (e.target.id === 'tradeModal') {
            closeTradeModal();
        }
    });
    
    // News search filter
    document.getElementById('newsSearchInput').addEventListener('input', (e) => {
        filterNews(e.target.value);
    });
    
    // Show Impact button
    document.getElementById('showImpactBtn').addEventListener('click', () => {
        toggleNewsImpact();
    });
}

// ==================== Data Loading ====================

async function loadInitialData() {
    console.log('loadInitialData started');
    try {
        await Promise.all([
            loadGreeks(),
            loadTimeLadder(),
            loadSpotRates(),
            loadVolSurface(),
            loadPortfolioPositions(),
            loadNews()
        ]);
        console.log('loadInitialData completed');
    } catch (error) {
        console.error('loadInitialData error:', error);
    }
}

async function loadGreeks() {
    try {
        const response = await fetch(`/api/portfolios/${currentPortfolio}/greeks`);
        const data = await response.json();
        
        if (data.total_greeks) {
            currentGreeks = data.total_greeks;
            updateGreeksDisplay(data.total_greeks);
        }
    } catch (error) {
        console.error('Failed to load Greeks:', error);
    }
}

async function loadSpotRates() {
    try {
        const response = await fetch('/api/spot-rates');
        const data = await response.json();
        updateSpotRatesDisplay(data.rates);
    } catch (error) {
        console.error('Failed to load spot rates:', error);
    }
}

async function loadVolSurface() {
    try {
        const response = await fetch('/api/vol-surface');
        const data = await response.json();
        updateVolSurfaceDisplay(data);
    } catch (error) {
        console.error('Failed to load vol surface:', error);
    }
}

async function loadTimeLadder() {
    try {
        const greekType = document.getElementById('ladderGreekSelect').value;
        const response = await fetch(`/api/portfolios/${currentPortfolio}/time-ladder?greek_type=${greekType}`);
        const data = await response.json();
        
        updateLadderChart(data.ladder, greekType);
        updateLadderTable(data.ladder);
    } catch (error) {
        console.error('Failed to load time ladder:', error);
    }
}

async function loadPortfolioPositions() {
    try {
        const response = await fetch(`/api/portfolios/${currentPortfolio}`);
        const data = await response.json();
        
        if (data.positions) {
            // Get Greeks for each position
            const greeksResponse = await fetch(`/api/portfolios/${currentPortfolio}/greeks`);
            const greeksData = await greeksResponse.json();
            
            updatePositionsList(data.positions, greeksData.position_greeks || {});
        }
    } catch (error) {
        console.error('Failed to load positions:', error);
    }
}

async function loadNews() {
    try {
        console.log('Fetching news from /api/news...');
        const response = await fetch('/api/news');
        console.log('News response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('News API error:', response.status, errorText);
            updateNewsList([]);
            showNewsError(`Failed to load news (${response.status})`);
            return;
        }
        
        const data = await response.json();
        console.log('News data received:', data.count, 'headlines');
        
        // Sort by published_at descending
        const sortedHeadlines = (data.headlines || []).sort((a, b) => {
            const dateA = new Date(a.published_at || 0);
            const dateB = new Date(b.published_at || 0);
            return dateB - dateA;
        });
        
        currentHeadlines = sortedHeadlines;
        console.log('Current headlines count:', currentHeadlines.length);
        updateNewsList(currentHeadlines);
        
        if (currentHeadlines.length === 0) {
            showNewsError('No news headlines available');
        }
    } catch (error) {
        console.error('Failed to load news:', error);
        updateNewsList([]);
        showNewsError('Failed to load news: ' + error.message);
    }
}

function showNewsError(message) {
    const container = document.getElementById('newsList');
    if (container) {
        container.innerHTML = `<div class="news-error">${message}</div>`;
    }
}

function filterNews(query) {
    if (!query) {
        updateNewsList(currentHeadlines);
        return;
    }
    const lower = query.toLowerCase();
    const filtered = currentHeadlines.filter(h => 
        h.headline.toLowerCase().includes(lower) ||
        (h.content && h.content.toLowerCase().includes(lower)) ||
        h.source.toLowerCase().includes(lower)
    );
    updateNewsList(filtered);
}

function toggleNewsImpact() {
    if (showingImpact) {
        // Switch back to normal news view
        showingImpact = false;
        document.getElementById('newsList').style.display = 'block';
        document.getElementById('newsImpactList').style.display = 'none';
        document.getElementById('newsImpactSummary').style.display = 'none';
        document.getElementById('showImpactBtn').textContent = 'Show Impact';
    } else {
        // Load and show impact
        loadNewsImpact();
    }
}

async function loadNewsImpact() {
    const impactListContainer = document.getElementById('newsImpactList');
    
    // Show loading state
    impactListContainer.innerHTML = '<div class="news-loading">Loading news impact data...</div>';
    impactListContainer.style.display = 'block';
    document.getElementById('newsList').style.display = 'none';
    document.getElementById('newsImpactSummary').style.display = 'flex';
    showingImpact = true;
    document.getElementById('showImpactBtn').textContent = 'Hide Impact';
    
    try {
        const response = await fetch('/api/news-impact?max_results=10');
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to load news impact (${response.status}): ${errorText}`);
        }
        
        const data = await response.json();
        currentImpactData = data;
        
        // Show baseline
        document.getElementById('baselineVega').textContent = formatNumber(data.baseline_greeks.vega, 2);
        
        updateNewsImpactList(data.news_impacts);
        
    } catch (error) {
        console.error('Failed to load news impact:', error);
        impactListContainer.innerHTML = `<div class="news-error">Failed to load news impact: ${error.message}</div>`;
        showAlert('error', 'Error', 'Failed to load news impact: ' + error.message);
    }
}

function updateNewsImpactList(impacts) {
    const container = document.getElementById('newsImpactList');
    container.innerHTML = '';
    
    if (!impacts || impacts.length === 0) {
        container.innerHTML = '<div class="news-empty">No news impact data available</div>';
        return;
    }
    
    impacts.forEach(item => {
        const div = document.createElement('div');
        div.className = 'news-item news-impact-item';
        
        const publishedDate = item.published_at ? new Date(item.published_at).toLocaleString() : '';
        const sentimentClass = item.sentiment === 'positive' ? 'positive' : (item.sentiment === 'negative' ? 'negative' : 'neutral');
        const eventTypeBadge = item.event_type || 'unknown';
        
        const impact = item.greeks_impact;
        const hasImpact = impact.vega !== 0 || impact.delta !== 0 || impact.gamma !== 0;
        const impactClass = impact.vega > 0 ? 'positive' : (impact.vega < 0 ? 'negative' : '');
        
        div.innerHTML = `
            <div class="news-header">
                <span class="news-source">${item.source || 'Unknown'}</span>
                <span class="news-time">${publishedDate}</span>
                <span class="event-type-badge ${eventTypeBadge}">${eventTypeBadge}</span>
                <span class="sentiment-badge ${sentimentClass}">${item.sentiment || 'neutral'}</span>
            </div>
            <div class="news-headline">${item.headline || ''}</div>
            <div class="news-impact-details">
                <div class="impact-row">
                    <span class="impact-label">Sentiment Score:</span>
                    <span class="impact-value">${item.sentiment_score || 0}</span>
                </div>
                <div class="impact-row">
                    <span class="impact-label">Importance:</span>
                    <span class="impact-value">${item.importance || 0}</span>
                </div>
                <div class="impact-divider"></div>
                <div class="impact-row greeks-impact">
                    <span class="impact-label">Vega Impact:</span>
                    <span class="impact-value ${impactClass}">${formatNumber(impact.vega, 2)}</span>
                </div>
                <div class="impact-row greeks-impact">
                    <span class="impact-label">Delta Impact:</span>
                    <span class="impact-value">${formatNumber(impact.delta, 2)}</span>
                </div>
                <div class="impact-row greeks-impact">
                    <span class="impact-label">Gamma Impact:</span>
                    <span class="impact-value">${formatNumber(impact.gamma, 4)}</span>
                </div>
                <div class="impact-divider"></div>
                <div class="vol-shocks">
                    <span class="vol-shock-label">Vol Shocks:</span>
                    <span class="vol-shock-item">1W: ${item.vol_shocks['1W_ATM'] || 0}</span>
                    <span class="vol-shock-item">1M: ${item.vol_shocks['1M_ATM'] || 0}</span>
                    <span class="vol-shock-item">3M: ${item.vol_shocks['3M_ATM'] || 0}</span>
                </div>
            </div>
            ${item.url ? `<a href="${item.url}" target="_blank" class="news-link">Read more</a>` : ''}
        `;
        
        container.appendChild(div);
    });
}

function updateNewsList(headlines) {
    const container = document.getElementById('newsList');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (headlines.length === 0) {
        container.innerHTML = '<div class="news-empty">No news headlines available</div>';
        return;
    }
    
    headlines.forEach(item => {
        const div = document.createElement('div');
        div.className = 'news-item';
        
        const publishedDate = item.published_at ? new Date(item.published_at).toLocaleString() : '';
        
        div.innerHTML = `
            <div class="news-header">
                <span class="news-source">${item.source || 'Unknown'}</span>
                <span class="news-time">${publishedDate}</span>
            </div>
            <div class="news-headline">${item.headline || ''}</div>
            ${item.url ? `<a href="${item.url}" target="_blank" class="news-link">Read more</a>` : ''}
        `;
        
        container.appendChild(div);
    });
}

// ==================== Display Updates ====================

function updateGreeksDisplay(greeks) {
    const greeksMap = {
        'delta': document.getElementById('delta'),
        'gamma': document.getElementById('gamma'),
        'vega': document.getElementById('vega'),
        'theta': document.getElementById('theta'),
        'rho': document.getElementById('rho')
    };
    
    for (const [key, element] of Object.entries(greeksMap)) {
        if (greeks[key] !== undefined && greeks[key] !== null) {
            element.textContent = formatNumber(greeks[key], 2);
            element.className = 'greek-value ' + getValueClass(greeks[key]);
        }
    }
}

function updateSpotRatesDisplay(rates) {
    const container = document.getElementById('spotRates');
    container.innerHTML = '';
    
    for (const [pair, rate] of Object.entries(rates)) {
        const formattedPair = pair.replace('USD', '/USD').replace('USD', '/USD');
        const div = document.createElement('div');
        div.className = 'spot-rate-item';
        div.innerHTML = `
            <span class="pair">${pair}</span>
            <span class="rate">${rate.toFixed(4)}</span>
        `;
        container.appendChild(div);
    }
}

function updateVolSurfaceDisplay(data) {
    const container = document.getElementById('volSurface');
    container.innerHTML = '';
    
    const labels = data.tenor_labels || ['1W', '1M', '3M', '6M', '1Y'];
    const vols = data.vols_atm || [];
    
    labels.forEach((label, i) => {
        const div = document.createElement('div');
        div.className = 'vol-item';
        div.innerHTML = `
            <span class="tenor">${label}</span>
            <span class="vol">${((vols[i] || 0) * 100).toFixed(2)}%</span>
        `;
        container.appendChild(div);
    });
}

function updatePositionsList(positions, positionGreeks) {
    const container = document.getElementById('positionsList');
    container.innerHTML = '';
    
    positions.forEach(pos => {
        const greeks = positionGreeks[pos.position_id] || {};
        const div = document.createElement('div');
        div.className = 'position-card';
        div.dataset.positionId = pos.position_id;
        
        const tenorLabel = getTenorLabel(pos.tenor);
        const optionTypeColor = pos.quantity >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
        
        div.innerHTML = `
            <div class="position-header">
                <span class="instrument">${pos.instrument}</span>
                <span class="trade-id">${pos.position_id}</span>
            </div>
            <div class="position-details">
                <div class="detail-item">
                    <span class="detail-label">Strike</span>
                    <span class="detail-value">${pos.strike.toFixed(4)}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Tenor</span>
                    <span class="detail-value">${tenorLabel}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Qty</span>
                    <span class="detail-value" style="color: ${optionTypeColor}">
                        ${pos.quantity >= 0 ? '+' : ''}${formatNumber(pos.quantity, 0)}
                    </span>
                </div>
            </div>
            <div class="position-greeks">
                <span class="mini-greek">D: <span>${formatNumber(greeks.delta || 0, 2)}</span></span>
                <span class="mini-greek">G: <span>${formatNumber(greeks.gamma || 0, 4)}</span></span>
                <span class="mini-greek">V: <span>${formatNumber(greeks.vega || 0, 2)}</span></span>
                <span class="mini-greek">T: <span>${formatNumber(greeks.theta || 0, 2)}</span></span>
            </div>
        `;
        
        // Click to delete
        div.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') {
                // Could show details modal
            }
        });
        
        container.appendChild(div);
    });
}

function updateTimestamp(isoString) {
    const el = document.getElementById('lastUpdate');
    if (isoString) {
        const date = new Date(isoString);
        el.textContent = date.toLocaleTimeString();
    }
}

// ==================== Chart ====================

function initializeChart() {
    const ctx = document.getElementById('ladderChart').getContext('2d');
    
    ladderChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['1W', '1M', '3M', '6M', '1Y'],
            datasets: [{
                label: 'Vega',
                data: [0, 0, 0, 0, 0],
                backgroundColor: 'rgba(59, 130, 246, 0.6)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 35, 50, 0.9)',
                    titleColor: '#f0f4f8',
                    bodyColor: '#94a3b8',
                    borderColor: '#2d3a4f',
                    borderWidth: 1,
                    callbacks: {
                        label: (context) => {
                            return `Vega: ${formatNumber(context.raw, 2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(45, 58, 79, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#94a3b8'
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(45, 58, 79, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        callback: (value) => formatNumber(value, 0)
                    }
                }
            }
        }
    });
}

function updateLadderChart(ladderData, greekType) {
    if (!ladderChart) return;
    
    const data = ladderData.map(entry => entry.greeks[greekType] || 0);
    
    ladderChart.data.datasets[0].data = data;
    ladderChart.data.datasets[0].label = greekType.charAt(0).toUpperCase() + greekType.slice(1);
    ladderChart.options.scales.y.ticks.callback = (value) => formatNumber(value, 2);
    
    // Update colors based on Greek type
    const colors = {
        delta: { bg: 'rgba(59, 130, 246, 0.6)', border: 'rgba(59, 130, 246, 1)' },
        gamma: { bg: 'rgba(168, 85, 247, 0.6)', border: 'rgba(168, 85, 247, 1)' },
        vega: { bg: 'rgba(34, 197, 94, 0.6)', border: 'rgba(34, 197, 94, 1)' },
        theta: { bg: 'rgba(234, 179, 8, 0.6)', border: 'rgba(234, 179, 8, 1)' },
        rho: { bg: 'rgba(239, 68, 68, 0.6)', border: 'rgba(239, 68, 68, 1)' }
    };
    
    const color = colors[greekType] || colors.vega;
    ladderChart.data.datasets[0].backgroundColor = color.bg;
    ladderChart.data.datasets[0].borderColor = color.border;
    
    ladderChart.update();
}

function updateLadderTable(ladderData) {
    const tbody = document.getElementById('ladderTableBody');
    tbody.innerHTML = '';
    
    ladderData.forEach(entry => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="tenor-cell">${entry.tenor}</td>
            <td>${formatNumber(entry.greeks.delta || 0, 2)}</td>
            <td>${formatNumber(entry.greeks.gamma || 0, 4)}</td>
            <td>${formatNumber(entry.greeks.vega || 0, 2)}</td>
            <td>${formatNumber(entry.greeks.theta || 0, 2)}</td>
            <td>${formatNumber(entry.greeks.rho || 0, 2)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ==================== Trade Modal ====================

function openTradeModal() {
    document.getElementById('tradeModal').classList.add('active');
    
    // Pre-fill strike based on current spot
    const instrument = document.getElementById('tradeInstrument').value;
    const spotRates = {
        'EURUSD': 1.0850,
        'USDJPY': 149.50,
        'GBPUSD': 1.2650,
        'USDCHF': 0.8850,
        'AUDUSD': 0.6550,
        'USDCAD': 1.3450,
        'NZDUSD': 0.6050
    };
    
    document.getElementById('tradeStrike').value = spotRates[instrument] || 1.0;
}

function closeTradeModal() {
    document.getElementById('tradeModal').classList.remove('active');
    document.getElementById('tradeForm').reset();
}

async function handleTradeSubmit(event) {
    event.preventDefault();
    
    const tradeData = {
        instrument: document.getElementById('tradeInstrument').value,
        strike: parseFloat(document.getElementById('tradeStrike').value),
        tenor: parseFloat(document.getElementById('tradeTenor').value),
        quantity: parseFloat(document.getElementById('tradeQuantity').value),
        option_type: document.getElementById('tradeOptionType').value,
        portfolio_id: currentPortfolio
    };
    
    try {
        const response = await fetch('/api/trades', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(tradeData)
        });
        
        if (response.ok) {
            closeTradeModal();
            showAlert('success', 'Trade Created', `Trade ${tradeData.instrument} has been added`);
        } else {
            const error = await response.json();
            showAlert('error', 'Error', error.detail || 'Failed to create trade');
        }
    } catch (error) {
        showAlert('error', 'Error', 'Network error. Please try again.');
    }
}

// ==================== Alerts ====================

function showAlert(type, title, message) {
    const container = document.getElementById('alertsContainer');
    
    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    alert.innerHTML = `
        <div class="alert-header">
            <span class="alert-type">${title}</span>
            <span class="alert-time">${new Date().toLocaleTimeString()}</span>
        </div>
        <div class="alert-message">${message}</div>
    `;
    
    container.appendChild(alert);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 300);
    }, 5000);
}

// ==================== Utilities ====================

function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined) return '--';
    
    const absNum = Math.abs(num);
    if (absNum >= 1000000) {
        return (num / 1000000).toFixed(decimals) + 'M';
    } else if (absNum >= 1000) {
        return (num / 1000).toFixed(decimals) + 'K';
    }
    return num.toFixed(decimals);
}

function getValueClass(value) {
    if (value > 0) return 'positive';
    if (value < 0) return 'negative';
    return '';
}

function getTenorLabel(tenor) {
    if (tenor <= 1/52) return '1W';
    if (tenor <= 1/12) return '1M';
    if (tenor <= 3/12) return '3M';
    if (tenor <= 6/12) return '6M';
    return '1Y';
}

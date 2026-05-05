// static/js/greeks_ui.js

// Global state
let ws = null;
let wsFailed = false;
let greeksPollInterval = null;
let currentPortfolio = 'FX-PORTFOLIO-01';
let ladderChart = null;
let impactChart = null;
let spotImpactChart = null;
let gaugeContexts = {};
let currentGreeks = {
    delta: 0, gamma: 0, vega: 0, theta: 0, rho: 0
};
let currentHeadlines = [];
let currentImpactData = null;
let currentSpotRates = {};
let currentSpotChanges = [];
let activeTab = 'news';
let newsPollInterval = null;
let spotRatesPollInterval = null;
let alertsPollInterval = null;
let currentAlerts = { spot_alerts: [], risk_alerts: [] };

// Polling intervals (in milliseconds)
const NEWS_POLL_INTERVAL = 60000; // 60 seconds
const SPOT_RATES_POLL_INTERVAL = 30000; // 30 seconds for live spot rates
const ALERTS_POLL_INTERVAL = 15000; // 15 seconds for alerts (faster polling to catch spot rate alerts)
const IMPACT_POLL_INTERVAL = 120000; // 120 seconds (longer since it's heavier)
const GREEKS_POLL_INTERVAL = 5000; // 5 seconds for Greeks polling (WebSocket fallback)

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
    try {
        startAutoPolling();
    } catch (e) {
        console.error('Auto polling init error:', e);
    }
    try {
        startSpotRatesPolling();
    } catch (e) {
        console.error('Spot rates polling init error:', e);
    }
    try {
        startAlertsPolling();
    } catch (e) {
        console.error('Alerts polling init error:', e);
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
        console.log('WebSocket disconnected. Starting REST polling fallback...');
        wsFailed = true;
        startGreeksPolling();
        // Stop reconnecting attempts after first failure to avoid endless loops
        if (wsFailed) {
            console.log('WebSocket failed, using REST polling instead');
        }
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
        dot.classList.remove('disconnected', 'polling');
        dot.classList.add('connected');
        text.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        // Don't add 'disconnected' class if we're in polling mode
        if (!wsFailed) {
            dot.classList.add('disconnected');
            text.textContent = 'Disconnected';
        }
        // else leave current status (will be updated to 'Polling' by startGreeksPolling)
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
    } else if (data.type === 'spot_alert') {
        // Spot rate alert triggered - show prominent notification
        const alert = data.alert;
        const direction = alert.change_pct > 0 ? '📈 UP' : '📉 DOWN';
        showAlert(
            'warning',
            `Spot Alert: ${alert.pair}`,
            `${direction} ${alert.change_pct.toFixed(3)}% (${alert.baseline_rate.toFixed(5)} → ${alert.current_rate.toFixed(5)})`,
            8000 // Show for 8 seconds
        );
        // Refresh alerts list
        loadAlerts();
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
    
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tab = e.target.dataset.tab;
            switchTab(tab);
        });
    });
    
    // Mobile navigation toggle
    const mobileNavToggle = document.getElementById('mobileNavToggle');
    if (mobileNavToggle) {
        mobileNavToggle.addEventListener('click', () => {
            mobileNavToggle.classList.toggle('active');
            // Toggle panel visibility on mobile
            document.querySelectorAll('.panel').forEach(panel => {
                panel.classList.toggle('expanded');
            });
        });
    }
    
    // Panel header click to expand/collapse on mobile
    document.querySelectorAll('.panel-header').forEach(header => {
        header.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                const panel = header.closest('.panel');
                if (panel) {
                    panel.classList.toggle('expanded');
                }
            }
        });
    });
    
    // Initialize startAutoPolling after DOM is ready
    setTimeout(startAutoPolling, 1000);
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
            loadPortfolioPositions()
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

// ==================== Greeks REST Polling (WebSocket Fallback) ====================

function startGreeksPolling() {
    console.log('Starting Greeks REST polling fallback...');
    
    // Initial fetch
    loadGreeks();
    
    // Set up polling interval
    greeksPollInterval = setInterval(() => {
        loadGreeks();
    }, GREEKS_POLL_INTERVAL);
    
    // Update status to show polling mode
    const statusEl = document.getElementById('wsStatus');
    if (statusEl) {
        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');
        if (dot) {
            dot.classList.remove('disconnected');
            dot.classList.add('polling');
        }
        if (text) text.textContent = 'Polling';
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
        console.log('Loading portfolio positions for:', currentPortfolio);
        const response = await fetch(`/api/portfolios/${currentPortfolio}`);
        console.log('Portfolio response status:', response.status);
        
        if (!response.ok) {
            console.error('Failed to load portfolio, status:', response.status);
            return;
        }
        
        const data = await response.json();
        console.log('Portfolio data received:', data);
        
        if (data.positions && data.positions.length > 0) {
            console.log('Found', data.positions.length, 'positions');
            // Get Greeks for each position
            const greeksResponse = await fetch(`/api/portfolios/${currentPortfolio}/greeks`);
            const greeksData = await greeksResponse.json();
            console.log('Greeks data received:', greeksData);
            
            updatePositionsList(data.positions, greeksData.position_greeks || {});
        } else {
            console.log('No positions found in portfolio data');
            // Show empty state
            const container = document.getElementById('positionsList');
            container.innerHTML = '<div class="positions-empty">No positions in portfolio</div>';
        }
    } catch (error) {
        console.error('Failed to load positions:', error);
    }
}

// ==================== Tab Management ====================

function switchTab(tab) {
    activeTab = tab;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tab}`);
    });
    
    // Show/hide Greek selector based on tab
    const greekSelector = document.getElementById('ladderGreekSelector');
    if (greekSelector) {
        greekSelector.style.display = tab === 'ladder' ? 'flex' : 'none';
    }
    
    // If switching to news tab, ensure data is loaded
    if (tab === 'news') {
        if (!currentImpactData) {
            loadNewsWithImpact();
        } else {
            // Data already loaded, just update the display
            updateNewsImpactList(currentImpactData.news_impacts);
        }
    }
    
    console.log('Switched to tab:', tab);
}

// ==================== Spot Rates Polling ====================

function startSpotRatesPolling() {
    console.log('Starting spot rates polling...');
    
    // Initial fetch
    loadLiveSpotRates();
    loadSpotRateChanges();
    
    // Set up polling interval
    spotRatesPollInterval = setInterval(() => {
        loadLiveSpotRates();
        loadSpotRateChanges();
    }, SPOT_RATES_POLL_INTERVAL);
}

async function loadLiveSpotRates() {
    try {
        const response = await fetch('/api/spot-rates/live');
        if (!response.ok) return;
        
        const data = await response.json();
        currentSpotRates = data.rates || {};
        
        updateSpotRatesDisplay(data.rates, data.source);
        
        // Update timestamp
        if (data.last_update) {
            updateSpotTimestamp(data.last_update);
        }
    } catch (error) {
        console.error('Failed to load live spot rates:', error);
    }
}

async function loadSpotRateChanges() {
    try {
        const response = await fetch('/api/spot-rates/changes');
        if (!response.ok) return;
        
        const data = await response.json();
        currentSpotChanges = data.changes || [];
        
        updateSpotChangesDisplay(data.changes);
    } catch (error) {
        console.error('Failed to load spot rate changes:', error);
    }
}

function updateSpotTimestamp(isoString) {
    const el = document.getElementById('spotLastUpdate');
    if (el && isoString) {
        const date = new Date(isoString);
        el.textContent = date.toLocaleTimeString();
    }
}

// ==================== Alerts Polling ====================

function startAlertsPolling() {
    console.log('Starting alerts polling...');
    
    // Initial fetch
    loadAlerts();
    
    // Set up polling interval
    alertsPollInterval = setInterval(() => {
        loadAlerts();
    }, ALERTS_POLL_INTERVAL);
}

async function loadAlerts() {
    try {
        const response = await fetch('/api/alerts/all?limit=20');
        if (!response.ok) return;
        
        const data = await response.json();
        currentAlerts = {
            spot_alerts: data.spot_alerts || [],
            risk_alerts: data.risk_alerts || []
        };
        
        updateAlertsDisplay(currentAlerts);
        
        // Update alert count badges
        updateAlertBadges(currentAlerts);
    } catch (error) {
        console.error('Failed to load alerts:', error);
    }
}

function updateAlertBadges(alerts) {
    const spotBadge = document.getElementById('spotAlertBadge');
    const riskBadge = document.getElementById('riskAlertBadge');
    
    if (spotBadge) {
        spotBadge.textContent = alerts.spot_alerts.length;
        spotBadge.style.display = alerts.spot_alerts.length > 0 ? 'inline' : 'none';
    }
    
    if (riskBadge) {
        riskBadge.textContent = alerts.risk_alerts.length;
        riskBadge.style.display = alerts.risk_alerts.length > 0 ? 'inline' : 'none';
    }
}

function updateAlertsDisplay(alerts) {
    const container = document.getElementById('alertsList');
    if (!container) return;
    
    container.innerHTML = '';
    
    const allAlerts = [
        ...alerts.spot_alerts.map(a => ({...a, alert_category: 'spot'})),
        ...alerts.risk_alerts.map(a => ({...a, alert_category: 'risk'}))
    ];
    
    if (allAlerts.length === 0) {
        container.innerHTML = '<div class="alerts-empty">No active alerts</div>';
        return;
    }
    
    allAlerts.slice(0, 20).forEach(alert => {
        const div = document.createElement('div');
        const severityClass = alert.severity ? `severity-${alert.severity}` : '';
        div.className = `alert-item ${alert.alert_category} ${severityClass}`.trim();
        
        if (alert.alert_category === 'spot') {
            const direction = alert.change_pct > 0 ? 'up' : 'down';
            const directionIcon = alert.change_pct > 0 ? '📈' : '📉';
            const directionSign = alert.change_pct > 0 ? '+' : '';
            div.innerHTML = `
                <div class="alert-header">
                    <span class="alert-type spot">${directionIcon} Spot ${alert.pair}</span>
                    <span class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</span>
                </div>
                <div class="alert-message">${alert.message}</div>
                <div class="alert-detail">${directionSign}${alert.change_pct.toFixed(3)}%</div>
            `;
        } else {
            const severityIcon = alert.severity === 'high' ? '🚨' : (alert.severity === 'medium' ? '⚠️' : 'ℹ️');
            div.innerHTML = `
                <div class="alert-header">
                    <span class="alert-type ${alert.severity || ''}">${severityIcon} ${alert.title}</span>
                    <span class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</span>
                </div>
                <div class="alert-message">${alert.message}</div>
            `;
        }
        
        container.appendChild(div);
    });
}

// ==================== Combined Impact ====================

async function loadCombinedImpact() {
    try {
        const response = await fetch('/api/impact/combined', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                portfolio_id: currentPortfolio,
                weights: {
                    spot_rate_weight: 0.3,
                    vol_shock_weight: 0.7
                }
            })
        });
        
        if (!response.ok) return;
        
        const data = await response.json();
        
        // Update display with combined impact
        updateCombinedImpactDisplay(data);
        
    } catch (error) {
        console.error('Failed to load combined impact:', error);
    }
}

function updateCombinedImpactDisplay(data) {
    // Update baseline vs current Greeks comparison
    if (data.baseline_greeks && data.current_greeks) {
        const baselineContainer = document.getElementById('baselineGreeks');
        const currentContainer = document.getElementById('currentGreeks');
        
        if (baselineContainer && data.baseline_greeks) {
            baselineContainer.innerHTML = `
                <div class="greek-compare-item">
                    <span class="label">Delta:</span>
                    <span class="value">${formatNumber(data.baseline_greeks.delta, 2)}</span>
                </div>
                <div class="greek-compare-item">
                    <span class="label">Vega:</span>
                    <span class="value">${formatNumber(data.baseline_greeks.vega, 2)}</span>
                </div>
            `;
        }
        
        if (currentContainer && data.current_greeks) {
            const deltaDiff = data.greeks_delta?.delta || 0;
            const vegaDiff = data.greeks_delta?.vega || 0;
            
            currentContainer.innerHTML = `
                <div class="greek-compare-item">
                    <span class="label">Delta:</span>
                    <span class="value ${deltaDiff > 0 ? 'positive' : 'negative'}">${formatNumber(data.current_greeks.delta, 2)} (${deltaDiff > 0 ? '+' : ''}${formatNumber(deltaDiff, 2)})</span>
                </div>
                <div class="greek-compare-item">
                    <span class="label">Vega:</span>
                    <span class="value ${vegaDiff > 0 ? 'positive' : 'negative'}">${formatNumber(data.current_greeks.vega, 2)} (${vegaDiff > 0 ? '+' : ''}${formatNumber(vegaDiff, 2)})</span>
                </div>
            `;
        }
    }
    
    // Update spot impacts
    if (data.spot_impacts && data.spot_impacts.length > 0) {
        updateSpotImpactsDisplay(data.spot_impacts);
    }
}

function updateSpotImpactsDisplay(spotImpacts) {
    const container = document.getElementById('spotImpactsList');
    if (!container) return;
    
    container.innerHTML = '';
    
    spotImpacts.forEach(impact => {
        const div = document.createElement('div');
        div.className = 'spot-impact-item';
        
        div.innerHTML = `
            <div class="spot-impact-pair">${impact.pair}</div>
            <div class="spot-impact-change ${impact.rate_change_pct > 0 ? 'positive' : 'negative'}">
                ${impact.rate_change_pct > 0 ? '+' : ''}${impact.rate_change_pct.toFixed(3)}%
            </div>
            <div class="spot-impact-delta">
                Est. Δ: ${formatNumber(impact.estimated_delta_impact, 0)}
            </div>
        `;
        
        container.appendChild(div);
    });
}

// ==================== Display Updates ====================

function updateSpotRatesDisplay(rates, source) {
    const container = document.getElementById('spotRates');
    if (!container) return;
    
    container.innerHTML = '';
    
    // Add source indicator
    const sourceLabel = document.createElement('span');
    sourceLabel.className = 'spot-source';
    sourceLabel.textContent = source === 'live' ? '● LIVE' : '○ MOCK';
    sourceLabel.style.cssText = source === 'live' ? 'color: #22c55e; font-size: 10px;' : 'color: #94a3b8; font-size: 10px;';
    
    for (const [pair, rate] of Object.entries(rates)) {
        const div = document.createElement('div');
        div.className = 'spot-rate-item';
        
        // Find change for this pair
        const change = currentSpotChanges.find(c => c.pair === pair);
        const changeClass = change ? (change.direction === 'up' ? 'positive' : change.direction === 'down' ? 'negative' : '') : '';
        const changeStr = change ? `${change.direction === 'up' ? '↑' : change.direction === 'down' ? '↓' : '→'} ${Math.abs(change.change_pct).toFixed(2)}%` : '';
        
        div.innerHTML = `
            <span class="pair">${pair}</span>
            <span class="rate">${rate.toFixed(5)}</span>
            <span class="change ${changeClass}">${changeStr}</span>
        `;
        container.appendChild(div);
    }
}

function updateSpotChangesDisplay(changes) {
    const container = document.getElementById('spotChanges');
    if (!container) return;
    
    container.innerHTML = '';
    
    changes.forEach(change => {
        const div = document.createElement('div');
        div.className = 'spot-change-item';
        
        const direction = change.direction === 'up' ? '↑' : change.direction === 'down' ? '↓' : '→';
        const colorClass = change.direction === 'up' ? 'positive' : change.direction === 'down' ? 'negative' : '';
        
        div.innerHTML = `
            <span class="pair">${change.pair}</span>
            <span class="change ${colorClass}">${direction} ${Math.abs(change.change_pct).toFixed(3)}%</span>
        `;
        container.appendChild(div);
    });
}

async function loadNewsWithImpact() {
    try {
        console.log('Fetching news with impact from /api/news-with-impact...');
        const response = await fetch('/api/news-with-impact?max_results=10');
        console.log('News with impact response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('News with impact API error:', response.status, errorText);
            return;
        }
        
        const data = await response.json();
        console.log('News with impact data received:', data.count, 'headlines');
        
        currentImpactData = data;
        currentHeadlines = data.news_impacts || [];
        
        // Store trace ID for the batch
        const batchTraceId = data.trace_id;
        
        // Show baseline
        document.getElementById('baselineVega').textContent = formatNumber(data.baseline_greeks.vega, 2);
        
        // Initialize gauges and chart
        initializeGauges();
        initializeImpactChart(data.news_impacts);
        
        updateNewsImpactList(data.news_impacts);
        
    } catch (error) {
        console.error('Failed to load news with impact:', error);
    }
}

async function loadNews() {
    // Deprecated: Use loadNewsWithImpact() instead - it fetches news AND impact in single call
    // Kept for backward compatibility but does nothing now
    console.log('loadNews is deprecated - use loadNewsWithImpact');
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

async function loadNewsImpact() {
    // Deprecated: Use loadNewsWithImpact() instead - it fetches news AND impact in single call
    console.log('loadNewsImpact is deprecated - use loadNewsWithImpact');
    await loadNewsWithImpact();
}

function initializeGauges() {
    const gaugeDefs = [
        { id: 'vegaGauge', label: 'Vega', color: '#22c55e' },
        { id: 'deltaGauge', label: 'Delta', color: '#3b82f6' },
        { id: 'gammaGauge', label: 'Gamma', color: '#a855f7' }
    ];
    
    gaugeDefs.forEach(def => {
        const canvas = document.getElementById(def.id);
        if (canvas) {
            gaugeContexts[def.id] = {
                canvas: canvas,
                ctx: canvas.getContext('2d'),
                color: def.color,
                value: 0,
                maxValue: 100000
            };
            drawGauge(def.id, 0);
        }
    });
}

function drawGauge(gaugeId, normalizedValue) {
    const gauge = gaugeContexts[gaugeId];
    if (!gauge) return;
    
    const ctx = gauge.ctx;
    const canvas = gauge.canvas;
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 35;
    const lineWidth = 8;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw background arc (semicircle from left to right)
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, Math.PI, 0, false);
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#1a2332';
    ctx.stroke();
    
    // Draw value arc
    const valueAngle = Math.PI + (Math.PI * Math.min(Math.max(normalizedValue, 0), 1));
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, Math.PI, valueAngle, false);
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.strokeStyle = gauge.color;
    ctx.stroke();
}

function updateGauges(impacts) {
    // Calculate total impacts
    let totalVega = 0, totalDelta = 0, totalGamma = 0;
    
    impacts.forEach(item => {
        const impact = item.greeks_impact || {};
        totalVega += Math.abs(impact.vega || 0);
        totalDelta += Math.abs(impact.delta || 0);
        totalGamma += Math.abs(impact.gamma || 0);
    });
    
    // Update gauge values and draw
    gaugeContexts['vegaGauge'].value = totalVega;
    gaugeContexts['vegaGauge'].maxValue = Math.max(totalVega * 1.5, 10000);
    drawGauge('vegaGauge', Math.min(totalVega / gaugeContexts['vegaGauge'].maxValue, 1));
    
    gaugeContexts['deltaGauge'].value = totalDelta;
    gaugeContexts['deltaGauge'].maxValue = Math.max(totalDelta * 1.5, 10000);
    drawGauge('deltaGauge', Math.min(totalDelta / gaugeContexts['deltaGauge'].maxValue, 1));
    
    gaugeContexts['gammaGauge'].value = totalGamma;
    gaugeContexts['gammaGauge'].maxValue = Math.max(totalGamma * 1.5, 10000);
    drawGauge('gammaGauge', Math.min(totalGamma / gaugeContexts['gammaGauge'].maxValue, 1));
    
    // Update gauge value displays
    const vegaValueEl = document.getElementById('vegaGaugeValue');
    const deltaValueEl = document.getElementById('deltaGaugeValue');
    const gammaValueEl = document.getElementById('gammaGaugeValue');
    
    if (vegaValueEl) vegaValueEl.textContent = formatNumber(totalVega, 0);
    if (deltaValueEl) deltaValueEl.textContent = formatNumber(totalDelta, 0);
    if (gammaValueEl) gammaValueEl.textContent = formatNumber(totalGamma, 0);
}

function initializeImpactChart(impacts) {
    const ctx = document.getElementById('impactChart').getContext('2d');
    
    if (impactChart) {
        impactChart.destroy();
    }
    
    const labels = impacts.map((item, i) => `N${i + 1}`);
    const vegaData = impacts.map(item => item.greeks_impact?.vega || 0);
    const deltaData = impacts.map(item => item.greeks_impact?.delta || 0);
    
    impactChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Vega',
                    data: vegaData,
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Delta',
                    data: deltaData,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        boxWidth: 10,
                        font: { size: 9 },
                        color: '#94a3b8'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 35, 50, 0.9)',
                    titleColor: '#f0f4f8',
                    bodyColor: '#94a3b8',
                    borderColor: '#2d3a4f',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    display: true,
                    grid: { color: 'rgba(45, 58, 79, 0.5)' },
                    ticks: { 
                        color: '#94a3b8',
                        font: { size: 9 },
                        callback: (value) => formatNumber(value, 0)
                    }
                }
            }
        }
    });
}

function updateNewsImpactList(impacts) {
    const container = document.getElementById('newsImpactList');
    container.innerHTML = '';
    
    if (!impacts || impacts.length === 0) {
        container.innerHTML = '<div class="news-empty">No news impact data available</div>';
        // Update summary metrics
        const activeCountEl = document.getElementById('activeNewsCount');
        const totalImpactEl = document.getElementById('totalImpact');
        if (activeCountEl) activeCountEl.textContent = '0';
        if (totalImpactEl) totalImpactEl.textContent = '--';
        return;
    }
    
    // Update summary metrics
    const activeCountEl = document.getElementById('activeNewsCount');
    const totalImpactEl = document.getElementById('totalImpact');
    if (activeCountEl) activeCountEl.textContent = impacts.length;
    
    // Calculate total impact (sum of absolute vega impacts)
    let totalImpact = 0;
    impacts.forEach(item => {
        totalImpact += Math.abs(item.greeks_impact?.vega || 0);
    });
    if (totalImpactEl) {
        totalImpactEl.textContent = formatNumber(totalImpact, 0);
        totalImpactEl.className = 'metric-value ' + (totalImpact > 0 ? 'positive' : '');
    }
    
    // Show trace ID if available
    const traceIdEl = document.getElementById('currentTraceId');
    if (traceIdEl && currentImpactData && currentImpactData.trace_id) {
        traceIdEl.textContent = currentImpactData.trace_id;
        traceIdEl.title = 'Click to view full audit trail';
        traceIdEl.onclick = () => {
            window.open(`/api/audit/trace/${currentImpactData.trace_id}`, '_blank');
        };
        traceIdEl.style.cursor = 'pointer';
        traceIdEl.style.display = 'inline';
    }
    
    // Update gauges with total impact
    updateGauges(impacts);
    
    // Update impact chart
    if (impactChart) {
        const vegaData = impacts.map(item => item.greeks_impact?.vega || 0);
        const deltaData = impacts.map(item => item.greeks_impact?.delta || 0);
        impactChart.data.datasets[0].data = vegaData;
        impactChart.data.datasets[1].data = deltaData;
        impactChart.update();
    }
    
    impacts.forEach(item => {
        const div = document.createElement('div');
        div.className = 'news-impact-item';
        
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
            ${item.url ? `<a href="${item.url}" target="_blank" class="news-link">Read more →</a>` : ''}
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
    
    console.log('updatePositionsList called with', positions?.length, 'positions and greeks:', Object.keys(positionGreeks || {}));
    
    if (!positions || positions.length === 0) {
        container.innerHTML = '<div class="positions-empty">No positions in portfolio</div>';
        return;
    }
    
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
                backgroundColor: 'rgba(34, 197, 94, 0.6)',
                borderColor: 'rgba(34, 197, 94, 1)',
                borderWidth: 1,
                borderRadius: 4
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
                    backgroundColor: 'rgba(26, 35, 50, 0.95)',
                    titleColor: '#f0f4f8',
                    bodyColor: '#94a3b8',
                    borderColor: '#2d3a4f',
                    borderWidth: 1,
                    cornerRadius: 6,
                    padding: 10,
                    callbacks: {
                        label: (context) => {
                            const greekType = document.getElementById('ladderGreekSelect')?.value || 'vega';
                            return `${greekType.charAt(0).toUpperCase() + greekType.slice(1)}: ${formatNumber(context.raw, 2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(45, 58, 79, 0.3)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 11 }
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(45, 58, 79, 0.3)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 11 },
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
    
    // Update chart legend text
    const legendText = document.getElementById('chartLegendText');
    if (legendText) {
        legendText.textContent = greekType.charAt(0).toUpperCase() + greekType.slice(1);
    }
    
    // Update legend dot color
    const legendDot = document.querySelector('.legend-dot');
    if (legendDot) {
        const colorMap = {
            delta: 'rgba(59, 130, 246, 0.6)',
            gamma: 'rgba(168, 85, 247, 0.6)',
            vega: 'rgba(34, 197, 94, 0.6)',
            theta: 'rgba(234, 179, 8, 0.6)',
            rho: 'rgba(239, 68, 68, 0.6)'
        };
        legendDot.style.backgroundColor = colorMap[greekType] || colorMap.vega;
    }
    
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
        
        const deltaVal = entry.greeks.delta || 0;
        const gammaVal = entry.greeks.gamma || 0;
        const vegaVal = entry.greeks.vega || 0;
        const thetaVal = entry.greeks.theta || 0;
        const rhoVal = entry.greeks.rho || 0;
        
        const getValueClass = (val) => val > 0 ? 'positive-value' : (val < 0 ? 'negative-value' : '');
        
        tr.innerHTML = `
            <td class="tenor-cell">${entry.tenor}</td>
            <td class="${getValueClass(deltaVal)}">${formatNumber(deltaVal, 2)}</td>
            <td class="${getValueClass(gammaVal)}">${formatNumber(gammaVal, 4)}</td>
            <td class="${getValueClass(vegaVal)}">${formatNumber(vegaVal, 2)}</td>
            <td class="${getValueClass(thetaVal)}">${formatNumber(thetaVal, 2)}</td>
            <td class="${getValueClass(rhoVal)}">${formatNumber(rhoVal, 2)}</td>
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

function showAlert(type, title, message, duration = 5000) {
    const container = document.getElementById('alertsContainer');
    
    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    
    // Icon based on alert type
    const icons = {
        info: 'ℹ️',
        warning: '⚠️',
        error: '🚨',
        success: '✅'
    };
    
    alert.innerHTML = `
        <div class="alert-header">
            <span class="alert-type ${type}">${icons[type] || ''} ${title}</span>
            <span class="alert-time">${new Date().toLocaleTimeString()}</span>
        </div>
        <div class="alert-message">${message}</div>
    `;
    
    container.appendChild(alert);
    
    // Auto-remove after specified duration (default 5 seconds)
    setTimeout(() => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 300);
    }, duration);
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

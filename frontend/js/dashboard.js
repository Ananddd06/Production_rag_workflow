// dashboard.js
// Handles fetching and rendering dashboard metrics

const API_BASE = 'http://localhost:8000/api';

async function fetchDashboardData() {
  try {
    const response = await fetch(`${API_BASE}/metrics/dashboard`);
    if (!response.ok) throw new Error('Failed to fetch dashboard data');
    const data = await response.json();
    try {
      renderDashboard(data);
      updateCharts(data);
      updateHealthStatus(true);
    } catch (renderError) {
      console.error('Render error:', renderError);
      document.getElementById('health-text').textContent = 'Render Error: ' + renderError.message;
      updateHealthStatus(false);
    }
  } catch (error) {
    console.error('Dashboard fetch error:', error);
    document.getElementById('health-text').textContent = 'Fetch Error: ' + error.message;
    updateHealthStatus(false);
  }
}

function renderDashboard(data) {
  // Quality Metrics
  if (data.quality_summary) {
    updateCircularProgress('progress-feedback', 'val-feedback', data.quality_summary.feedback_ratio, `${Math.round(data.quality_summary.feedback_ratio * 100)}%`);
    updateCircularProgress('progress-citation', 'val-citation', data.quality_summary.citation_accuracy, `${Math.round(data.quality_summary.citation_accuracy * 100)}%`);
    updateCircularProgress('progress-hallucination', 'val-hallucination', data.quality_summary.hallucination_rate, `${Math.round(data.quality_summary.hallucination_rate * 100)}%`, true);
  }

  // Cache Stats
  if (data.cache_stats) {
    const hitRate = data.cache_stats.hit_rate * 100;
    document.getElementById('cache-hit-pct').textContent = `${hitRate.toFixed(1)}%`;
    
    const total = data.cache_stats.hits + data.cache_stats.misses;
    const hitPct = total > 0 ? (data.cache_stats.hits / total) * 100 : 0;
    const missPct = total > 0 ? (data.cache_stats.misses / total) * 100 : 0;
    
    document.getElementById('cache-hits-bar').style.width = `${hitPct}%`;
    document.getElementById('cache-misses-bar').style.width = `${missPct}%`;
    
    document.getElementById('cache-hits-val').textContent = data.cache_stats.hits;
    document.getElementById('cache-misses-val').textContent = data.cache_stats.misses;
    document.getElementById('cache-size').textContent = `${data.cache_stats.size} / ${data.cache_stats.max_size}`;
  }

  // Document Stats
  if (data.document_stats) {
    const docCount = data.document_stats.total_documents;
    const docCountEl = document.getElementById('doc-count');
    if (docCountEl) docCountEl.textContent = docCount;
    
    const statDocsEl = document.getElementById('stat-documents');
    if (statDocsEl) statDocsEl.textContent = docCount;
    
    const footerDocEl = document.getElementById('footer-doc-count');
    if (footerDocEl) footerDocEl.textContent = docCount;
  }
  
  if (data.query_count !== undefined) {
    const footerQueryEl = document.getElementById('footer-query-count');
    if (footerQueryEl) footerQueryEl.textContent = data.query_count;
  }

  // Cost
  if (data.cost_history) {
    const totalCost = data.cost_history.reduce((sum, item) => sum + (item.cost_breakdown.total_cost || 0), 0);
    const queries = data.cost_history.length || 1;
    const costPer1k = (totalCost / queries) * 1000;
    
    const costTotalEl = document.getElementById('cost-total');
    if (costTotalEl) costTotalEl.textContent = `$${totalCost.toFixed(4)}`;
    
    const costPer1kEl = document.getElementById('cost-per-1k');
    if (costPer1kEl) costPer1kEl.textContent = `$${costPer1k.toFixed(2)}`;
  }

  // Events & Alerts
  if (data.recent_alerts) {
    renderEvents(data.recent_alerts);
  }
  
  // Uploaded Documents
  if (data.recent_events) {
    const listEl = document.getElementById('uploaded-documents-list');
    if (listEl) {
      const ingestEvents = data.recent_events.filter(e => e.event_type === 'ingest');
      if (ingestEvents.length === 0) {
        listEl.innerHTML = '<li style="color: var(--text-secondary); font-size: 0.9rem;">No documents recently uploaded</li>';
      } else {
        listEl.innerHTML = ingestEvents.map(e => {
          const date = new Date(e.timestamp);
          const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const source = e.metadata ? e.metadata.source : 'Unknown';
          const chunks = e.metadata ? e.metadata.chunks : 0;
          return `<li style="font-size: 0.9rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem;">
            <span style="color: var(--accent-blue);">📄</span>
            <span style="flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${source}">${source}</span>
            <span style="color: var(--text-secondary); font-size: 0.8rem; background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px;">${chunks} chunks</span>
            <span style="color: var(--text-secondary); font-size: 0.8rem;">${timeStr}</span>
          </li>`;
        }).join('');
      }
    }
  }
}

function updateCircularProgress(elementId, valueId, ratio, displayValue, inverseColor = false) {
  const container = document.getElementById(elementId);
  const valEl = document.getElementById(valueId);
  if (!container || !valEl) return;
  
  valEl.textContent = displayValue;
  
  const circle = container.querySelector('.progress-fill');
  if (circle) {
    // 2 * pi * r = 2 * 3.14159 * 38 = 238.76
    const circumference = 238.76;
    const offset = circumference - (ratio * circumference);
    circle.style.strokeDashoffset = offset;
    
    // Change color based on value
    if (inverseColor) {
      if (ratio > 0.2) circle.style.stroke = 'var(--accent-red)';
      else if (ratio > 0.1) circle.style.stroke = 'var(--accent-gold)';
      else circle.style.stroke = 'var(--accent-green)';
    } else {
      if (ratio < 0.5) circle.style.stroke = 'var(--accent-red)';
      else if (ratio < 0.8) circle.style.stroke = 'var(--accent-gold)';
      else circle.style.stroke = 'var(--accent-green)';
    }
  }
}

function renderEvents(alerts) {
  const container = document.getElementById('events-list');
  if (!container) return;
  
  if (!alerts || alerts.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <div class="empty-text">No alerts yet</div>
      </div>
    `;
    return;
  }
  
  container.innerHTML = alerts.map(alert => {
    const date = new Date(alert.timestamp);
    const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    return `
      <div class="event-item">
        <div class="event-severity ${alert.severity}"></div>
        <div class="event-content">
          <div class="event-message">${alert.message}</div>
          <div class="event-time">${timeStr} - ${alert.type}</div>
        </div>
      </div>
    `;
  }).join('');
}

function updateHealthStatus(isHealthy) {
  const indicator = document.getElementById('health-indicator');
  const text = document.getElementById('health-text');
  
  if (isHealthy) {
    indicator.classList.remove('unhealthy');
    text.textContent = 'Healthy';
  } else {
    indicator.classList.add('unhealthy');
    if (!text.textContent.includes('Error')) {
      text.textContent = 'Degraded';
    }
  }
}

function renderLatencyBreakdown(latencyObj) {
  if (!latencyObj) return;
  
  const total = latencyObj.total_ms || 1;
  document.getElementById('latency-total-value').textContent = `${Math.round(latencyObj.total_ms || 0)}ms`;
  
  const stages = ['preprocessing', 'retrieval', 'reranking', 'assembly', 'generation'];
  
  stages.forEach(stage => {
    const val = latencyObj[`${stage}_ms`] || 0;
    const pct = Math.min(100, Math.max(0, (val / total) * 100));
    
    // Update dashboard bars
    const dashBar = document.getElementById(`bar-${stage}`);
    const dashVal = document.getElementById(`val-${stage}`);
    if (dashBar) dashBar.style.width = `${pct}%`;
    if (dashVal) dashVal.textContent = `${Math.round(val)}ms`;
  });
  
  // Update inline response bar
  const inlineContainer = document.getElementById('latency-bar-inline');
  if (inlineContainer) {
    inlineContainer.innerHTML = stages.map(stage => {
      const val = latencyObj[`${stage}_ms`] || 0;
      const pct = (val / total) * 100;
      if (pct < 1) return '';
      return `<div class="bar-segment seg-${stage}" style="width: ${pct}%" title="${stage}: ${Math.round(val)}ms"></div>`;
    }).join('');
  }
}

// query.js
// Handles RAG querying, feedback, and document ingestion

let currentQueryId = null;

async function submitQuery() {
  const inputEl = document.getElementById('query-input');
  const query = inputEl.value.trim();
  if (!query) return;

  const btnSubmit = document.getElementById('btn-submit');
  const loadingContainer = document.getElementById('loading-container');
  const responseCard = document.getElementById('response-card');
  const responseEmpty = document.getElementById('response-empty');

  // Set loading state
  inputEl.disabled = true;
  btnSubmit.disabled = true;
  responseCard.classList.remove('active');
  responseEmpty.style.display = 'none';
  loadingContainer.classList.add('active');

  // Start Pipeline Animation
  const pipelineState = { active: true };
  simulatePipeline(pipelineState);

  try {
    const response = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, top_k: 5 })
    });

    if (!response.ok) throw new Error('Query failed');
    const data = await response.json();
    
    renderResponse(data);
    
    // Refresh dashboard stats after query
    fetchDashboardData();
    
  } catch (error) {
    console.error('Query error:', error);
    showToast('Failed to execute query', 'error');
    responseEmpty.style.display = 'flex';
  } finally {
    pipelineState.active = false;
    finishPipeline();
    // Reset state
    inputEl.disabled = false;
    btnSubmit.disabled = false;
    loadingContainer.classList.remove('active');
    inputEl.focus();
  }
}

function renderResponse(data) {
  const responseCard = document.getElementById('response-card');
  const answerEl = document.getElementById('response-answer');
  const citationsContainer = document.getElementById('citations-container');
  const costEl = document.getElementById('response-cost');
  const latencyEl = document.getElementById('response-latency');
  
  currentQueryId = data.query_id;
  
  // Format Answer (convert [1] to HTML spans)
  let formattedAnswer = data.answer;
  if (data.citations_used && data.citations_used.length > 0) {
    data.citations_used.forEach(num => {
      const regex = new RegExp(`\\[${num}\\]`, 'g');
      formattedAnswer = formattedAnswer.replace(regex, `<span class="citation-ref" title="Source ${num}">${num}</span>`);
    });
  }
  answerEl.innerHTML = formattedAnswer;
  
  // Render Citations
  if (data.citations && data.citations.length > 0) {
    citationsContainer.innerHTML = data.citations.map(c => `
      <div class="citation-item">
        <div class="citation-number">${c.id}</div>
        <div>
          <div class="citation-source">${c.title || c.source}</div>
          <div>${c.text_preview}</div>
        </div>
      </div>
    `).join('');
    document.getElementById('citations-list').style.display = 'block';
  } else {
    document.getElementById('citations-list').style.display = 'none';
  }
  
  // Meta Info
  if (data.cost && data.cost.total_cost) {
    costEl.textContent = `Cost: $${data.cost.total_cost.toFixed(5)}`;
  } else {
    costEl.textContent = 'Cost: $0.00000';
  }
  
  if (data.latency && data.latency.total_ms) {
    latencyEl.textContent = `${Math.round(data.latency.total_ms)}ms`;
  }
  
  // Reset feedback buttons
  document.getElementById('btn-thumbs-up').classList.remove('active');
  document.getElementById('btn-thumbs-down').classList.remove('active');
  
  // Render Latency Breakdown (using dashboard.js function)
  if (data.latency) {
    renderLatencyBreakdown(data.latency);
  }
  
  // Show Card
  responseCard.classList.add('active');
  if (data.cached) {
    showToast('Response loaded from cache', 'info');
  }
}

async function submitFeedback(type) {
  if (!currentQueryId) return;
  
  try {
    const response = await fetch(`${API_BASE}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query_id: currentQueryId, feedback: type })
    });
    
    if (response.ok) {
      document.getElementById('btn-thumbs-up').classList.remove('active');
      document.getElementById('btn-thumbs-down').classList.remove('active');
      document.getElementById(`btn-thumbs-${type}`).classList.add('active');
      showToast('Feedback recorded. Thank you!', 'success');
      fetchDashboardData();
    }
  } catch (error) {
    console.error('Feedback error:', error);
    showToast('Failed to record feedback', 'error');
  }
}

async function handleFileUpload(files) {
  if (!files || files.length === 0) return;
  
  showToast(`Uploading ${files.length} file(s)...`, 'info');
  
  for (let file of files) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        showToast(`Successfully ingested ${file.name}`, 'success');
      } else {
        showToast(`Failed to ingest ${file.name}`, 'error');
      }
    } catch (error) {
      console.error('Upload error:', error);
      showToast(`Error uploading ${file.name}`, 'error');
    }
  }
  
  fetchDashboardData();
}

async function handleTextIngest() {
  const textEl = document.getElementById('paste-text');
  const text = textEl.value.trim();
  if (!text) return;
  
  const btn = document.getElementById('btn-add-doc');
  btn.disabled = true;
  btn.textContent = 'Adding...';
  
  const formData = new FormData();
  formData.append('text', text);
  formData.append('metadata', JSON.stringify({ source: 'manual_paste' }));
  
  try {
    const response = await fetch(`${API_BASE}/ingest`, {
      method: 'POST',
      body: formData
    });
    
    if (response.ok) {
      showToast('Document added successfully', 'success');
      textEl.value = '';
      fetchDashboardData();
    } else {
      showToast('Failed to add document', 'error');
    }
  } catch (error) {
    console.error('Ingest error:', error);
    showToast('Error adding document', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Add Document';
  }
}

// Toast Notification System
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'error') icon = '❌';
  if (type === 'warning') icon = '⚠️';
  
  toast.innerHTML = `
    <div class="toast-icon">${icon}</div>
    <div class="toast-message">${message}</div>
    <button class="toast-close">&times;</button>
  `;
  
  container.appendChild(toast);
  
  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => {
    toast.classList.add('toast-fade-out');
    setTimeout(() => toast.remove(), 300);
  });
  
  setTimeout(() => {
    if (toast.parentElement) {
      toast.classList.add('toast-fade-out');
      setTimeout(() => toast.remove(), 300);
    }
  }, 4000);
}

// Pipeline Animation
async function simulatePipeline(state) {
  resetPipeline();
  
  const steps = ['preprocess', 'retrieve', 'rerank', 'assemble', 'generate'];
  const timings = [100, 300, 1100, 1200, 1300]; // Timestamps to switch
  
  const delay = ms => new Promise(res => setTimeout(res, ms));

  let currentStepIndex = 0;

  for (let i = 0; i < timings.length; i++) {
    if (!state.active) break;
    
    // Deactivate previous
    if (i > 0) {
      document.getElementById(`step-${steps[i-1]}`).classList.remove('active');
      document.getElementById(`step-${steps[i-1]}`).classList.add('completed');
      if (i <= 4) document.getElementById(`conn-${i}`).classList.add('active');
    }
    
    // Activate current
    document.getElementById(`step-${steps[i]}`).classList.add('active');
    
    // Wait until next step
    const waitTime = i === timings.length - 1 ? 9999999 : timings[i+1] - timings[i];
    
    let waited = 0;
    while(waited < waitTime && state.active) {
      await delay(50);
      waited += 50;
    }
  }
}

function resetPipeline() {
  const steps = ['preprocess', 'retrieve', 'rerank', 'assemble', 'generate'];
  steps.forEach(s => {
    const el = document.getElementById(`step-${s}`);
    if (el) {
      el.classList.remove('active', 'completed');
    }
  });
  for (let i = 1; i <= 4; i++) {
    const conn = document.getElementById(`conn-${i}`);
    if (conn) conn.classList.remove('active');
  }
}

function finishPipeline() {
  const steps = ['preprocess', 'retrieve', 'rerank', 'assemble', 'generate'];
  steps.forEach(s => {
    const el = document.getElementById(`step-${s}`);
    if (el) {
      el.classList.remove('active');
      el.classList.add('completed');
    }
  });
  for (let i = 1; i <= 4; i++) {
    const conn = document.getElementById(`conn-${i}`);
    if (conn) conn.classList.add('active');
  }
}

// app.js
// Main initialization and event binding

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Chart.js
  initCharts();
  
  // Initial data fetch
  fetchDashboardData();
  
  // Setup clock
  setInterval(() => {
    const now = new Date();
    document.getElementById('header-time').textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }, 1000);
  
  // Poll dashboard every 10 seconds
  setInterval(fetchDashboardData, 10000);
  
  // --- Event Listeners ---
  
  // Query Submission
  document.getElementById('btn-submit').addEventListener('click', submitQuery);
  document.getElementById('query-input').addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      submitQuery();
    }
  });
  
  // Feedback
  document.getElementById('btn-thumbs-up').addEventListener('click', () => submitFeedback('up'));
  document.getElementById('btn-thumbs-down').addEventListener('click', () => submitFeedback('down'));
  
  // File Upload (Drag & Drop)
  const uploadZone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  
  uploadZone.addEventListener('click', () => fileInput.click());
  
  uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
  });
  
  uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
  });
  
  uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files);
    }
  });
  
  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileUpload(e.target.files);
    }
  });
  
  // Text Ingest
  document.getElementById('btn-add-doc').addEventListener('click', handleTextIngest);
});

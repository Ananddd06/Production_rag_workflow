// charts.js
// Handles initialization and updating of Chart.js charts

const chartState = {
  latencyChart: null,
  costChart: null
};

function initCharts() {
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.font.family = "'Inter', sans-serif";

  // Latency Trend Chart
  const latencyCtx = document.getElementById('latency-chart').getContext('2d');
  chartState.latencyChart = new Chart(latencyCtx, {
    type: 'line',
    data: {
      labels: [], // Time labels
      datasets: [
        {
          label: 'Total Latency (ms)',
          data: [],
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245, 158, 11, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: 'rgba(17, 24, 39, 0.9)',
          titleColor: '#f1f5f9',
          bodyColor: '#f1f5f9',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          padding: 10
        }
      },
      scales: {
        x: { grid: { color: 'rgba(255, 255, 255, 0.05)' } },
        y: { 
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      },
      interaction: {
        mode: 'nearest',
        axis: 'x',
        intersect: false
      }
    }
  });

  // Cost Doughnut Chart
  const costCtx = document.getElementById('cost-chart').getContext('2d');
  chartState.costChart = new Chart(costCtx, {
    type: 'doughnut',
    data: {
      labels: ['Embedding', 'Generation', 'Vector DB'],
      datasets: [{
        data: [0, 0, 0],
        backgroundColor: [
          '#10b981', // green
          '#ef4444', // red
          '#3b82f6'  // blue
        ],
        borderWidth: 0,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '75%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(17, 24, 39, 0.9)',
          callbacks: {
            label: function(context) {
              let label = context.label || '';
              if (label) { label += ': '; }
              if (context.parsed !== null) {
                label += new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 4 }).format(context.parsed);
              }
              return label;
            }
          }
        }
      }
    }
  });
}

function updateCharts(dashboardData) {
  if (!chartState.latencyChart || !chartState.costChart) return;

  // Update Cost Chart
  if (dashboardData.cost_history) {
    const totalEmbedding = dashboardData.cost_history.reduce((sum, item) => sum + (item.cost_breakdown.embedding_cost || 0), 0);
    const totalGen = dashboardData.cost_history.reduce((sum, item) => sum + (item.cost_breakdown.generation_cost || 0), 0);
    const totalDb = dashboardData.cost_history.reduce((sum, item) => sum + (item.cost_breakdown.vector_db_cost || 0), 0);
    
    chartState.costChart.data.datasets[0].data = [totalEmbedding, totalGen, totalDb];
    chartState.costChart.update();
  }

  // Update Latency Chart
  if (dashboardData.latency_history && dashboardData.latency_history.length > 0) {
    const history = dashboardData.latency_history;
    const labels = history.map(item => {
      const date = new Date(item.timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    });
    const data = history.map(item => item.latency_breakdown.total_ms || 0);

    chartState.latencyChart.data.labels = labels;
    chartState.latencyChart.data.datasets[0].data = data;
    chartState.latencyChart.update();
  }
}

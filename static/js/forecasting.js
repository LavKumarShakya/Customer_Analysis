/**
 * Demand Forecasting Module — Frontend Logic
 * Handles API integration, Plotly chart rendering, and UI updates.
 */

document.addEventListener('DOMContentLoaded', function() {
    const forecastForm = document.getElementById('forecastForm');
    const generateBtn = document.getElementById('generateBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const kpiRow = document.getElementById('kpiRow');
    const insightsRow = document.getElementById('insightsRow');
    const forecastChart = document.getElementById('forecastChart');

    forecastForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const product = document.getElementById('productSelect').value;
        const category = document.getElementById('categorySelect').value;
        const horizon = document.getElementById('horizonSelect').value;
        const model = document.getElementById('modelSelect').value;

        if (!product) return;

        // UI State: Loading
        generateBtn.disabled = true;
        generateBtn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status"></span> Generating...`;
        loadingSpinner.style.display = 'block';
        forecastChart.style.opacity = '0.5';

        // API Call
        fetch('/api/forecast', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product, category, horizon, model })
        })
        .then(response => response.json())
        .then(res => {
            if (res.status === 'success') {
                updateUI(res.data);
            } else {
                alert('Error generating forecast: ' + res.message);
            }
        })
        .catch(err => {
            console.error('Forecast API Error:', err);
            alert('A system error occurred while generating the forecast.');
        })
        .finally(() => {
            // UI State: Reset
            generateBtn.disabled = false;
            generateBtn.innerHTML = `<i class="bi bi-magic me-2"></i>Generate`;
            loadingSpinner.style.display = 'none';
            forecastChart.style.opacity = '1';
        });
    });

    function updateUI(data) {
        // 1. Show Hidden Sections
        kpiRow.style.display = 'flex';
        insightsRow.style.display = 'flex';

        // 2. Update KPI Cards
        document.getElementById('kpiVolume').textContent = data.summary.total;
        document.getElementById('kpiGrowth').innerHTML = `<i class="bi bi-arrow-up-short"></i> ${data.summary.growth}`;
        document.getElementById('kpiConfidence').textContent = data.summary.confidence;
        document.getElementById('kpiPeakDate').textContent = new Date(data.summary.peak_date).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
        document.getElementById('kpiPeakVal').textContent = data.summary.peak_value + ' units';
        document.getElementById('kpiRisk').textContent = data.summary.risk;
        
        const riskCard = document.getElementById('kpiRisk').closest('.kpi-card');
        if (data.summary.risk === 'High') {
            document.getElementById('kpiRiskDetail').textContent = 'Urgent action required';
            document.getElementById('kpiRiskDetail').className = 'kpi-delta negative';
            riskCard.querySelector('.kpi-glow').setAttribute('data-bg', '#ef4444');
        } else {
            document.getElementById('kpiRiskDetail').textContent = 'No immediate action';
            document.getElementById('kpiRiskDetail').className = 'kpi-delta positive';
            riskCard.querySelector('.kpi-glow').setAttribute('data-bg', '#10b981');
        }

        // 3. Render Unified Chart
        renderUnifiedChart(data.historical, data.forecast);

        // 4. Update Alerts
        const alertsContainer = document.getElementById('alertsContainer');
        alertsContainer.innerHTML = '';
        if (data.alerts.length === 0) {
            alertsContainer.innerHTML = '<div class="text-muted text-center p-3">No immediate risks detected.</div>';
        } else {
            data.alerts.forEach(alert => {
                const alertDiv = document.createElement('div');
                alertDiv.className = `alert-box alert-${alert.type === 'danger' ? 'risk' : 'warn'} mb-2`;
                alertDiv.innerHTML = `<i class="bi bi-${alert.type === 'danger' ? 'exclamation-octagon' : 'exclamation-triangle'}"></i> <div>${alert.message}</div>`;
                alertsContainer.appendChild(alertDiv);
            });
        }

        // 5. Update Recommendations Table
        const tableBody = document.getElementById('recommendationsTable');
        tableBody.innerHTML = '';
        data.recommendations.forEach(rec => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${new Date(rec.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}</td>
                <td><span class="seg-badge seg-reg">${rec.action}</span></td>
                <td class="fw-bold">${rec.quantity.toLocaleString()} units</td>
            `;
            tableBody.appendChild(row);
        });

        // Re-apply data-bg for the risk card color change
        document.querySelectorAll('[data-bg]').forEach(function(el) {
            el.style.background = el.getAttribute('data-bg');
        });
    }

    function renderUnifiedChart(historical, forecast) {
        const histDates = historical.map(d => d.date);
        const histValues = historical.map(d => d.value);

        const foreDates = forecast.map(d => d.date);
        const foreValues = forecast.map(d => d.value);
        const foreUpper = forecast.map(d => d.upper);
        const foreLower = forecast.map(d => d.lower);

        // Bridge the gap between historical and forecast
        const lastHist = historical[historical.length - 1];
        const bridgeDates = [lastHist.date, foreDates[0]];
        const bridgeValues = [lastHist.value, foreValues[0]];

        const traceHist = {
            x: histDates,
            y: histValues,
            name: 'Historical Sales',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#3b82f6', width: 3 }
        };

        const traceFore = {
            x: foreDates,
            y: foreValues,
            name: 'Forecasted Demand',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#a855f7', width: 3, dash: 'dash' }
        };

        const traceBridge = {
            x: bridgeDates,
            y: bridgeValues,
            name: 'Transition',
            type: 'scatter',
            mode: 'lines',
            showlegend: false,
            line: { color: '#6366f1', width: 2, dash: 'dot' }
        };

        const traceUpper = {
            x: foreDates,
            y: foreUpper,
            name: 'Upper Bound',
            type: 'scatter',
            mode: 'lines',
            line: { width: 0 },
            showlegend: false
        };

        const traceLower = {
            x: foreDates,
            y: foreLower,
            name: 'Confidence Interval',
            type: 'scatter',
            mode: 'lines',
            line: { width: 0 },
            fill: 'tonexty',
            fillcolor: 'rgba(168, 85, 247, 0.15)'
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'Inter, sans-serif', color: '#94a3b8' },
            margin: { l: 50, r: 50, t: 30, b: 50 },
            hovermode: 'x unified',
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                linecolor: 'rgba(255,255,255,0.1)'
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                linecolor: 'rgba(255,255,255,0.1)',
                title: 'Volume (Units)'
            },
            legend: {
                orientation: 'h',
                y: -0.2,
                x: 0.5,
                xanchor: 'center',
                bgcolor: 'rgba(8,14,26,0.8)',
                bordercolor: 'rgba(255,255,255,0.1)',
                borderwidth: 1
            }
        };

        Plotly.newPlot('forecastChart', [traceUpper, traceLower, traceHist, traceBridge, traceFore], layout, { responsive: true, displayModeBar: false });
    }
});

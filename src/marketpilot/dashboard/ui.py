"""
MarketPilot Dashboard — UI templates.
"""

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MarketPilot Dashboard</title>
    <style>
        :root {
            --bg: #0f1115;
            --surface: #1a1d24;
            --surface-hover: #242830;
            --text: #e2e8f0;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --border: #334155;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }

        header {
            background-color: var(--surface);
            padding: 1rem 2rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header-title {
            font-size: 1.25rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .badge {
            background-color: var(--border);
            color: var(--text-muted);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.05em;
        }
        
        .badge.testnet {
            background-color: rgba(239, 68, 68, 0.2);
            color: #fca5a5;
        }
        
        .badge.mainnet {
            background-color: rgba(16, 185, 129, 0.2);
            color: #6ee7b7;
        }

        main {
            padding: 2rem;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            box-sizing: border-box;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
        }

        .panel {
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
        }

        .panel-header {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.5rem;
            color: var(--text);
            display: flex;
            justify-content: space-between;
        }

        .stat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .stat {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .stat-label {
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        .stat-value {
            font-size: 1.2rem;
            font-weight: 500;
        }
        
        .stat-value.up { color: var(--success); }
        .stat-value.down { color: var(--danger); }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }

        th, td {
            text-align: left;
            padding: 0.75rem 0.5rem;
            border-bottom: 1px solid var(--border);
        }

        th {
            color: var(--text-muted);
            font-weight: 500;
        }

        .empty-state {
            color: var(--text-muted);
            font-style: italic;
            text-align: center;
            padding: 2rem 0;
        }

        button {
            background-color: var(--surface-hover);
            color: var(--text);
            border: 1px solid var(--border);
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background-color 0.2s;
        }

        button:hover {
            background-color: var(--border);
        }
        
        canvas {
            width: 100%;
            height: 200px;
            margin-top: 1rem;
            background-color: var(--bg);
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <header>
        <div class="header-title">
            MarketPilot Dashboard
            <span class="badge" id="env-badge">LOADING</span>
        </div>
        <div>
            <span id="last-updated" style="color: var(--text-muted); font-size: 0.9rem; margin-right: 1rem;"></span>
            <button onclick="refreshAll()">Refresh Data</button>
        </div>
    </header>

    <main>
        <div class="panel" style="grid-column: 1 / -1;">
            <div class="panel-header">
                Market Analysis (BTCUSDT)
                <span id="market-status" style="font-size: 0.8rem; font-weight: normal;"></span>
            </div>
            <div class="stat-grid" id="market-stats" style="grid-template-columns: repeat(4, 1fr);">
                <div class="stat"><span class="stat-label">Price</span><span class="stat-value" id="val-price">--</span></div>
                <div class="stat"><span class="stat-label">Signal</span><span class="stat-value" id="val-signal">--</span></div>
                <div class="stat"><span class="stat-label">RSI</span><span class="stat-value" id="val-rsi">--</span></div>
                <div class="stat"><span class="stat-label">Risk Eligible</span><span class="stat-value" id="val-eligible">--</span></div>
            </div>
            <canvas id="price-chart"></canvas>
        </div>

        <div class="panel">
            <div class="panel-header">Paper Account</div>
            <div id="paper-content">
                <div class="stat-grid" style="margin-bottom: 1rem;">
                    <div class="stat"><span class="stat-label">Equity</span><span class="stat-value" id="val-equity">--</span></div>
                    <div class="stat"><span class="stat-label">Realized PnL</span><span class="stat-value" id="val-rpnl">--</span></div>
                </div>
                <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 0.5rem;">Open Positions</div>
                <div id="paper-positions"></div>
            </div>
        </div>

        <div class="panel">
            <div class="panel-header">Latest Scanner Results</div>
            <div id="scanner-content" style="overflow-x: auto;">
                <div class="empty-state">Loading...</div>
            </div>
        </div>
        
        <div class="panel" style="grid-column: 1 / -1;">
            <div class="panel-header">Autopilot Control Center</div>
            <div class="stat-grid" style="margin-bottom: 1rem;">
                <div class="stat"><span class="stat-label">Execution Mode</span><span class="stat-value" id="val-exec-mode">--</span></div>
                <div class="stat"><span class="stat-label">Control Key</span>
                    <input type="password" id="control-key-input" placeholder="Enter Control Key" style="padding: 0.5rem; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--text); font-size: 0.9rem;" />
                </div>
            </div>
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
                <button onclick="runAutopilot()" style="background-color: var(--success); color: white; border: none; font-weight: bold;">Run Candidate Autopilot Cycle</button>
                <button onclick="manualClosePrompt()" style="background-color: var(--danger); color: white; border: none; font-weight: bold;">Manual Force Close</button>
            </div>
            <div id="autopilot-logs" style="font-family: monospace; font-size: 0.85rem; background: var(--bg); padding: 1rem; border-radius: 4px; border: 1px solid var(--border); max-height: 150px; overflow-y: auto;">
                <div>Waiting for actions...</div>
            </div>
        </div>

        <div class="panel" style="grid-column: 1 / -1;">
            <div class="panel-header">Historical Runs</div>
            <div class="stat-grid">
                <div>
                    <div style="font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem;">Latest Backtest</div>
                    <div id="backtest-content">
                        <div class="empty-state">No historical run available</div>
                    </div>
                </div>
                <div>
                    <div style="font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem;">Latest Optimization</div>
                    <div id="optimization-content">
                        <div class="empty-state">No historical run available</div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        async function fetchAPI(endpoint) {
            try {
                const res = await fetch(endpoint);
                if (!res.ok) {
                    if (res.status === 404) return null;
                    throw new Error(`HTTP ${res.status}`);
                }
                const json = await res.json();
                return json.data || json;
            } catch (err) {
                console.error(err);
                return null;
            }
        }
        
        function logAutopilot(msg) {
            const logs = document.getElementById("autopilot-logs");
            const div = document.createElement("div");
            const time = new Date().toLocaleTimeString();
            div.textContent = `[${time}] ${msg}`;
            logs.appendChild(div);
            logs.scrollTop = logs.scrollHeight;
        }

        async function runAutopilot() {
            const key = document.getElementById("control-key-input").value;
            if (!key) return alert("Please enter the Control Key first.");
            logAutopilot("Triggering autopilot cycle...");
            try {
                const res = await fetch("/api/control/autopilot/run", {
                    method: "POST",
                    headers: { "x-marketpilot-control-key": key, "Content-Type": "application/json" }
                });
                const data = await res.json();
                if (res.ok) {
                    if (data.decision) {
                        logAutopilot(`Cycle complete. Target selected: ${data.decision.candidate.symbol}. Executed: ${data.decision.executed}`);
                    } else {
                        logAutopilot(`Cycle complete: ${data.message}`);
                    }
                } else {
                    logAutopilot(`Error: ${data.detail}`);
                }
            } catch (e) {
                logAutopilot(`Request failed: ${e.message}`);
            }
        }
        
        async function manualClosePrompt() {
            const key = document.getElementById("control-key-input").value;
            if (!key) return alert("Please enter the Control Key first.");
            const symbol = prompt("Enter the Demo symbol to manually close (e.g. BTCUSDT):");
            if (!symbol) return;
            logAutopilot(`Triggering manual close for ${symbol}...`);
            try {
                const res = await fetch("/api/control/demo/close", {
                    method: "POST",
                    headers: { "x-marketpilot-control-key": key, "Content-Type": "application/json" },
                    body: JSON.stringify({ symbol: symbol })
                });
                const data = await res.json();
                if (res.ok) {
                    logAutopilot(`Successfully closed ${symbol}. Record: ${data.record.order_link_id}`);
                } else {
                    logAutopilot(`Error: ${data.detail}`);
                }
            } catch (e) {
                logAutopilot(`Request failed: ${e.message}`);
            }
        }

        function formatDecimal(val, suffix = "") {
            if (val === null || val === undefined) return "--";
            return Number(val).toFixed(4) + suffix;
        }

        async function refreshMarket() {
            const data = await fetchAPI("/api/market?symbol=BTCUSDT&interval=60");
            if (data) {
                document.getElementById("val-price").textContent = formatDecimal(data.latest_price);
                
                const sig = data.signal.direction;
                const sigEl = document.getElementById("val-signal");
                sigEl.textContent = sig;
                sigEl.className = "stat-value " + (sig === "LONG" ? "up" : (sig === "SHORT" ? "down" : ""));
                
                document.getElementById("val-rsi").textContent = formatDecimal(data.indicators.rsi);
                
                const elig = data.risk.eligible_for_paper_trading;
                document.getElementById("val-eligible").textContent = elig ? "YES" : "NO";
                
                drawChart(data.klines);
            }
        }

        async function refreshPaper() {
            const data = await fetchAPI("/api/paper");
            if (data) {
                document.getElementById("val-equity").textContent = formatDecimal(data.equity);
                
                const rpnl = Number(data.realized_pnl);
                const rpnlEl = document.getElementById("val-rpnl");
                rpnlEl.textContent = formatDecimal(rpnl);
                rpnlEl.className = "stat-value " + (rpnl > 0 ? "up" : (rpnl < 0 ? "down" : ""));

                const posContainer = document.getElementById("paper-positions");
                if (data.positions && data.positions.length > 0) {
                    let html = '<table><tr><th>Symbol</th><th>Dir</th><th>Qty</th><th>uPnL</th><th>Action</th></tr>';
                    for (const p of data.positions) {
                        const upnl = Number(p.unrealized_pnl);
                        const uCls = upnl > 0 ? "up" : (upnl < 0 ? "down" : "");
                        
                        let actHtml = p.decision_action || "N/A";
                        if (actHtml !== "HOLD" && actHtml !== "N/A" && actHtml !== "INVALID") {
                            actHtml = `<span style="color: var(--danger); font-weight: 600;">${actHtml}</span>`;
                        } else if (actHtml === "HOLD") {
                            actHtml = `<span style="color: var(--text-muted);">${actHtml}</span>`;
                        }
                        
                        html += `<tr>
                            <td>${p.symbol}</td>
                            <td class="${p.direction === 'LONG' ? 'up' : 'down'}">${p.direction}</td>
                            <td>${formatDecimal(p.quantity)}</td>
                            <td class="${uCls}">${formatDecimal(upnl)}</td>
                            <td>${actHtml}</td>
                        </tr>`;
                    }
                    html += '</table>';
                    posContainer.innerHTML = html;
                } else {
                    posContainer.innerHTML = '<div class="empty-state">No open positions</div>';
                }
            }
        }
        
        async function refreshScanner() {
            const data = await fetchAPI("/api/scan");
            const container = document.getElementById("scanner-content");
            if (data && data.length > 0) {
                let html = '<table><tr><th>Symbol</th><th>Close</th><th>24h Chg</th><th>Turnover</th></tr>';
                for (const r of data) {
                    const chg = Number(r.price_change_percent) * 100;
                    const chgCls = chg > 0 ? "up" : (chg < 0 ? "down" : "");
                    html += `<tr>
                        <td>${r.symbol}</td>
                        <td>${formatDecimal(r.last_price)}</td>
                        <td class="${chgCls}">${formatDecimal(chg, '%')}</td>
                        <td>${formatDecimal(r.turnover_24h)}</td>
                    </tr>`;
                }
                html += '</table>';
                container.innerHTML = html;
            } else {
                container.innerHTML = '<div class="empty-state">No scan results</div>';
            }
        }

        async function refreshReports() {
            const bt = await fetchAPI("/api/backtest/latest");
            if (bt) {
                document.getElementById("backtest-content").innerHTML = `
                    <div class="stat"><span class="stat-label">Symbol</span><span class="stat-value">${bt.symbol} (${bt.interval}m)</span></div>
                    <div class="stat" style="margin-top: 0.5rem;"><span class="stat-label">Return</span><span class="stat-value">${formatDecimal(Number(bt.metrics.total_return_fraction) * 100, "%")}</span></div>
                    <div class="stat" style="margin-top: 0.5rem;"><span class="stat-label">Trades</span><span class="stat-value">${bt.metrics.trade_count}</span></div>
                `;
            } else {
                document.getElementById("backtest-content").innerHTML = '<div class="empty-state">No historical run available</div>';
            }
            
            const opt = await fetchAPI("/api/optimization/latest");
            if (opt) {
                document.getElementById("optimization-content").innerHTML = `
                    <div class="stat"><span class="stat-label">Symbol</span><span class="stat-value">${opt.symbol} (${opt.interval}m)</span></div>
                    <div class="stat" style="margin-top: 0.5rem;"><span class="stat-label">Candidates</span><span class="stat-value">${opt.candidates ? opt.candidates.length : 0}</span></div>
                    <div class="stat" style="margin-top: 0.5rem;"><span class="stat-label">Best Label</span><span class="stat-value">${opt.best_candidate ? opt.best_candidate.candidate.label : 'None'}</span></div>
                `;
            } else {
                document.getElementById("optimization-content").innerHTML = '<div class="empty-state">No historical run available</div>';
            }
        }

        function drawChart(klines) {
            const canvas = document.getElementById("price-chart");
            const ctx = canvas.getContext("2d");
            // Set internal resolution based on CSS size
            canvas.width = canvas.clientWidth * window.devicePixelRatio;
            canvas.height = canvas.clientHeight * window.devicePixelRatio;
            ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
            
            const width = canvas.clientWidth;
            const height = canvas.clientHeight;
            
            ctx.clearRect(0, 0, width, height);
            if (!klines || klines.length === 0) return;
            
            const prices = klines.map(k => Number(k.close));
            const min = Math.min(...prices);
            const max = Math.max(...prices);
            const range = max - min || 1;
            
            const xStep = width / Math.max(1, prices.length - 1);
            
            ctx.beginPath();
            ctx.strokeStyle = "#3b82f6";
            ctx.lineWidth = 2;
            
            for (let i = 0; i < prices.length; i++) {
                const x = i * xStep;
                // Pad Y slightly so it doesn't touch the top/bottom exactly
                const paddedRange = range * 1.2;
                const paddedMin = min - range * 0.1;
                const y = height - ((prices[i] - paddedMin) / paddedRange) * height;
                
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        let isRefreshing = false;
        let refreshTimer = null;

        async function refreshAll() {
            if (isRefreshing) return;
            isRefreshing = true;
            
            if (refreshTimer) clearTimeout(refreshTimer);
            
            document.getElementById("last-updated").textContent = "Updating...";
            await Promise.all([
                refreshMarket(),
                refreshPaper(),
                refreshScanner(),
                refreshReports()
            ]);
            document.getElementById("last-updated").textContent = "Updated " + new Date().toLocaleTimeString();
            
            const isTestnet = window.location.hostname.includes("testnet") || true; 
            const badge = document.getElementById("env-badge");
            
            // Check settings for Autopilot
            const settings = await fetchAPI("/api/settings");
            if (settings) {
                const modeEl = document.getElementById("val-exec-mode");
                if (settings.kill_switch) {
                    modeEl.textContent = "EMERGENCY KILLED";
                    modeEl.className = "stat-value down";
                    badge.textContent = "KILLED";
                    badge.className = "badge down";
                } else if (settings.demo_execution_enabled) {
                    if (settings.demo_auto_submit_enabled) {
                        modeEl.textContent = "ARMED (AUTO-SUBMIT)";
                        modeEl.className = "stat-value up";
                    } else {
                        modeEl.textContent = "SUGGEST-ONLY (DEMO READY)";
                        modeEl.className = "stat-value";
                    }
                    badge.textContent = "DEMO (ACTIVE)";
                    badge.className = "badge testnet";
                } else {
                    modeEl.textContent = "DISABLED (OBSERVER)";
                    modeEl.className = "stat-value down";
                    badge.textContent = "OBSERVER";
                    badge.className = "badge";
                }
            } else {
                badge.textContent = "TESTNET";
                badge.className = "badge testnet";
            }
            
            isRefreshing = false;
            
            // Auto refresh every 30 seconds to match cache
            refreshTimer = setTimeout(refreshAll, 30000);
        }

        refreshAll();
    </script>
</body>
</html>
"""

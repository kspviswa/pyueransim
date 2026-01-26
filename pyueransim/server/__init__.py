"""
FastAPI + WebSocket Server for pyueransim.
Provides real-time metrics, control interface, and configuration forms.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import uuid


# Global simulation instances
gnb_simulation = None


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

# Global log buffer
log_buffer: List[Dict[str, Any]] = []
max_log_buffer = 1000


def add_log(level: str, message: str) -> None:
    """Add log entry to buffer."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message
    }
    log_buffer.append(entry)
    if len(log_buffer) > max_log_buffer:
        log_buffer.pop(0)
    asyncio.create_task(manager.broadcast({"type": "log", "data": entry}))


# FastAPI app
app = FastAPI(
    title="PyUERANSIM - 5G SA Simulator",
    description="Python port of UERANSIM - 5G Standalone gNB and UE Simulator",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class GnbConfigModel(BaseModel):
    mcc: str = "208"
    mnc: str = "93"
    nci: int = 0x000000010
    id_length: int = 32
    tac: int = 1
    ngap_ip: str = "127.0.0.1"
    gtp_ip: str = "127.0.0.1"
    amf_ip: str = "127.0.0.1"
    amf_port: int = 38412


class UeConfigModel(BaseModel):
    imsi: str = "imsi-208930000000001"
    key: str = "8baf473f2f8fd09487cccbd7097c6862"
    opc: str = "8e27b6af0e692e750f32667a3b14605d"
    amf: str = "8000"
    dnn: str = "internet"
    sst: int = 1
    sd: int = 0x010203


class MultipleUeConfigModel(BaseModel):
    """Config for adding multiple UEs at once."""
    count: int = 1
    imsi_prefix: str = "imsi-208930000000001"
    key: str = "8baf473f2f8fd09487cccbd7097c6862"
    opc: str = "8e27b6af0e692e750f32667a3b14605d"
    amf: str = "8000"
    dnn: str = "internet"
    sst: int = 1
    sd: int = 0x010203


class ControlCommand(BaseModel):
    command: str
    ue_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


async def initialize_simulation(gnb_config: GnbConfigModel) -> None:
    """Initialize the gNB simulation with real AMF connection."""
    global gnb_simulation

    from pyueransim.simulation import GnbSimulation, GnbConfig

    cfg = GnbConfig(
        mcc=gnb_config.mcc,
        mnc=gnb_config.mnc,
        nci=gnb_config.nci,
        id_length=gnb_config.id_length,
        tac=gnb_config.tac,
        ngap_ip=gnb_config.ngap_ip,
        gtp_ip=gnb_config.gtp_ip,
        amf_ip=gnb_config.amf_ip,
        amf_port=gnb_config.amf_port
    )

    gnb_id = f"gnb-{uuid.uuid4().hex[:8]}"
    gnb_simulation = GnbSimulation(cfg, gnb_id)
    gnb_simulation.on_log = add_log

    add_log("INFO", f"gNB initialized: {gnb_id}")
    add_log("INFO", f"  AMF: {gnb_config.amf_ip}:{gnb_config.amf_port}")
    add_log("INFO", f"  Local IP: {gnb_config.ngap_ip}")


@app.get("/")
async def root():
    """Return HTML UI."""
    return HTMLResponse(get_html_content())


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "simulation_running": gnb_simulation is not None and gnb_simulation.amf_connected
    }


@app.post("/api/gnb/start")
async def start_gnb(config: GnbConfigModel) -> Dict[str, Any]:
    """Configure and start gNB to connect to AMF."""
    global gnb_simulation

    from pyueransim.simulation import GnbSimulation, GnbConfig

    if gnb_simulation and gnb_simulation.amf_connected:
        return {"status": "already_running", "amf_connected": True}

    cfg = GnbConfig(
        mcc=config.mcc,
        mnc=config.mnc,
        nci=config.nci,
        id_length=config.id_length,
        tac=config.tac,
        ngap_ip=config.ngap_ip,
        gtp_ip=config.gtp_ip,
        amf_ip=config.amf_ip,
        amf_port=config.amf_port
    )

    gnb_id = f"gnb-{uuid.uuid4().hex[:8]}"
    gnb_simulation = GnbSimulation(cfg, gnb_id)
    gnb_simulation.on_log = add_log

    add_log("INFO", f"Starting gNB: {gnb_id}")
    add_log("INFO", f"  AMF: {config.amf_ip}:{config.amf_port}")
    add_log("INFO", f"  MCC/MNC: {config.mcc}/{config.mnc}")

    await gnb_simulation.start()

    if gnb_simulation.amf_connected:
        add_log("INFO", "gNB connected to AMF successfully")
        return {"status": "started", "amf_connected": True, "gnb_id": gnb_id}
    else:
        add_log("ERROR", "Failed to connect to AMF")
        gnb_simulation = None
        return {"status": "failed", "amf_connected": False}


@app.post("/api/gnb/stop")
async def stop_gnb() -> Dict[str, Any]:
    """Stop gNB and disconnect from AMF."""
    global gnb_simulation

    if gnb_simulation:
        await gnb_simulation.stop()
        add_log("INFO", "gNB stopped")
        gnb_simulation = None

    return {"status": "stopped"}


@app.get("/api/gnb/state")
async def get_gnb_state() -> Dict[str, Any]:
    """Get gNB state."""
    if gnb_simulation is None:
        return {"running": False, "configured": False}
    return {
        "running": True,
        "configured": True,
        "gnb_id": gnb_simulation.gnb_id,
        "state": gnb_simulation.get_state().__dict__,
        "config": gnb_simulation.config.__dict__
    }


@app.get("/api/gnb/ues")
async def get_ue_states() -> Dict[str, Any]:
    """Get all UE states."""
    if gnb_simulation is None:
        return {"ues": []}
    return {"ues": gnb_simulation.get_ue_states()}


@app.post("/api/gnb/ues")
async def add_ue(config: UeConfigModel) -> Dict[str, Any]:
    """Add a new UE to simulation."""
    if gnb_simulation is None:
        raise HTTPException(status_code=404, detail="gNB not running")

    from pyueransim.simulation import UeSimulation, UeConfig

    ue_cfg = UeConfig(
        imsi=config.imsi,
        key=config.key,
        opc=config.opc,
        amf=config.amf,
        dnn=config.dnn,
        sst=config.sst,
        sd=config.sd
    )

    ue_id = f"ue-{uuid.uuid4().hex[:8]}"
    ue = UeSimulation(ue_cfg, ue_id)
    ue.log_callback = add_log
    gnb_simulation.ues[ue_id] = ue

    add_log("INFO", f"UE added: {ue_id} (IMSI: {config.imsi})")

    return {"ue_id": ue_id, "state": ue.get_state().__dict__}


@app.post("/api/gnb/ues/multiple")
async def add_multiple_ues(config: MultipleUeConfigModel) -> Dict[str, Any]:
    """Add multiple UEs at once."""
    if gnb_simulation is None:
        raise HTTPException(status_code=404, detail="gNB not running")

    from pyueransim.simulation import UeSimulation, UeConfig

    added_ues = []
    for i in range(config.count):
        suffix = str(int(config.imsi_prefix.split('-')[-1]) + i).zfill(12)
        imsi = f"imsi-{suffix}"

        ue_cfg = UeConfig(
            imsi=imsi,
            key=config.key,
            opc=config.opc,
            amf=config.amf,
            dnn=config.dnn,
            sst=config.sst,
            sd=config.sd
        )

        ue_id = f"ue-{uuid.uuid4().hex[:8]}"
        ue = UeSimulation(ue_cfg, ue_id)
        ue.log_callback = add_log
        gnb_simulation.ues[ue_id] = ue
        added_ues.append({"ue_id": ue_id, "imsi": imsi})

    add_log("INFO", f"Added {config.count} UEs")
    return {"status": "added", "ues": added_ues}


@app.post("/api/gnb/ues/{ue_id}/register")
async def trigger_registration(ue_id: str) -> Dict[str, Any]:
    """Trigger UE registration."""
    if gnb_simulation is None:
        raise HTTPException(status_code=404, detail="gNB not running")
    if ue_id not in gnb_simulation.ues:
        raise HTTPException(status_code=404, detail="UE not found")

    ue = gnb_simulation.ues[ue_id]
    await ue.start_registration(gnb_simulation.gnb_id)
    add_log("INFO", f"Registration triggered for UE: {ue_id}")

    return {"status": "registration_started", "ue_id": ue_id}


@app.delete("/api/gnb/ues/{ue_id}")
async def remove_ue(ue_id: str) -> Dict[str, Any]:
    """Remove UE from simulation."""
    if gnb_simulation is None:
        raise HTTPException(status_code=404, detail="gNB not running")
    if ue_id not in gnb_simulation.ues:
        raise HTTPException(status_code=404, detail="UE not found")

    del gnb_simulation.ues[ue_id]
    add_log("INFO", f"UE removed: {ue_id}")

    return {"status": "removed", "ue_id": ue_id}


@app.get("/api/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Get all metrics."""
    if gnb_simulation is None:
        return {"gnb": {}, "ues": []}

    return {
        "gnb": gnb_simulation.get_metrics(),
        "ues": [ue.get_metrics() for ue in gnb_simulation.ues.values()]
    }


@app.get("/api/logs")
async def get_logs(level: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    """Get log entries."""
    logs = log_buffer
    if level:
        logs = [l for l in logs if l["level"] == level.upper()]
    return {"logs": logs[-limit:], "total": len(log_buffer)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            if gnb_simulation:
                state = {
                    "type": "state",
                    "data": {
                        "gnb_id": gnb_simulation.gnb_id,
                        "gnb_state": gnb_simulation.get_state().__dict__,
                        "metrics": gnb_simulation.get_metrics(),
                        "ue_count": len(gnb_simulation.ues),
                        "amf_connected": gnb_simulation.amf_connected
                    }
                }
                await websocket.send_json(state)

            await asyncio.sleep(1.0)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def get_html_content() -> str:
    """Generate HTML UI content."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyUERANSIM - 5G SA Simulator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f1a; color: #eee; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 1rem; }
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 1.5rem 2rem; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { color: #00d4ff; font-size: 1.5rem; font-weight: 600; }
        .status-badge { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; border-radius: 20px; background: #1a1a2e; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; background: #666; }
        .status-dot.running { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
        .status-dot.stopped { background: #ff4757; }
        .status-text { font-size: 0.875rem; color: #888; }

        /* Setup Screen */
        .setup-screen { display: flex; justify-content: center; align-items: center; min-height: calc(100vh - 80px); padding: 2rem; }
        .setup-card { background: #1a1a2e; border-radius: 16px; padding: 2rem; width: 100%; max-width: 600px; border: 1px solid #333; }
        .setup-card h2 { color: #00d4ff; margin-bottom: 0.5rem; font-size: 1.25rem; }
        .setup-card p { color: #888; margin-bottom: 1.5rem; font-size: 0.875rem; }
        .form-section { margin-bottom: 1.5rem; }
        .form-section h3 { color: #fff; font-size: 0.875rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #333; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
        .form-group { margin-bottom: 0.75rem; }
        .form-group label { display: block; font-size: 0.75rem; color: #888; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .form-group input { width: 100%; background: #0f0f1a; border: 1px solid #333; color: #eee; padding: 0.75rem; border-radius: 8px; font-size: 0.875rem; transition: border-color 0.2s; }
        .form-group input:focus { outline: none; border-color: #00d4ff; }
        .form-group input::placeholder { color: #555; }
        .start-btn { width: 100%; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); color: #000; border: none; padding: 1rem; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
        .start-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0, 212, 255, 0.3); }

        /* Dashboard Screen */
        .dashboard-screen { display: none; }
        .dashboard-screen.active { display: block; }
        .setup-screen.hidden { display: none; }

        .dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
        .card { background: #1a1a2e; border-radius: 12px; padding: 1.25rem; border: 1px solid #333; }
        .card h3 { color: #00d4ff; font-size: 0.875rem; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }
        .card-header-action { font-size: 0.75rem; color: #888; cursor: pointer; }
        .card-header-action:hover { color: #00d4ff; }

        .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }
        .metric { background: #0f0f1a; padding: 1rem; border-radius: 8px; text-align: center; }
        .metric-value { font-size: 1.75rem; font-weight: 700; color: #00ff88; }
        .metric-label { font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 0.25rem; }

        .ue-list { max-height: 300px; overflow-y: auto; }
        .ue-item { background: #0f0f1a; padding: 0.75rem; border-radius: 8px; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center; }
        .ue-info { flex: 1; }
        .ue-id { font-size: 0.875rem; color: #fff; }
        .ue-imsi { font-size: 0.7rem; color: #666; font-family: monospace; }
        .ue-state { padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
        .ue-state.registered { background: #00ff88; color: #000; }
        .ue-state.connecting { background: #ffaa00; color: #000; }
        .ue-state.disconnected { background: #333; color: #888; }

        .add-ue-form { background: #0f0f1a; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
        .add-ue-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem; }
        .add-ue-form input { width: 100%; background: #1a1a2e; border: 1px solid #333; color: #eee; padding: 0.5rem; border-radius: 4px; font-size: 0.8rem; }
        .add-ue-btn { width: 100%; background: #333; color: #fff; border: none; padding: 0.75rem; border-radius: 6px; cursor: pointer; font-size: 0.875rem; transition: background 0.2s; }
        .add-ue-btn:hover { background: #444; }

        .logs-container { max-height: 250px; overflow-y: auto; font-family: 'Monaco', 'Menlo', monospace; font-size: 0.75rem; background: #0a0a12; padding: 0.75rem; border-radius: 8px; }
        .log-entry { padding: 0.25rem 0; border-bottom: 1px solid #1a1a2e; display: flex; gap: 0.5rem; }
        .log-time { color: #555; }
        .log-level { color: #00d4ff; font-weight: 600; min-width: 40px; }
        .log-msg { color: #aaa; }
        .log-entry.ERROR .log-msg { color: #ff4757; }
        .log-entry.WARN .log-msg { color: #ffaa00; }

        .stop-btn { background: #ff4757; color: #fff; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.875rem; }
        .stop-btn:hover { background: #ff6b7a; }

        .add-multiple-section { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #333; }
        .add-multiple-row { display: flex; gap: 0.5rem; align-items: flex-end; }
        .add-multiple-row input[type="number"] { width: 80px; }
        .add-multiple-row input[type="text"] { flex: 1; }
        .batch-btn { background: #0099cc; color: #fff; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="header">
        <h1>PyUERANSIM</h1>
        <div class="status-badge">
            <div class="status-dot" id="statusDot"></div>
            <span class="status-text" id="statusText">Not Running</span>
        </div>
    </div>

    <!-- Setup Screen -->
    <div class="setup-screen" id="setupScreen">
        <div class="setup-card">
            <h2>Connect gNB to 5G Core</h2>
            <p>Configure your gNB to connect to an AMF. Default values work for local Open5GS.</p>

            <div class="form-section">
                <h3>Network Configuration</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label>MCC</label>
                        <input type="text" id="mcc" value="208" placeholder="e.g., 208">
                    </div>
                    <div class="form-group">
                        <label>MNC</label>
                        <input type="text" id="mnc" value="93" placeholder="e.g., 93">
                    </div>
                </div>
                <div class="form-group">
                    <label>AMF IP Address</label>
                    <input type="text" id="amfIp" value="127.0.0.1" placeholder="IP of your 5G Core AMF">
                </div>
                <div class="form-group">
                    <label>AMF Port</label>
                    <input type="text" id="amfPort" value="38412" placeholder="SCTP port (default: 38412)">
                </div>
            </div>

            <div class="form-section">
                <h3>Local gNB Settings</h3>
                <div class="form-group">
                    <label>gNB IP Address</label>
                    <input type="text" id="gnbIp" value="127.0.0.1" placeholder="Local IP for this gNB">
                </div>
            </div>

            <button class="start-btn" onclick="startSimulation()">Start gNB</button>
        </div>
    </div>

    <!-- Dashboard Screen -->
    <div class="dashboard-screen" id="dashboardScreen">
        <div class="container">
            <div class="card" style="margin-bottom: 1rem;">
                <h3>
                    <span>Active Simulation</span>
                    <button class="stop-btn" onclick="stopSimulation()">Stop</button>
                </h3>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-value" id="metricConnectedUes">0</div>
                        <div class="metric-label">Connected UEs</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="metricTotalUes">0</div>
                        <div class="metric-label">Total UEs</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="metricMessages">0</div>
                        <div class="metric-label">Messages</div>
                    </div>
                </div>
            </div>

            <div class="dashboard-grid">
                <!-- Add UE Card -->
                <div class="card">
                    <h3>Add UE</h3>
                    <div class="add-ue-form">
                        <div class="add-ue-row">
                            <input type="text" id="ueImsi" placeholder="IMSI (e.g., imsi-208930000000001)">
                            <input type="text" id="ueKey" placeholder="Key (hex)" value="8baf473f2f8fd09487cccbd7097c6862">
                        </div>
                        <div class="add-ue-row">
                            <input type="text" id="ueOpc" placeholder="OPC (hex)" value="8e27b6af0e692e750f32667a3b14605d">
                            <input type="text" id="ueAmf" placeholder="AMF" value="8000">
                        </div>
                        <button class="add-ue-btn" onclick="addUe()">Add & Register UE</button>
                    </div>

                    <div class="add-multiple-section">
                        <div class="form-group">
                            <label style="font-size: 0.7rem; color: #888; margin-bottom: 0.5rem;">Add Multiple UEs</label>
                            <div class="add-multiple-row">
                                <input type="number" id="ueCount" value="5" min="1" max="50">
                                <input type="text" id="ueImsiPrefix" placeholder="IMSI prefix" value="imsi-208930000000001">
                                <button class="batch-btn" onclick="addMultipleUes()">Add</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Active UEs Card -->
                <div class="card">
                    <h3>
                        <span>Active UEs</span>
                        <span class="card-header-action" onclick="loadUes()">Refresh</span>
                    </h3>
                    <div class="ue-list" id="ueList">
                        <div style="color: #555; text-align: center; padding: 2rem;">No UEs connected</div>
                    </div>
                </div>

                <!-- Logs Card -->
                <div class="card" style="grid-column: 1 / -1;">
                    <h3>
                        <span>Protocol Logs</span>
                        <span class="card-header-action" onclick="clearLogs()">Clear</span>
                    </h3>
                    <div class="logs-container" id="logsContainer">
                        <div style="color: #555; text-align: center; padding: 1rem;">Logs will appear here</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let simulationRunning = false;

        function connectWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'state') updateDashboard(data.data);
                else if (data.type === 'log') addLogEntry(data.data);
            };
            ws.onclose = () => setTimeout(connectWebSocket, 3000);
        }

        async function startSimulation() {
            const config = {
                mcc: document.getElementById('mcc').value,
                mnc: document.getElementById('mnc').value,
                amf_ip: document.getElementById('amfIp').value,
                amf_port: parseInt(document.getElementById('amfPort').value),
                ngap_ip: document.getElementById('gnbIp').value,
                nci: 0x000000010,
                id_length: 32,
                tac: 1,
                gtp_ip: document.getElementById('gnbIp').value
            };

            const btn = document.querySelector('.start-btn');
            btn.textContent = 'Connecting...';
            btn.disabled = true;

            try {
                const response = await fetch('/api/gnb/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(config)
                });
                const data = await response.json();

                if (data.status === 'started' && data.amf_connected) {
                    simulationRunning = true;
                    document.getElementById('setupScreen').classList.add('hidden');
                    document.getElementById('dashboardScreen').classList.add('active');
                    updateStatus('running', 'AMF Connected');
                    addLog('INFO', 'gNB connected to AMF successfully');
                } else {
                    alert('Failed to connect to AMF. Check your configuration.');
                    btn.textContent = 'Start gNB';
                    btn.disabled = false;
                }
            } catch (e) {
                alert('Error: ' + e.message);
                btn.textContent = 'Start gNB';
                btn.disabled = false;
            }
        }

        async function stopSimulation() {
            await fetch('/api/gnb/stop', {method: 'POST'});
            simulationRunning = false;
            document.getElementById('setupScreen').classList.remove('hidden');
            document.getElementById('dashboardScreen').classList.remove('active');
            updateStatus('stopped', 'Not Running');
            addLog('INFO', 'Simulation stopped');
        }

        function updateStatus(status, text) {
            const dot = document.getElementById('statusDot');
            const label = document.getElementById('statusText');
            dot.className = 'status-dot ' + status;
            label.textContent = text;
        }

        function updateDashboard(data) {
            document.getElementById('metricConnectedUes').textContent = data.metrics.connected_ues || 0;
            document.getElementById('metricTotalUes').textContent = data.metrics.total_ues || 0;
            document.getElementById('metricMessages').textContent = data.metrics.messages_exchanged || 0;
        }

        async function addUe() {
            const ue = {
                imsi: document.getElementById('ueImsi').value || 'imsi-208930000000001',
                key: document.getElementById('ueKey').value,
                opc: document.getElementById('ueOpc').value,
                amf: document.getElementById('ueAmf').value
            };
            const response = await fetch('/api/gnb/ues', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(ue)
            });
            const data = await response.json();
            if (data.ue_id) {
                await fetch(`/api/gnb/ues/${data.ue_id}/register`, {method: 'POST'});
                loadUes();
            }
        }

        async function addMultipleUes() {
            const config = {
                count: parseInt(document.getElementById('ueCount').value),
                imsi_prefix: document.getElementById('ueImsiPrefix').value,
                key: document.getElementById('ueKey').value,
                opc: document.getElementById('ueOpc').value
            };
            await fetch('/api/gnb/ues/multiple', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });
            loadUes();
        }

        async function loadUes() {
            const response = await fetch('/api/gnb/ues');
            const data = await response.json();
            const container = document.getElementById('ueList');
            if (data.ues && data.ues.length > 0) {
                container.innerHTML = data.ues.map(ue => {
                    let stateClass = 'disconnected';
                    if (ue.rrc_state === 'RRC_CONNECTED') stateClass = 'connecting';
                    if (ue.mm_state === 'MM_REGISTERED') stateClass = 'registered';
                    return `<div class="ue-item">
                        <div class="ue-info">
                            <div class="ue-id">${ue.ue_id}</div>
                            <div class="ue-imsi">${ue.imsi || ue.ue_id}</div>
                        </div>
                        <span class="ue-state ${stateClass}">${ue.mm_state.replace('MM_', '')}</span>
                    </div>`;
                }).join('');
            } else {
                container.innerHTML = '<div style="color: #555; text-align: center; padding: 2rem;">No UEs connected</div>';
            }
        }

        function addLog(level, message) {
            const container = document.getElementById('logsContainer');
            const time = new Date().toLocaleTimeString();
            container.innerHTML = `<div class="log-entry ${level}">
                <span class="log-time">${time}</span>
                <span class="log-level">${level}</span>
                <span class="log-msg">${message}</span>
            </div>` + container.innerHTML;
            if (container.children.length > 100) container.lastChild.remove();
        }

        function addLogEntry(log) {
            const container = document.getElementById('logsContainer');
            const time = new Date(log.timestamp).toLocaleTimeString();
            container.innerHTML = `<div class="log-entry ${log.level}">
                <span class="log-time">${time}</span>
                <span class="log-level">${log.level}</span>
                <span class="log-msg">${log.message}</span>
            </div>` + container.innerHTML;
            if (container.children.length > 100) container.lastChild.remove();
        }

        function clearLogs() {
            document.getElementById('logsContainer').innerHTML = '<div style="color: #555; text-align: center; padding: 1rem;">Logs cleared</div>';
        }

        // Initialize
        connectWebSocket();
        setInterval(loadUes, 3000);
    </script>
</body>
</html>
    """


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    return app

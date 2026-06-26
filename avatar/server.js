const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');
const { exec } = require('child_process');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

const PORT = 3456;
const STATIC_DIR = __dirname;
const CACHE_DIR = path.join(__dirname, 'cache');

app.use(express.json());

app.use('/models', express.static(path.join(STATIC_DIR, 'models')));
app.use('/lib', express.static(path.join(STATIC_DIR, 'lib')));
app.use('/node_modules', express.static(path.join(STATIC_DIR, 'node_modules')));
app.use(express.static(STATIC_DIR));

app.get('/tts', (req, res) => {
    const name = req.query.name || '访客';
    const type = req.query.type || 'check_in';
    const variant = Number.isInteger(Number(req.query.variant))
        ? Math.max(0, Number(req.query.variant))
        : Math.floor(Math.random() * 6);

    if (!fs.existsSync(CACHE_DIR)) {
        fs.mkdirSync(CACHE_DIR, { recursive: true });
    }

    const cacheFile = path.join(CACHE_DIR, `${name}_${type}_${variant}.mp3`);

    if (fs.existsSync(cacheFile)) {
        return res.sendFile(cacheFile);
    }

    const ttsScript = path.join(__dirname, '..', 'core', 'tts_server.py');
    const cmd = `python "${ttsScript}" "${name}" "${type}" "${cacheFile}" "${variant}"`;

    exec(cmd, { cwd: path.join(__dirname, '..') }, (err, stdout, stderr) => {
        if (err) {
            console.error('TTS error:', stderr || err.message);
            return res.status(500).json({ error: 'TTS generation failed' });
        }
        if (fs.existsSync(cacheFile)) {
            res.sendFile(cacheFile);
        } else {
            res.status(500).json({ error: 'TTS file not found' });
        }
    });
});

wss.on('connection', (ws) => {
    console.log('Client connected');

    ws.on('message', (data) => {
        try {
            const msg = JSON.parse(data.toString());
            console.log('Received:', msg);
        } catch (e) {
            console.error('Invalid message:', data.toString());
        }
    });

    ws.on('close', () => {
        console.log('Client disconnected');
    });
});

function broadcast(event) {
    const payload = JSON.stringify(event);
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(payload);
        }
    });
}

app.post('/event', (req, res) => {
    const event = req.body;
    console.log('Event received:', event);
    broadcast(event);
    res.json({ ok: true });
});

server.listen(PORT, () => {
    console.log(`Avatar server running at http://localhost:${PORT}`);
    console.log(`Open http://localhost:${PORT} to see Epsilon`);
});

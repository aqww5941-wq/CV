const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');
const { execFile } = require('child_process');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

const PORT = 3456;
const STATIC_DIR = __dirname;
const CACHE_DIR = path.join(__dirname, 'cache');
const ROOT_DIR = path.join(__dirname, '..');
const EMPLOYEES_DIR = path.join(ROOT_DIR, 'employees');
const TTS_SCRIPT = path.join(ROOT_DIR, 'core', 'tts_server.py');
const EMPLOYEE_SYNC_SCRIPT = path.join(ROOT_DIR, 'core', 'employee_sync.py');
const LOCAL_ENROLL_SCRIPT = path.join(ROOT_DIR, 'core', 'local_enroll.py');
const VENV_PYTHON = path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe');
const PYTHON_BIN = fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python';
const TTS_VOICE_BY_MODEL = {
    epsilon: 'zh-CN-XiaoxiaoNeural',
    chitose: 'zh-TW-YunJheNeural',
    haruGreeter: 'zh-CN-XiaoxiaoNeural',
    haru: 'zh-CN-XiaoyiNeural',
    natori: 'zh-TW-YunJheNeural'
};
const TTS_VOICES = Array.from(new Set(Object.values(TTS_VOICE_BY_MODEL)));
const TTS_PREWARM_CONCURRENCY = Math.max(1, Number(process.env.TTS_PREWARM_CONCURRENCY) || 2);
const EMPLOYEE_SYNC_TOKEN = process.env.EMPLOYEE_SYNC_TOKEN || '';
const NAMED_TTS_TYPES = ['check_in', 'check_out', 'repeat', 'first_time', 'returning'];
const ANONYMOUS_TTS_TYPES = ['stranger', 'idle_long', 'crowd'];
const prewarmStatus = {
    running: false,
    complete: false,
    generated: 0,
    skipped: 0,
    total: 0,
    error: ''
};
const avatarReadyStatus = {
    ready: false,
    model: '',
    at: ''
};

app.use(express.json());

app.use('/models', express.static(path.join(STATIC_DIR, 'models')));
app.use('/lib', express.static(path.join(STATIC_DIR, 'lib')));
app.use('/node_modules', express.static(path.join(STATIC_DIR, 'node_modules')));
app.use(express.static(STATIC_DIR));

app.get('/tts', (req, res) => {
    const type = req.query.type || 'check_in';
    const name = req.query.name || '访客';
    const voice = resolveTtsVoice(req.query.model || req.query.voice);
    const variant = Number.isInteger(Number(req.query.variant))
        ? Math.max(0, Number(req.query.variant))
        : Math.floor(Math.random() * 6);

    if (!fs.existsSync(CACHE_DIR)) {
        fs.mkdirSync(CACHE_DIR, { recursive: true });
    }

    const cacheFile = getTtsCacheFile(name, type, variant, voice);

    if (fs.existsSync(cacheFile)) {
        return res.sendFile(cacheFile);
    }

    execFile(PYTHON_BIN, [TTS_SCRIPT, name, type, cacheFile, String(variant), voice], { cwd: ROOT_DIR }, (err, stdout, stderr) => {
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

app.get('/tts-text', (req, res) => {
    const name = req.query.name || '访客';
    const type = req.query.type || 'check_in';
    const variant = Number.isInteger(Number(req.query.variant))
        ? Math.max(0, Number(req.query.variant))
        : 0;

    execFile(
        PYTHON_BIN,
        [TTS_SCRIPT, name, type, '--print-text', String(variant)],
        { cwd: ROOT_DIR, encoding: 'utf8' },
        (err, stdout, stderr) => {
            if (err) {
                console.error('TTS text error:', stderr || err.message);
                return res.status(500).json({ error: 'TTS text failed' });
            }
            res.json({ text: stdout.trim() });
        }
    );
});

app.get('/tts-manifest', async (req, res) => {
    const manifest = await loadTtsManifest();
    res.json(manifest);
});

app.get('/tts-voices', (req, res) => {
    res.json({
        defaultVoice: TTS_VOICE_BY_MODEL.epsilon,
        byModel: TTS_VOICE_BY_MODEL,
        voices: TTS_VOICES
    });
});

app.get('/tts-prewarm-status', (req, res) => {
    res.json(prewarmStatus);
});

app.get('/avatar-ready', (req, res) => {
    res.json(avatarReadyStatus);
});

app.post('/avatar-ready', (req, res) => {
    avatarReadyStatus.ready = true;
    avatarReadyStatus.model = String((req.body && req.body.model) || '');
    avatarReadyStatus.at = new Date().toISOString();
    res.json({ ok: true, ...avatarReadyStatus });
});

app.post('/employees/sync', async (req, res) => {
    if (!isEmployeeSyncAuthorized(req)) {
        return res.status(401).json({ ok: false, error: 'unauthorized' });
    }

    const names = normalizeEmployeeNames(req.body);
    if (names.length === 0) {
        return res.status(400).json({ ok: false, error: 'name is required' });
    }

    try {
        const manifest = await loadTtsManifest();
        const results = [];
        for (const name of names) {
            const registered = await registerEmployee(name);
            fs.mkdirSync(path.join(EMPLOYEES_DIR, name), { recursive: true });
            const tts = await prewarmEmployeeTts(name, manifest);
            results.push({ name, inserted: registered.inserted, tts });
        }
        res.json({ ok: true, results });
    } catch (err) {
        console.error('Employee sync failed:', err);
        res.status(500).json({ ok: false, error: err.message || String(err) });
    }
});

app.post('/employees/enroll-local', async (req, res) => {
    if (!isEmployeeSyncAuthorized(req)) {
        return res.status(401).json({ ok: false, error: 'unauthorized' });
    }

    const name = String((req.body && req.body.name) || '').trim();
    if (!name) {
        return res.status(400).json({ ok: false, error: 'name is required' });
    }

    try {
        const enrollment = await enrollLocalEmployee(req.body);
        const manifest = await loadTtsManifest();
        const tts = await prewarmEmployeeTts(name, manifest);
        res.json({ ok: true, enrollment, tts });
    } catch (err) {
        console.error('Local enrollment failed:', err);
        res.status(500).json({ ok: false, error: err.message || String(err) });
    }
});

function safeCachePart(value) {
    return String(value || '访客').replace(/[<>:"/\\|?*\x00-\x1F]/g, '_');
}

function resolveTtsVoice(modelOrVoice = '') {
    const key = String(modelOrVoice || '').trim();
    return TTS_VOICE_BY_MODEL[key] || key || TTS_VOICE_BY_MODEL.epsilon;
}

function getTtsCacheFile(name, type, variant, voice = '') {
    return path.join(
        CACHE_DIR,
        `${safeCachePart(name)}_${safeCachePart(type)}_${safeCachePart(resolveTtsVoice(voice))}_${Math.max(0, Number(variant) || 0)}.mp3`
    );
}

function isEmployeeSyncAuthorized(req) {
    if (!EMPLOYEE_SYNC_TOKEN) return true;
    const token = req.get('x-api-key') || String(req.get('authorization') || '').replace(/^Bearer\s+/i, '');
    return token === EMPLOYEE_SYNC_TOKEN;
}

function normalizeEmployeeNames(body) {
    const source = Array.isArray(body && body.names)
        ? body.names
        : [body && body.name];
    return Array.from(new Set(
        source
            .map((name) => String(name || '').trim())
            .filter(Boolean)
    ));
}

function runEmployeeSync(args) {
    return new Promise((resolve, reject) => {
        execFile(
            PYTHON_BIN,
            [EMPLOYEE_SYNC_SCRIPT, ...args],
            { cwd: ROOT_DIR, encoding: 'utf8' },
            (err, stdout, stderr) => {
                let data = null;
                try {
                    data = parseJsonOutput(stdout);
                } catch (parseErr) {
                    reject(new Error(stderr || stdout || parseErr.message));
                    return;
                }
                if (err || data.ok === false) {
                    reject(new Error((data && data.error) || stderr || err.message));
                    return;
                }
                resolve(data);
            }
        );
    });
}

function registerEmployee(name) {
    return runEmployeeSync(['--register', name]);
}

function parseJsonOutput(stdout) {
    const text = String(stdout || '').trim();
    if (!text) return {};
    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
        if (lines[i].startsWith('{') && lines[i].endsWith('}')) {
            return JSON.parse(lines[i]);
        }
    }
    return JSON.parse(text);
}

function runPythonJsonScript(scriptPath, payload) {
    const payloadPath = path.join(
        CACHE_DIR,
        `payload_${Date.now()}_${Math.random().toString(16).slice(2)}.json`
    );
    if (!fs.existsSync(CACHE_DIR)) {
        fs.mkdirSync(CACHE_DIR, { recursive: true });
    }
    fs.writeFileSync(payloadPath, JSON.stringify(payload), 'utf8');

    return new Promise((resolve, reject) => {
        execFile(
            PYTHON_BIN,
            [scriptPath, payloadPath],
            { cwd: ROOT_DIR, encoding: 'utf8' },
            (err, stdout, stderr) => {
                fs.rm(payloadPath, { force: true }, () => {});
                let data = null;
                try {
                    data = parseJsonOutput(stdout);
                } catch (parseErr) {
                    reject(new Error(stderr || stdout || parseErr.message));
                    return;
                }
                if (err || data.ok === false) {
                    reject(new Error((data && data.error) || stderr || err.message));
                    return;
                }
                resolve(data);
            }
        );
    });
}

function enrollLocalEmployee(payload) {
    return runPythonJsonScript(LOCAL_ENROLL_SCRIPT, payload);
}

async function listDbEmployeeNames() {
    try {
        const data = await runEmployeeSync(['--list']);
        return Array.isArray(data.names) ? data.names : [];
    } catch (err) {
        console.error('Employee list from DB failed:', err.message || err);
        return [];
    }
}

async function listTtsNames() {
    const names = new Set(['访客']);
    if (!fs.existsSync(EMPLOYEES_DIR)) {
        return Array.from(new Set([...names, ...(await listDbEmployeeNames())]));
    }

    for (const entry of fs.readdirSync(EMPLOYEES_DIR, { withFileTypes: true })) {
        if (entry.isDirectory()) {
            names.add(entry.name);
        }
    }

    for (const name of await listDbEmployeeNames()) {
        names.add(name);
    }
    return Array.from(names);
}

function loadTtsManifest() {
    return new Promise((resolve) => {
        execFile(
            PYTHON_BIN,
            [TTS_SCRIPT, '--print-manifest'],
            { cwd: ROOT_DIR, encoding: 'utf8' },
            (err, stdout, stderr) => {
                if (err) {
                    console.error('TTS manifest failed:', stderr || err.message);
                    resolve({});
                    return;
                }
                try {
                    resolve(JSON.parse(stdout));
                } catch (parseErr) {
                    console.error('TTS manifest parse failed:', parseErr.message);
                    resolve({});
                }
            }
        );
    });
}

function generateTtsFile(name, type, variant, voice = '') {
    voice = resolveTtsVoice(voice);
    const cacheFile = getTtsCacheFile(name, type, variant, voice);
    if (fs.existsSync(cacheFile) && fs.statSync(cacheFile).size > 0) {
        return Promise.resolve('cached');
    }

    return generateTtsFileWithRetry(name, type, variant, voice, cacheFile, 3);
}

function generateTtsFileWithRetry(name, type, variant, voice, cacheFile, attempts) {
    return new Promise((resolve) => {
        let attempt = 0;

        function run() {
            attempt += 1;
            execFile(
                PYTHON_BIN,
                [TTS_SCRIPT, name, type, cacheFile, String(variant), voice],
                { cwd: ROOT_DIR },
                (err, stdout, stderr) => {
                    if (!err && fs.existsSync(cacheFile) && fs.statSync(cacheFile).size > 0) {
                        resolve('created');
                        return;
                    }

                    if (attempt < attempts) {
                        setTimeout(run, 800 * attempt);
                        return;
                    }

                    console.error(
                        `TTS prewarm failed: ${name}/${type}/${voice || 'default'}/${variant}`,
                        stderr || (err && err.message) || 'file not created'
                    );
                    resolve('failed');
                }
            );
        }

        run();
    });
}

async function prewarmEmployeeTts(name, manifest) {
    let generated = 0;
    let skipped = 0;
    let failed = 0;
    const files = NAMED_TTS_TYPES.flatMap((type) => {
        const variantCount = Math.max(1, manifest[type] || 1);
        return TTS_VOICES.flatMap((voice) => {
            return Array.from({ length: variantCount }, (_, variant) => ({
                name,
                type,
                voice,
                variant
            }));
        });
    });

    let cursor = 0;
    async function worker() {
        while (cursor < files.length) {
            const file = files[cursor++];
            try {
                const status = await generateTtsFile(file.name, file.type, file.variant, file.voice);
                if (status === 'created') {
                    generated += 1;
                } else if (status === 'cached') {
                    skipped += 1;
                } else {
                    failed += 1;
                }
            } catch (err) {
                failed += 1;
                console.error(`Employee TTS failed: ${file.name}/${file.type}/${file.voice}/${file.variant}`, err.message || err);
            }
        }
    }

    await Promise.all(
        Array.from({ length: Math.min(TTS_PREWARM_CONCURRENCY, files.length) }, worker)
    );

    if (failed > 0) {
        throw new Error(`TTS failed for ${failed} files`);
    }

    return { generated, skipped, total: files.length };
}

async function prewarmTtsCache() {
    if (!fs.existsSync(CACHE_DIR)) {
        fs.mkdirSync(CACHE_DIR, { recursive: true });
    }

    prewarmStatus.running = true;
    prewarmStatus.complete = false;
    prewarmStatus.generated = 0;
    prewarmStatus.skipped = 0;
    prewarmStatus.total = 0;
    prewarmStatus.error = '';

    const names = await listTtsNames();
    const manifest = await loadTtsManifest();
    let generated = 0;
    let skipped = 0;

    const jobs = [
        ...NAMED_TTS_TYPES.flatMap((type) => names.flatMap((name) => TTS_VOICES.map((voice) => ({ name, type, voice })))),
        ...ANONYMOUS_TTS_TYPES.flatMap((type) => TTS_VOICES.map((voice) => ({ name: '访客', type, voice })))
    ];

    prewarmStatus.total = jobs.reduce((sum, job) => {
        return sum + Math.max(1, manifest[job.type] || 1);
    }, 0);

    console.log(`TTS prewarm started: ${jobs.length} name/type groups, ${prewarmStatus.total} files`);

    const files = jobs.flatMap((job) => {
        const variantCount = Math.max(1, manifest[job.type] || 1);
        return Array.from({ length: variantCount }, (_, variant) => ({ ...job, variant }));
    });
    let cursor = 0;

    async function worker() {
        while (cursor < files.length) {
            const file = files[cursor++];
            const status = await generateTtsFile(file.name, file.type, file.variant, file.voice);
            if (status === 'created') {
                generated += 1;
            } else if (status === 'cached') {
                skipped += 1;
            } else {
                prewarmStatus.error = `TTS failed: ${file.name}/${file.type}/${file.voice}/${file.variant}`;
                throw new Error(prewarmStatus.error);
            }
            prewarmStatus.generated = generated;
            prewarmStatus.skipped = skipped;
        }
    }

    await Promise.all(
        Array.from({ length: Math.min(TTS_PREWARM_CONCURRENCY, files.length) }, worker)
    );

    prewarmStatus.running = false;
    prewarmStatus.complete = true;
    console.log(`TTS prewarm complete: generated=${generated}, cached/failed=${skipped}`);
}

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
    if (process.env.ENABLE_TTS_PREWARM === '1') {
        prewarmTtsCache().catch((err) => {
            prewarmStatus.running = false;
            prewarmStatus.complete = true;
            prewarmStatus.error = err.message || String(err);
            console.error('TTS prewarm error:', err);
        });
    } else {
        prewarmStatus.complete = true;
        prewarmStatus.error = '';
        console.log('TTS prewarm skipped. Set ENABLE_TTS_PREWARM=1 to enable legacy full-cache generation.');
    }
});

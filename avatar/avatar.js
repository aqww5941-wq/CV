(function () {
    const { Live2DModel } = PIXI.live2d;
    const canvas = document.getElementById('canvas');
    const statusEl = document.getElementById('status');
    const loadingEl = document.getElementById('loading');

    let app, model = null;
    let ws = null;
    let audio = null;
    let idleState = 'idle';
    let idleTimer = null;
    let microTimer = null;
    let fidgetTimer = null;

    const BEHAVIORS = {
        greet: {
            status: '打招呼中...',
            expression: 'Smile',
            motions: [
                ['Tap', 0],
                ['Tap', 1],
                ['Tap', 2]
            ],
            tts: 'check_in',
            idleDelay: 4200
        },
        wave: {
            status: '招手中...',
            expression: 'Smile',
            motions: [
                ['Tap', 0],
                ['Tap', 1],
                ['Tap', 2],
                ['Tap', 3]
            ],
            idleDelay: 3600
        },
        bye: {
            status: '说再见...',
            expression: 'Normal',
            motions: [
                ['Flick', 0],
                ['Flick', 1]
            ],
            tts: 'check_out',
            idleDelay: 4200
        },
        check_in: {
            expression: 'Smile',
            motions: [
                ['Tap', 0],
                ['Tap', 1],
                ['Tap', 2],
                ['Tap', 3]
            ],
            tts: 'check_in',
            idleDelay: 4600
        },
        first_time: {
            expression: 'Blushing',
            motions: [
                ['Tap', 0],
                ['FlickUp', 0]
            ],
            tts: 'first_time',
            idleDelay: 5200
        },
        returning: {
            expression: 'Smile',
            motions: [
                ['Tap', 1],
                ['Tap', 3],
                ['Flick3', 0]
            ],
            tts: 'returning',
            idleDelay: 5200
        },
        check_out: {
            expression: 'Normal',
            motions: [
                ['Flick', 0],
                ['Flick', 1]
            ],
            tts: 'check_out',
            idleDelay: 4600
        },
        stranger: {
            expression: 'Surprised',
            motions: [
                ['FlickUp', 0],
                ['FlickUp', 1]
            ],
            tts: 'stranger',
            idleDelay: 4600
        },
        repeat: {
            expression: 'Blushing',
            motions: [
                ['Shake', 0],
                ['Shake', 1]
            ],
            tts: 'repeat',
            idleDelay: 4600
        },
        attention: {
            expression: 'Smile',
            motions: [
                ['Tap', 0],
                ['Tap', 2]
            ],
            idleDelay: 3600
        },
        idle_long: {
            expression: 'Sad',
            motions: [
                ['FlickDown', 0],
                ['FlickDown', 1]
            ],
            tts: 'idle_long',
            idleDelay: 5600
        },
        crowd: {
            expression: 'Surprised',
            motions: [
                ['Flick3', 0],
                ['Flick3', 1]
            ],
            tts: 'crowd',
            idleDelay: 5600
        }
    };

    function showStatus(text) {
        statusEl.textContent = text;
    }

    function fitModel() {
        if (!model) return;
        const w = app.screen.width;
        const h = app.screen.height;
        model.anchor.set(0.5, 0.5);
        const scale = Math.min(w / 1200, h / 2000) * 0.8;
        model.scale.set(scale);
        model.position.set(w / 2, h * 0.52);
    }

    function resize() {
        const rect = canvas.getBoundingClientRect();
        app.renderer.resize(rect.width, rect.height);
        fitModel();
    }

    async function playMotion(group, index) {
        if (!model) return;
        try {
            await model.motion(group, index);
        } catch (e) {
            console.error('Motion error:', group, e);
        }
    }

    function setExpression(name) {
        if (!model) return;
        try {
            model.expression(name);
            showStatus('表情: ' + name);
            document.querySelectorAll('#expression-buttons button').forEach(function (button) {
                button.classList.toggle('active', button.dataset.name === name);
            });
        } catch (e) {
            console.error('Expression error:', name, e);
        }
    }

    function playTTS(name, type) {
        if (audio) {
            audio.pause();
            audio = null;
        }

        var variant = Math.floor(Math.random() * 6);
        audio = new Audio('/tts?name=' + encodeURIComponent(name) + '&type=' + type + '&variant=' + variant);
        audio.play().catch(function () { });
    }

    function pick(items) {
        return items[Math.floor(Math.random() * items.length)];
    }

    function runBehavior(name, options) {
        if (!model) return;

        options = options || {};
        var behavior = BEHAVIORS[name];
        if (!behavior) return;

        idleState = name;
        stopIdleCycle();
        clearIdleTimer();

        setExpression(behavior.expression || 'Normal');

        if (behavior.motions && behavior.motions.length > 0) {
            var motion = pick(behavior.motions);
            setTimeout(function () {
                playMotion(motion[0], motion[1]);
            }, 80);
        }

        if (behavior.tts && options.silent !== true) {
            playTTS(options.name || '访客', options.tts || behavior.tts);
        }

        showStatus(options.status || behavior.status || '执行动作中');
        scheduleIdle(options.idleDelay || behavior.idleDelay || 4000);
    }

    function doAction(action) {
        switch (action) {
            case 'wave':
                runBehavior('wave', { silent: true });
                break;
            case 'greet':
                runBehavior('greet', { name: '访客' });
                break;
            case 'bye':
                runBehavior('bye', { name: '访客' });
                break;
            case 'surprise':
                runBehavior('stranger', { name: '访客', silent: true, status: '惊讶中...' });
                break;
            case 'smile':
                setExpression('Smile');
                break;
        }
    }

    function buildDebugPanel() {
        if (!model) return;

        var expressions = [
            'Angry.exp3.json', 'Blushing.exp3.json',
            'f01.exp3.json', 'f02.exp3.json',
            'Normal.exp3.json', 'Sad.exp3.json',
            'Smile.exp3.json', 'Surprised.exp3.json'
        ];

        var exprLabels = {
            'Angry.exp3.json': '生气',
            'Blushing.exp3.json': '害羞',
            'f01.exp3.json': '表情01',
            'f02.exp3.json': '表情02',
            'Normal.exp3.json': '正常',
            'Sad.exp3.json': '悲伤',
            'Smile.exp3.json': '微笑',
            'Surprised.exp3.json': '惊讶'
        };

        var motions = {
            '待机 Idle': 'Idle',
            '轻点 Tap': 'Tap',
            '轻弹 Flick': 'Flick',
            '上弹 FlickUp': 'FlickUp',
            '下弹 FlickDown': 'FlickDown',
            '三连弹 Flick3': 'Flick3',
            '摇头 Shake': 'Shake'
        };

        var motionCounts = {
            'Idle': 1, 'Tap': 4, 'Flick': 2,
            'FlickUp': 2, 'FlickDown': 2, 'Flick3': 2, 'Shake': 2
        };

        var exprContainer = document.getElementById('expression-buttons');
        var motionContainer = document.getElementById('motion-buttons');

        expressions.forEach(function (name) {
            var button = document.createElement('button');
            button.textContent = exprLabels[name] || name;
            button.dataset.name = name;
            button.addEventListener('click', function () {
                setExpression(name);
            });
            exprContainer.appendChild(button);
        });

        for (var label in motions) {
            var internalName = motions[label];
            var count = motionCounts[internalName] || 1;
            for (var i = 0; i < count; i++) {
                (function (motionLabel, name, index) {
                    var button = document.createElement('button');
                    button.textContent = motionLabel + (count > 1 ? '[' + index + ']' : '');
                    button.addEventListener('click', function () {
                        playMotion(name, index);
                        showStatus('动作: ' + motionLabel);
                    });
                    motionContainer.appendChild(button);
                })(label, internalName, i);
            }
        }
    }

    function connectWebSocket() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = protocol + '//' + location.host;
        ws = new WebSocket(wsUrl);

        ws.onopen = function () {
            console.log('WebSocket connected');
        };

        ws.onmessage = function (event) {
            try {
                const msg = JSON.parse(event.data);
                handleEvent(msg);
            } catch (e) {
                console.error('WS message error:', e);
            }
        };

        ws.onclose = function () {
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = function (err) {
            console.error('WebSocket error:', err);
        };
    }

    function handleEvent(msg) {
        clearIdleTimer();
        switch (msg.type) {
            case 'check_in':
                if (msg.is_first) {
                    runBehavior('first_time', { name: msg.name || '访客', status: (msg.name || '访客') + ' 首次签到' });
                } else if (msg.is_returning) {
                    runBehavior('returning', { name: msg.name || '访客', status: (msg.name || '访客') + ' 回访签到' });
                } else {
                    runBehavior('check_in', { name: msg.name || '访客', status: (msg.name || '访客') + ' 签到' });
                }
                break;
            case 'check_out':
                runBehavior('check_out', { name: msg.name || '访客', status: (msg.name || '访客') + ' 签退' });
                break;
            case 'stranger':
                runBehavior('stranger', { name: '', status: '检测到陌生人' });
                break;
            case 'repeat':
                runBehavior('repeat', { name: msg.name || '访客', status: (msg.name || '访客') + ' 重复签到' });
                break;
            case 'attention':
                if (idleState === 'idle') {
                    runBehavior('attention', { silent: true, status: '有人来了...' });
                }
                break;
            case 'idle_long':
                runBehavior('idle_long', { name: '', status: '长时间无人' });
                break;
            case 'crowd':
                runBehavior('crowd', { name: '', status: '多人出现! (' + (msg.count || '') + '人)' });
                break;
        }
    }

    function clearIdleTimer() {
        if (idleTimer) {
            clearTimeout(idleTimer);
            idleTimer = null;
        }
    }

    function scheduleIdle(delay) {
        clearIdleTimer();
        idleTimer = setTimeout(enterIdle, delay || 3000);
    }

    function enterIdle() {
        idleState = 'idle';
        setExpression('Normal');
        playMotion('Idle', 0);
        showStatus('待机中');
        startIdleCycle();
    }

    function startIdleCycle() {
        stopIdleCycle();
        scheduleMicroExpression();
        scheduleFidget();
    }

    function stopIdleCycle() {
        if (microTimer) {
            clearTimeout(microTimer);
            microTimer = null;
        }
        if (fidgetTimer) {
            clearTimeout(fidgetTimer);
            fidgetTimer = null;
        }
    }

    function scheduleMicroExpression() {
        if (idleState !== 'idle') return;

        var delay = 8000 + Math.random() * 7000;
        microTimer = setTimeout(function () {
            if (idleState !== 'idle') return;

            var exps = ['Normal', 'f01', 'f02'];
            var exp = exps[Math.floor(Math.random() * exps.length)];
            setExpression(exp + '.exp3.json');
            setTimeout(function () {
                if (idleState === 'idle') setExpression('Normal.exp3.json');
            }, 2000);
            scheduleMicroExpression();
        }, delay);
    }

    function scheduleFidget() {
        if (idleState !== 'idle') return;

        var delay = 30000 + Math.random() * 30000;
        fidgetTimer = setTimeout(function () {
            if (idleState !== 'idle') return;

            var motions = [
                function () { playMotion('Flick', Math.floor(Math.random() * 2)); },
                function () { playMotion('FlickUp', 0); },
                function () { playMotion('FlickDown', 0); }
            ];
            motions[Math.floor(Math.random() * motions.length)]();
            scheduleFidget();
        }, delay);
    }

    async function init() {
        try {
            const rect = canvas.getBoundingClientRect();
            const isDisplayMode = new URLSearchParams(location.search).has('display');

            if (isDisplayMode) {
                document.body.classList.add('display-mode');
            }

            app = new PIXI.Application({
                view: canvas,
                width: rect.width,
                height: rect.height,
                backgroundColor: 0x000000,
                backgroundAlpha: 0,
                antialias: true,
                resolution: window.devicePixelRatio || 1,
                autoDensity: true
            });

            window.addEventListener('resize', resize);

            model = await Live2DModel.from('models/Epsilon/Epsilon.model3.json');
            app.stage.addChild(model);
            fitModel();

            setExpression('Normal');
            playMotion('Idle', 0);
            enterIdle();
            buildDebugPanel();

            loadingEl.style.opacity = '0';
            setTimeout(function () {
                loadingEl.style.display = 'none';
            }, 500);

            canvas.addEventListener('click', function (e) {
                const rect = canvas.getBoundingClientRect();
                const y = (e.clientY - rect.top) / rect.height;
                if (y < 0.5) {
                    playMotion('Tap', Math.floor(Math.random() * 4));
                } else {
                    playMotion('Flick', Math.floor(Math.random() * 2));
                }
            });

            connectWebSocket();
        } catch (err) {
            console.error('Init failed:', err);
            loadingEl.innerHTML = '<div>加载失败</div><div style="font-size:14px;margin-top:8px;color:#ff6b6b">' + err.message + '</div>';
        }
    }

    window.doAction = doAction;
    window.setExpression = setExpression;
    window.playMotion = playMotion;

    init();
})();

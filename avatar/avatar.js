(function () {
    const { Live2DModel } = PIXI.live2d;
    const canvas = document.getElementById('canvas');
    const statusEl = document.getElementById('status');
    const loadingEl = document.getElementById('loading');
    const subtitleEl = document.getElementById('subtitle');
    const modelSwitcherEl = document.getElementById('model-switcher');

    let app, model = null;
    let currentModelKey = 'epsilon';
    let currentModelConfig = null;
    let ws = null;
    let audio = null;
    let idleState = 'idle';
    let idleTimer = null;
    let microTimer = null;
    let fidgetTimer = null;
    let subtitleTimer = null;
    let ttsManifest = {};
    let ttsVoiceByModel = {};
    let audioUnlocked = false;
    let audioContext = null;
    let lipAnalyser = null;
    let lipData = null;
    let lipFrame = null;
    let lipValue = 0;
    let mouthOpenValue = 0;
    let mouthBoundModel = null;
    let externalLipTarget = 0;
    let externalLipNextChangeAt = 0;
    let externalLipPauseUntil = 0;
    let externalLipNextPauseAt = 0;
    let lipStartedAt = 0;
    let ttsRequestId = 0;
    let ttsMutedUntil = 0;
    let isSwitchingModel = false;
    let queuedModelKey = null;
    let statusMode = 'idle';
    let lastBehaviorName = '';
    let lastBehaviorAt = 0;

    const MODEL_REGISTRY = {
        epsilon: {
            label: 'Epsilon',
            path: 'models/Epsilon/Epsilon.model3.json',
            voice: 'zh-CN-XiaoyiNeural',
            fit: { width: 1200, height: 2000, scale: 0.8, y: 0.52 },
            expressions: {
                Angry: 'Angry.exp3.json',
                Blushing: 'Blushing.exp3.json',
                f01: 'f01.exp3.json',
                f02: 'f02.exp3.json',
                Normal: 'Normal.exp3.json',
                Sad: 'Sad.exp3.json',
                Smile: 'Smile.exp3.json',
                Surprised: 'Surprised.exp3.json'
            },
            expressionButtons: ['Angry', 'Blushing', 'f01', 'f02', 'Normal', 'Sad', 'Smile', 'Surprised'],
            motionCounts: {
                Idle: 1,
                Tap: 4,
                Flick: 2,
                FlickUp: 2,
                FlickDown: 2,
                Flick3: 2,
                Shake: 2
            }
        },
        chitose: {
            label: 'Chitose 男',
            path: 'models/chitose_ja/runtime/chitose.model3.json',
            voice: 'zh-TW-YunJheNeural',
            fit: { width: 1150, height: 1900, scale: 0.86, y: 0.54 },
            expressions: {
                Angry: 'Angry.exp3.json',
                Blushing: 'Blushing.exp3.json',
                f01: 'f01.exp3.json',
                f02: 'f01.exp3.json',
                Normal: 'Normal.exp3.json',
                Sad: 'Sad.exp3.json',
                Smile: 'Smile.exp3.json',
                Surprised: 'Surprised.exp3.json'
            },
            expressionButtons: ['Angry', 'Blushing', 'f01', 'Normal', 'Sad', 'Smile', 'Surprised'],
            motionCounts: {
                Idle: 1,
                Tap: 2,
                Flick: 1
            },
            motionMap: {
                Idle: [['Idle', 0]],
                Tap: [['Tap', 0], ['Tap', 1]],
                Flick: [['Flick', 0]],
                FlickUp: [['Tap', 0], ['Tap', 1]],
                FlickDown: [['Tap', 1], ['Idle', 0]],
                Flick3: [['Tap', 0], ['Flick', 0]],
                Shake: [['Tap', 1], ['Flick', 0]]
            }
        },
        haruGreeter: {
            label: 'Haru',
            path: 'models/haru_greeter_ja/runtime/haru_greeter_t05.model3.json',
            voice: 'zh-CN-XiaoxiaoNeural',
            fit: { width: 1200, height: 1900, scale: 0.52, y: 0.62 },
            expressions: {},
            expressionButtons: [],
            motionCounts: {
                '': 27
            },
            motionIndexLabels: {
                '': {
                    5: '震惊',
                    7: '害羞',
                    8: '害羞',
                    10: '害羞',
                    12: '害羞',
                    13: '震惊',
                    14: '震惊',
                    16: '害羞',
                    17: '害羞',
                    18: '害羞',
                    19: '害羞',
                    20: '失落',
                    21: '开心',
                    22: '开心',
                    23: '搞怪',
                    24: '失落',
                    25: '震惊',
                    26: '震惊'
                }
            },
            motionMap: {
                Idle: [['', 0]],
                Tap: [['', 1], ['', 2], ['', 3], ['', 4], ['', 5]],
                Flick: [['', 6], ['', 7], ['', 8]],
                FlickUp: [['', 9], ['', 10], ['', 11]],
                FlickDown: [['', 12], ['', 13], ['', 14]],
                Flick3: [['', 15], ['', 16], ['', 17]],
                Shake: [['', 18], ['', 19], ['', 20]]
            }
        },
        haru: {
            label: 'Hiyori',
            path: 'models/hiyori_zh-Hans/runtime/hiyori_pro_t11.model3.json',
            voice: 'zh-CN-XiaoyiNeural',
            fit: { width: 1200, height: 2100, scale: 0.5, y: 0.55 },
            expressions: {},
            expressionButtons: [],
            motionCounts: {
                Idle: 3,
                Tap: 2,
                Flick: 1,
                FlickUp: 1,
                FlickDown: 1,
                'Tap@Body': 1,
                'Flick@Body': 1
            },
            motionMap: {
                Idle: [['Idle', 0], ['Idle', 1], ['Idle', 2]],
                Tap: [['Tap', 0], ['Tap', 1], ['Tap@Body', 0]],
                Flick: [['Flick', 0], ['Flick@Body', 0]],
                FlickUp: [['FlickUp', 0], ['Tap', 0]],
                FlickDown: [['FlickDown', 0], ['Idle', 1]],
                Flick3: [['Tap', 0], ['Tap', 1], ['Flick@Body', 0]],
                Shake: [['Flick', 0], ['FlickDown', 0]]
            }
        },
        natori: {
            label: 'Natori 男',
            path: 'models/natori_zh-Hans/runtime/natori_pro_t06.model3.json',
            voice: 'zh-TW-YunJheNeural',
            fit: { width: 1200, height: 2100, scale: 0.42, y: 0.68 },
            expressions: {
                Angry: 'Angry',
                Blushing: 'Blushing',
                f01: 'exp_01',
                f02: 'exp_02',
                Normal: 'Normal',
                Sad: 'Sad',
                Smile: 'Smile',
                Surprised: 'Surprised'
            },
            expressionButtons: ['Angry', 'Blushing', 'exp_01', 'exp_02', 'exp_03', 'exp_04', 'exp_05', 'Normal', 'Sad', 'Smile', 'Surprised'],
            motionCounts: {
                Idle: 3,
                Tap: 1,
                'FlickUp@Head': 1,
                'Flick@Body': 1,
                'FlickDown@Body': 1,
                'Tap@Head': 1
            },
            motionMap: {
                Idle: [['Idle', 0], ['Idle', 1], ['Idle', 2]],
                Tap: [['Tap', 0], ['Tap@Head', 0]],
                Flick: [['Flick@Body', 0]],
                FlickUp: [['FlickUp@Head', 0], ['Tap@Head', 0]],
                FlickDown: [['FlickDown@Body', 0]],
                Flick3: [['Tap', 0], ['Flick@Body', 0]],
                Shake: [['FlickDown@Body', 0], ['Flick@Body', 0]]
            }
        }
    };

    const DEFAULT_MODEL_KEY = 'epsilon';
    const DEFAULT_TTS_VOICE = 'zh-CN-XiaoxiaoNeural';
    const MODEL_LOAD_ATTEMPTS = 3;

    const BEHAVIORS = {
        greet: {
            status: '打招呼中',
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
            status: '招手中',
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
            status: '说再见中',
            expression: 'Normal',
            motions: [
                ['Flick', 0],
                ['Flick', 1]
            ],
            tts: 'check_out',
            idleDelay: 4200
        },
        check_in: {
            status: '打招呼中',
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
            status: '欢迎中',
            expression: 'Blushing',
            motions: [
                ['Tap', 0],
                ['FlickUp', 0]
            ],
            tts: 'first_time',
            idleDelay: 5200
        },
        returning: {
            status: '欢迎中',
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
            status: '告别中',
            expression: 'Normal',
            motions: [
                ['Flick', 0],
                ['Flick', 1]
            ],
            tts: 'check_out',
            idleDelay: 4600
        },
        stranger: {
            status: '好奇观察中',
            expression: 'Surprised',
            motions: [
                ['FlickUp', 0],
                ['FlickUp', 1]
            ],
            tts: 'stranger',
            idleDelay: 4600
        },
        repeat: {
            status: '互动中',
            expression: 'Blushing',
            motions: [
                ['Shake', 0],
                ['Shake', 1]
            ],
            tts: 'repeat',
            idleDelay: 4600
        },
        attention: {
            status: '注意到有人',
            expression: 'Smile',
            motions: [
                ['Tap', 0],
                ['Tap', 2]
            ],
            idleDelay: 3600
        },
        idle_long: {
            status: '想念中',
            expression: 'Sad',
            motions: [
                ['FlickDown', 0],
                ['FlickDown', 1]
            ],
            tts: 'idle_long',
            idleDelay: 5600
        },
        crowd: {
            status: '热闹接待中',
            expression: 'Surprised',
            motions: [
                ['Flick3', 0],
                ['Flick3', 1]
            ],
            tts: 'crowd',
            idleDelay: 5600
        }
    };

    const MODEL_BEHAVIOR_OVERRIDES = {
        epsilon: {
            greet: {
                expression: ['Normal', 'Blushing', 'Smile'],
                motions: [['Flick3', 0], ['Flick3', 1], ['Shake', 0], ['Shake', 1]]
            },
            check_in: {
                expression: ['Normal', 'Blushing', 'Smile'],
                motions: [['Flick3', 0], ['Flick3', 1], ['Shake', 0], ['Shake', 1]]
            },
            first_time: {
                expression: ['Normal', 'Blushing', 'Smile'],
                motions: [['Flick3', 0], ['Flick3', 1]]
            },
            returning: {
                expression: ['Normal', 'Blushing', 'Smile'],
                motions: [['Flick3', 0], ['Flick3', 1], ['Shake', 0], ['Shake', 1]]
            },
            check_out: {
                expression: ['Normal', 'Blushing', 'Smile'],
                motions: [['Flick3', 0], ['Flick3', 1], ['Shake', 0], ['Shake', 1]]
            },
            stranger: {
                expression: ['Normal', 'Blushing', 'Smile'],
                motions: [['Flick3', 0], ['Flick3', 1], ['Shake', 0], ['Shake', 1]]
            },
            repeat: {
                expressionPool: 'all',
                motionPool: 'visible'
            }
        },
        haruGreeter: {
            greet: {
                motions: [['', 21], ['', 22]]
            },
            check_in: {
                motions: [['', 21], ['', 22]]
            },
            first_time: {
                motions: [['', 21], ['', 22]]
            },
            returning: {
                motions: [['', 21], ['', 22]]
            },
            check_out: {
                motions: [['', 21], ['', 22]]
            },
            stranger: {
                motions: [['', 5], ['', 13], ['', 14], ['', 25], ['', 26]]
            },
            repeat: {
                motions: [['', 7], ['', 8], ['', 10], ['', 12], ['', 16], ['', 17], ['', 18], ['', 19], ['', 5], ['', 13], ['', 14], ['', 20], ['', 23], ['', 24], ['', 25], ['', 26]]
            },
            attention: {
                motions: [['', 7], ['', 8], ['', 10], ['', 12], ['', 16], ['', 17], ['', 18], ['', 19], ['', 21], ['', 22]]
            },
            idle_long: {
                motions: [['', 3], ['', 4], ['', 20], ['', 24]]
            },
            crowd: {
                motions: [['', 5], ['', 13], ['', 14], ['', 25], ['', 26]]
            }
        },
        haru: {
            greet: {
                motions: [['Tap', 0], ['Tap', 1], ['Flick', 0]]
            },
            check_in: {
                motions: [['Tap', 0], ['Tap', 1], ['Flick', 0]]
            },
            first_time: {
                motions: [['Tap', 0], ['Tap', 1], ['Flick', 0]]
            },
            returning: {
                motions: [['Tap', 0], ['Tap', 1], ['Flick', 0]]
            },
            check_out: {
                motions: [['Tap', 0], ['Tap', 1], ['Flick', 0]]
            },
            stranger: {
                motions: [['Tap', 0], ['Tap', 1], ['Flick', 0]]
            },
            repeat: {
                motionPool: 'visible'
            },
            attention: {
                motionPool: 'visible'
            },
            idle_long: {
                motionPool: 'visible'
            },
            crowd: {
                motionPool: 'visible'
            }
        }
    };

    function showStatus(text, mode) {
        mode = mode || 'activity';
        if (statusMode === 'speech' && mode !== 'speech') {
            return;
        }
        statusMode = mode;
        statusEl.textContent = text;
    }

    function fitModel() {
        if (!model) return;
        const w = app.screen.width;
        const h = app.screen.height;
        const fit = (currentModelConfig && currentModelConfig.fit) || {};
        model.anchor.set(0.5, 0.5);
        const scale = Math.min(w / (fit.width || 1200), h / (fit.height || 2000)) * (fit.scale || 0.8);
        model.scale.set(scale);
        model.position.set(w / 2, h * (fit.y || 0.52));
    }

    function resize() {
        const rect = canvas.getBoundingClientRect();
        app.renderer.resize(rect.width, rect.height);
        fitModel();
    }

    async function playMotion(group, index) {
        if (!model) return;
        var motion = resolveMotion(group, index);
        try {
            var priority = PIXI.live2d.MotionPriority
                ? PIXI.live2d.MotionPriority.FORCE
                : 3;
            var started = await model.motion(motion[0], motion[1], priority);
            if (!started) {
                console.warn('Motion rejected:', motion[0], motion[1]);
            }
        } catch (e) {
            console.error('Motion error:', motion[0], motion[1], e);
        }
    }

    function setExpression(name) {
        if (!model) return;
        var expression = resolveExpression(name);
        if (!expression) return;
        try {
            model.expression(expression);
            showStatus('表情：' + getExpressionLabel(expression), 'activity');
            document.querySelectorAll('#expression-buttons button').forEach(function (button) {
                button.classList.toggle('active', button.dataset.name === expression);
            });
        } catch (e) {
            console.error('Expression error:', expression, e);
        }
    }

    function normalizeExpressionName(name) {
        return String(name || '').replace(/\.exp3\.json$/i, '');
    }

    function resolveExpression(name) {
        var config = currentModelConfig || {};
        var expressions = config.expressions || {};
        var normalized = normalizeExpressionName(name);
        if (Object.prototype.hasOwnProperty.call(expressions, normalized)) {
            return expressions[normalized];
        }
        if (Object.prototype.hasOwnProperty.call(expressions, name)) {
            return expressions[name];
        }
        return expressions.Normal || null;
    }

    function getExpressionLabel(name) {
        var labels = {
            Angry: '生气',
            Blushing: '害羞',
            f01: '表情01',
            f02: '表情02',
            exp_01: '表情01',
            exp_02: '表情02',
            exp_03: '表情03',
            exp_04: '表情04',
            exp_05: '表情05',
            Normal: '正常',
            Sad: '悲伤',
            Smile: '微笑',
            Surprised: '惊讶'
        };
        var normalized = normalizeExpressionName(name);
        return labels[normalized] || normalized || name;
    }

    function resolveMotion(group, index) {
        var config = currentModelConfig || {};
        var map = config.motionMap || {};
        var mapped = map[group];
        if (mapped && mapped.length > 0) {
            return mapped[Math.abs(index || 0) % mapped.length];
        }

        var count = config.motionCounts && config.motionCounts[group];
        if (count) {
            return [group, Math.abs(index || 0) % count];
        }

        var idle = map.Idle && map.Idle[0];
        return idle || ['Idle', 0];
    }

    function playTTS(name, type) {
        if (performance.now() < ttsMutedUntil) return;
        var requestId = ++ttsRequestId;
        if (audio) {
            audio.pause();
            audio = null;
        }
        stopLipSync();

        var variantCount = Math.max(1, ttsManifest[type] || 1);
        var variant = Math.floor(Math.random() * variantCount);
        var subtitleText = '';
        var audioStarted = false;

        loadSubtitleText(name, type, variant).then(function (text) {
            subtitleText = text;
            if (audioStarted && subtitleText) {
                showStatus(subtitleText, 'speech');
            }
        });

        var modelKey = currentModelKey || DEFAULT_MODEL_KEY;
        var audioUrl = '/tts?name=' + encodeURIComponent(name || '访客') + '&type=' + type + '&variant=' + variant + '&model=' + encodeURIComponent(modelKey);

        fetch(audioUrl)
            .then(function (res) {
                if (!res.ok) {
                    throw new Error('TTS HTTP ' + res.status);
                }
                return res.blob();
            })
            .then(function (blob) {
                if (requestId !== ttsRequestId) return;
                var objectUrl = URL.createObjectURL(blob);
                audio = new Audio(objectUrl);
                audio.addEventListener('playing', function () {
                    audioStarted = true;
                    startLipSync(audio);
                    if (subtitleText) {
                        showStatus(subtitleText, 'speech');
                    }
                });
                audio.addEventListener('ended', function () {
                    URL.revokeObjectURL(objectUrl);
                    statusMode = 'idle';
                    stopLipSync();
                    hideSubtitle();
                });
                audio.addEventListener('error', function () {
                    URL.revokeObjectURL(objectUrl);
                    statusMode = 'idle';
                    stopLipSync();
                    hideSubtitle();
                });
                return audio.play();
            })
            .catch(function (err) {
                if (requestId !== ttsRequestId) return;
                statusMode = 'idle';
                stopLipSync();
                console.error('TTS play failed:', err);
                hideSubtitle();
            });
    }

    function unlockAudio() {
        if (audioUnlocked) return;
        audioUnlocked = true;
        var silentAudio = new Audio();
        silentAudio.muted = true;
        silentAudio.play().catch(function () { });
        ensureAudioContext();
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume().catch(function () { });
        }
    }

    function ensureAudioContext() {
        if (!audioContext) {
            var AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                audioContext = new AudioContextClass();
            }
        }
        return audioContext;
    }

    function startLipSync(audioElement) {
        if (!model || !audioElement) return;
        lipStartedAt = performance.now();
        setMouthOpen(0.28);

        var ctx = ensureAudioContext();
        if (!ctx) {
            startFallbackLipSync(audioElement);
            return;
        }

        try {
            if (ctx.state === 'suspended') {
                ctx.resume().catch(function () { });
            }
            var source = ctx.createMediaElementSource(audioElement);
            lipAnalyser = ctx.createAnalyser();
            lipAnalyser.fftSize = 256;
            lipData = new Uint8Array(lipAnalyser.fftSize);
            source.connect(lipAnalyser);
            lipAnalyser.connect(ctx.destination);
            animateLipByAudio(audioElement);
        } catch (e) {
            startFallbackLipSync(audioElement);
        }
    }

    function animateLipByAudio(audioElement) {
        if (!lipAnalyser || !lipData || !audioElement || audioElement.paused || audioElement.ended) {
            stopLipSync();
            return;
        }

        lipAnalyser.getByteTimeDomainData(lipData);
        var sum = 0;
        for (var i = 0; i < lipData.length; i++) {
            var normalized = (lipData[i] - 128) / 128;
            sum += normalized * normalized;
        }
        var rms = Math.sqrt(sum / lipData.length);
        var elapsed = performance.now() - lipStartedAt;
        var target = Math.max(0, Math.min(1, (rms - 0.012) * 6.4));
        if (elapsed < 520 && target < 0.22) {
            target = 0.24 + Math.abs(Math.sin(elapsed / 42)) * 0.28;
        }
        lipValue = lipValue * 0.58 + target * 0.42;
        setMouthOpen(lipValue);
        lipFrame = requestAnimationFrame(function () {
            animateLipByAudio(audioElement);
        });
    }

    function startFallbackLipSync(audioElement) {
        if (!audioElement || audioElement.paused || audioElement.ended) {
            stopLipSync();
            return;
        }
        var t = performance.now() / 1000;
        var target = 0.18 + Math.abs(Math.sin(t * 13.5)) * 0.62 + Math.abs(Math.sin(t * 6.2)) * 0.16;
        lipValue = lipValue * 0.45 + Math.min(1, target) * 0.55;
        setMouthOpen(lipValue);
        lipFrame = requestAnimationFrame(function () {
            startFallbackLipSync(audioElement);
        });
    }

    function startExternalLipSync() {
        if (!model) return;
        var now = performance.now();

        if (!lipFrame || externalLipNextChangeAt <= 0) {
            lipValue = 0.18;
            externalLipTarget = 0.42;
            externalLipNextChangeAt = now;
            externalLipPauseUntil = 0;
            externalLipNextPauseAt = now + 650 + Math.random() * 950;
            setMouthOpen(lipValue);
        }

        if (now >= externalLipNextPauseAt) {
            externalLipPauseUntil = now + 70 + Math.random() * 170;
            externalLipNextPauseAt = now + 760 + Math.random() * 1200;
        }

        if (now < externalLipPauseUntil) {
            externalLipTarget = 0.03 + Math.random() * 0.08;
        } else if (now >= externalLipNextChangeAt) {
            var r = Math.random();
            if (r < 0.16) {
                externalLipTarget = 0.02 + Math.random() * 0.08;
            } else if (r < 0.42) {
                externalLipTarget = 0.16 + Math.random() * 0.16;
            } else if (r < 0.82) {
                externalLipTarget = 0.34 + Math.random() * 0.24;
            } else {
                externalLipTarget = 0.58 + Math.random() * 0.24;
            }
            externalLipNextChangeAt = now + 55 + Math.random() * 95;
        }

        var target = Math.max(0, Math.min(1, externalLipTarget));
        var smoothing = target > lipValue ? 0.46 : 0.34;
        lipValue = lipValue * (1 - smoothing) + target * smoothing;
        if (lipValue < 0.035) lipValue = 0;
        setMouthOpen(lipValue);
        lipFrame = requestAnimationFrame(startExternalLipSync);
    }

    function stopLipSync() {
        if (lipFrame) {
            cancelAnimationFrame(lipFrame);
            lipFrame = null;
        }
        lipAnalyser = null;
        lipData = null;
        lipValue = 0;
        externalLipTarget = 0;
        externalLipNextChangeAt = 0;
        externalLipPauseUntil = 0;
        externalLipNextPauseAt = 0;
        lipStartedAt = 0;
        setMouthOpen(0);
    }

    function setMouthOpen(value) {
        mouthOpenValue = Math.max(0, Math.min(1, value || 0));
        applyMouthOpen();
    }

    function applyMouthOpen() {
        if (!model || !model.internalModel || !model.internalModel.coreModel) return;
        var coreModel = model.internalModel.coreModel;
        var v = mouthOpenValue;
        var ids = [];
        try {
            var settings = model.internalModel.settings;
            if (settings && typeof settings.getLipSyncParameters === 'function') {
                ids = settings.getLipSyncParameters() || [];
            }
        } catch (e0) { }

        ['PARAM_MOUTH_OPEN_Y', 'ParamMouthOpenY'].forEach(function (id) {
            if (ids.indexOf(id) < 0) ids.push(id);
        });

        ids.forEach(function (id) {
            try {
                coreModel.setParameterValueById(id, v);
            } catch (e) { }
        });
    }

    function bindMouthOpen(modelInstance) {
        if (!modelInstance || !modelInstance.internalModel || mouthBoundModel === modelInstance) return;
        mouthBoundModel = modelInstance;
        modelInstance.internalModel.on('beforeModelUpdate', applyMouthOpen);
    }

    function loadSubtitleText(name, type, variant) {
        var url = '/tts-text?name=' + encodeURIComponent(name) + '&type=' + type + '&variant=' + variant;
        return fetch(url)
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) {
                return data && data.text ? data.text : '';
            })
            .catch(function () { return ''; });
    }

    function showSubtitle(text) {
        if (!subtitleEl) return;
        if (subtitleTimer) {
            clearTimeout(subtitleTimer);
            subtitleTimer = null;
        }
        subtitleEl.textContent = text;
        subtitleEl.classList.add('visible');
        var duration = Math.max(3600, Math.min(7600, text.length * 220));
        subtitleTimer = setTimeout(function () {
            hideSubtitle();
        }, duration);
    }

    function hideSubtitle(delay) {
        if (!subtitleEl) return;
        if (subtitleTimer) {
            clearTimeout(subtitleTimer);
            subtitleTimer = null;
        }
        subtitleTimer = setTimeout(function () {
            subtitleEl.classList.remove('visible');
        }, delay || 0);
    }

    function pick(items) {
        return items[Math.floor(Math.random() * items.length)];
    }

    function getBehaviorConfig(name) {
        var base = BEHAVIORS[name];
        if (!base) return null;

        var modelOverrides = MODEL_BEHAVIOR_OVERRIDES[currentModelKey] || {};
        var override = modelOverrides[name];
        if (!override) return base;

        var config = {};
        Object.keys(base).forEach(function (key) {
            config[key] = base[key];
        });
        Object.keys(override).forEach(function (key) {
            config[key] = override[key];
        });
        return config;
    }

    function resolveBehaviorExpression(behavior) {
        if (behavior.expressionPool === 'all') {
            var buttons = (currentModelConfig && currentModelConfig.expressionButtons) || [];
            return buttons.length > 0 ? pick(buttons) : (behavior.expression || 'Normal');
        }
        if (Array.isArray(behavior.expression)) {
            return pick(behavior.expression);
        }
        return behavior.expression || 'Normal';
    }

    function resolveBehaviorMotions(behavior) {
        if (behavior.motionPool === 'all' || behavior.motionPool === 'visible') {
            var counts = (currentModelConfig && currentModelConfig.motionCounts) || {};
            var motions = [];
            Object.keys(counts).forEach(function (group) {
                if (behavior.motionPool === 'visible' && group === 'Idle') return;
                for (var i = 0; i < counts[group]; i++) {
                    motions.push([group, i]);
                }
            });
            return motions.length > 0 ? motions : (behavior.motions || []);
        }
        return behavior.motions || [];
    }

    function runBehavior(name, options) {
        if (!model) return;

        options = options || {};
        var behavior = getBehaviorConfig(name);
        if (!behavior) return;

        lastBehaviorName = name;
        lastBehaviorAt = performance.now();
        idleState = name;
        stopIdleCycle();
        clearIdleTimer();

        setExpression(resolveBehaviorExpression(behavior));

        var motions = resolveBehaviorMotions(behavior);
        if (motions.length > 0) {
            var motion = pick(motions);
            setTimeout(function () {
                playMotion(motion[0], motion[1]);
            }, 80);
        }

        if (behavior.tts && options.silent !== true) {
            playTTS(options.name || '访客', options.tts || behavior.tts);
        }

        showStatus(behavior.status || '动作中', 'activity');
        scheduleIdle(options.idleDelay || behavior.idleDelay || 4000);
    }

    function normalizeSpeechBehaviorType(type) {
        if (type === 'first_time') return 'first_time';
        if (type === 'returning') return 'returning';
        if (type === 'check_in') return 'check_in';
        if (type === 'check_out') return 'check_out';
        if (type === 'stranger' || type === 'returning_stranger') return 'stranger';
        if (type === 'repeat') return 'repeat';
        return '';
    }

    function maybeRunSpeechVisualFallback(msg) {
        var behaviorName = normalizeSpeechBehaviorType(msg.event_type || msg.type);
        if (!behaviorName) return;
        var now = performance.now();
        if (behaviorName !== 'first_time' && lastBehaviorName === behaviorName && now - lastBehaviorAt < 1400) {
            return;
        }
        setTimeout(function () {
            runBehavior(behaviorName, { name: msg.name || '访客', silent: true });
        }, behaviorName === 'first_time' ? 260 : 0);
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
                runBehavior('stranger', { name: '访客', silent: true });
                break;
            case 'smile':
                setExpression('Smile');
                break;
        }
    }

    function buildModelSwitcher() {
        if (!modelSwitcherEl) return;
        modelSwitcherEl.innerHTML = '';

        Object.keys(MODEL_REGISTRY).forEach(function (key) {
            var config = MODEL_REGISTRY[key];
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = config.label;
            button.dataset.model = key;
            button.classList.toggle('active', key === currentModelKey);
            button.addEventListener('click', function () {
                requestSwitchModel(key);
            });
            modelSwitcherEl.appendChild(button);
        });
    }

    function setModelSwitcherBusy(isBusy) {
        if (!modelSwitcherEl) return;
        modelSwitcherEl.querySelectorAll('button').forEach(function (button) {
            button.disabled = isBusy;
            button.classList.toggle('active', button.dataset.model === currentModelKey);
        });
    }

    function notifyAvatarReady() {
        fetch('/avatar-ready', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: currentModelKey,
                label: currentModelConfig && currentModelConfig.label
            })
        }).catch(function () { });
    }

    function buildDebugPanel() {
        if (!model || !currentModelConfig) return;
        var exprContainer = document.getElementById('expression-buttons');
        var motionContainer = document.getElementById('motion-buttons');
        exprContainer.innerHTML = '';
        motionContainer.innerHTML = '';

        var expressions = currentModelConfig.expressionButtons || [];
        if (expressions.length === 0) {
            var empty = document.createElement('button');
            empty.textContent = '无表情';
            empty.disabled = true;
            exprContainer.appendChild(empty);
        }

        expressions.forEach(function (name) {
            var expression = resolveExpression(name);
            if (!expression) return;
            var button = document.createElement('button');
            button.textContent = getExpressionLabel(name);
            button.dataset.name = expression;
            button.addEventListener('click', function () {
                setExpression(expression);
            });
            exprContainer.appendChild(button);
        });

        var motionLabels = {
            '': '动作',
            Idle: '待机',
            Tap: '轻点',
            Flick: '轻弹',
            FlickUp: '上弹',
            FlickDown: '下弹',
            Flick3: '三连弹',
            FlickRight: '右弹',
            FlickLeft: '左弹',
            Shake: '摇头',
            'FlickUp@Head': '头部上弹',
            'Flick@Body': '身体轻弹',
            'FlickDown@Body': '身体下弹',
            'Tap@Head': '头部轻点',
            'Tap@Body': '身体轻点'
        };

        var motionCounts = currentModelConfig.motionCounts || {};
        for (var internalName in motionCounts) {
            var count = motionCounts[internalName] || 1;
            for (var i = 0; i < count; i++) {
                (function (name, index) {
                    var indexLabels = (currentModelConfig.motionIndexLabels && currentModelConfig.motionIndexLabels[name]) || {};
                    var motionLabel = indexLabels[index] || motionLabels[name] || name || '动作';
                    var button = document.createElement('button');
                    button.textContent = motionLabel + (count > 1 ? '[' + index + ']' : '');
                    button.addEventListener('click', function () {
                        playMotion(name, index);
                        showStatus('动作：' + motionLabel, 'activity');
                    });
                    motionContainer.appendChild(button);
                })(internalName, i);
            }
        }

        var mouthOpenButton = document.createElement('button');
        mouthOpenButton.textContent = '张嘴';
        mouthOpenButton.addEventListener('click', function () {
            stopLipSync();
            setMouthOpen(1);
            showStatus('口型：张嘴', 'activity');
        });
        motionContainer.appendChild(mouthOpenButton);

        var mouthCloseButton = document.createElement('button');
        mouthCloseButton.textContent = '闭嘴';
        mouthCloseButton.addEventListener('click', function () {
            stopLipSync();
            setMouthOpen(0);
            showStatus('口型：闭嘴', 'activity');
        });
        motionContainer.appendChild(mouthCloseButton);
    }

    function getInitialModelKey() {
        var params = new URLSearchParams(location.search);
        var fromUrl = params.get('model');
        if (fromUrl && MODEL_REGISTRY[fromUrl]) {
            return fromUrl;
        }

        try {
            var stored = localStorage.getItem('avatarModel');
            if (stored && MODEL_REGISTRY[stored]) {
                return stored;
            }
        } catch (e) { }

        return DEFAULT_MODEL_KEY;
    }

    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    async function loadLive2DModelWithRetry(config) {
        var lastError = null;
        for (var attempt = 1; attempt <= MODEL_LOAD_ATTEMPTS; attempt++) {
            try {
                return await Live2DModel.from(config.path);
            } catch (err) {
                lastError = err;
                console.error('Model load failed:', config.path, err);
                if (attempt < MODEL_LOAD_ATTEMPTS) {
                    await sleep(700 * attempt);
                }
            }
        }
        throw lastError || new Error('model load failed');
    }

    function getFallbackModelKeys(preferredKey) {
        var keys = [preferredKey, DEFAULT_MODEL_KEY].concat(Object.keys(MODEL_REGISTRY));
        return keys.filter(function (key, index) {
            return MODEL_REGISTRY[key] && keys.indexOf(key) === index;
        });
    }

    async function loadStartupModel(preferredKey) {
        var lastError = null;
        var keys = getFallbackModelKeys(preferredKey);
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i];
            try {
                var loadedModel = await loadLive2DModelWithRetry(MODEL_REGISTRY[key]);
                return { key: key, model: loadedModel };
            } catch (err) {
                lastError = err;
            }
        }
        throw lastError || new Error('all models failed');
    }

    async function requestSwitchModel(key) {
        if (!MODEL_REGISTRY[key]) return;
        if (isSwitchingModel) {
            queuedModelKey = key;
            return;
        }

        isSwitchingModel = true;
        try {
            await switchModel(key);
            while (queuedModelKey && queuedModelKey !== currentModelKey) {
                var nextKey = queuedModelKey;
                queuedModelKey = null;
                await switchModel(nextKey);
            }
        } finally {
            isSwitchingModel = false;
            queuedModelKey = null;
        }
    }

    async function switchModel(key, options) {
        if (!MODEL_REGISTRY[key]) return;
        options = options || {};

        if (model && key === currentModelKey && options.force !== true) {
            return;
        }

        stopIdleCycle();
        clearIdleTimer();
        ttsRequestId++;
        ttsMutedUntil = performance.now() + 3000;
        stopLipSync();
        hideSubtitle();
        if (audio) {
            audio.pause();
            audio = null;
        }

        var previousModel = model;
        var previousKey = currentModelKey;
        var previousConfig = currentModelConfig;
        currentModelKey = key;
        currentModelConfig = MODEL_REGISTRY[key];
        setModelSwitcherBusy(true);
        loadingEl.innerHTML = '<div class="spinner"></div><div>正在加载数字人...</div>';
        loadingEl.style.display = 'block';
        loadingEl.style.opacity = '1';

        try {
            var loaded = previousModel
                ? { key: key, model: await loadLive2DModelWithRetry(currentModelConfig) }
                : await loadStartupModel(key);
            var nextModel = loaded.model;
            currentModelKey = loaded.key;
            currentModelConfig = MODEL_REGISTRY[currentModelKey];
            if (previousModel) {
                app.stage.removeChild(previousModel);
                previousModel.destroy({ children: true, texture: false, baseTexture: false });
            }
            model = nextModel;
            app.stage.addChild(model);
            fitModel();
            bindMouthOpen(model);

            try {
                localStorage.setItem('avatarModel', currentModelKey);
            } catch (e) { }

            setExpression('Normal');
            playMotion('Idle', 0);
            enterIdle();
            buildDebugPanel();
            buildModelSwitcher();

            loadingEl.style.opacity = '0';
            setTimeout(function () {
                loadingEl.style.display = 'none';
            }, 500);
            notifyAvatarReady();
        } catch (err) {
            console.error('Model switch failed:', err);
            currentModelKey = previousKey;
            currentModelConfig = previousConfig;
            model = previousModel;
            loadingEl.innerHTML = '<div>模型加载失败</div><div style="font-size:14px;margin-top:8px;color:#ff6b6b">' + err.message + '</div>';
        } finally {
            setModelSwitcherBusy(false);
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
        if (msg.type === 'speech') {
            clearIdleTimer();
            if (msg.text) {
                showStatus(msg.text, 'speech');
                hideSubtitle();
            }
            if (msg.external_audio || msg.text) {
                stopLipSync();
                startExternalLipSync();
            }
            maybeRunSpeechVisualFallback(msg);
            return;
        }

        if (msg.type === 'speech_end') {
            statusMode = 'idle';
            stopLipSync();
            hideSubtitle();
            scheduleIdle(800);
            return;
        }

        clearIdleTimer();
        switch (msg.type) {
            case 'check_in':
                if (msg.is_first === true || msg.is_first === 'true' || msg.event_type === 'first_time') {
                    runBehavior('first_time', { name: msg.name || '访客', silent: true });
                } else if (msg.is_returning === true || msg.is_returning === 'true' || msg.event_type === 'returning') {
                    runBehavior('returning', { name: msg.name || '访客', silent: true });
                } else {
                    runBehavior('check_in', { name: msg.name || '访客', silent: true });
                }
                break;
            case 'first_time':
                runBehavior('first_time', { name: msg.name || '访客', silent: true });
                break;
            case 'returning':
                runBehavior('returning', { name: msg.name || '访客', silent: true });
                break;
            case 'check_out':
                runBehavior('check_out', { name: msg.name || '访客', silent: true });
                break;
            case 'stranger':
                runBehavior('stranger', { name: '', silent: true });
                break;
            case 'repeat':
                runBehavior('repeat', { name: msg.name || '访客', silent: true });
                break;
            case 'attention':
                if (idleState === 'idle') {
                    runBehavior('attention', { silent: true });
                }
                break;
            case 'idle_long':
                runBehavior('idle_long', { name: '', silent: true });
                break;
            case 'crowd':
                runBehavior('crowd', { name: '', silent: true });
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
        statusMode = 'idle';
        setExpression('Normal');
        playMotion('Idle', 0);
        showStatus('待机中', 'idle');
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

            fetch('/tts-manifest')
                .then(function (res) { return res.ok ? res.json() : {}; })
                .then(function (manifest) { ttsManifest = manifest || {}; })
                .catch(function () { ttsManifest = {}; });

            fetch('/tts-voices')
                .then(function (res) { return res.ok ? res.json() : {}; })
                .then(function (data) {
                    ttsVoiceByModel = (data && data.byModel) || {};
                    Object.keys(MODEL_REGISTRY).forEach(function (key) {
                        if (ttsVoiceByModel[key]) {
                            MODEL_REGISTRY[key].voice = ttsVoiceByModel[key];
                        }
                    });
                })
                .catch(function () { ttsVoiceByModel = {}; });

            currentModelKey = getInitialModelKey();
            currentModelConfig = MODEL_REGISTRY[currentModelKey];
            buildModelSwitcher();
            await switchModel(currentModelKey, { force: true });

            canvas.addEventListener('click', function (e) {
                unlockAudio();
                const rect = canvas.getBoundingClientRect();
                const y = (e.clientY - rect.top) / rect.height;
                if (y < 0.5) {
                    playMotion('Tap', Math.floor(Math.random() * 4));
                } else {
                    playMotion('Flick', Math.floor(Math.random() * 2));
                }
            });
            document.addEventListener('pointerdown', unlockAudio, { once: true });

            connectWebSocket();
        } catch (err) {
            console.error('Init failed:', err);
            loadingEl.innerHTML = '<div>加载失败</div><div style="font-size:14px;margin-top:8px;color:#ff6b6b">' + err.message + '</div>';
        }
    }

    window.doAction = doAction;
    window.setExpression = setExpression;
    window.playMotion = playMotion;
    window.switchModel = requestSwitchModel;
    window.__avatarDebug = {
        setMouthOpen: setMouthOpen,
        startExternalLipSync: startExternalLipSync,
        stopLipSync: stopLipSync,
        getMouthOpen: function () { return mouthOpenValue; }
    };

    init();
})();

(function () {
    var themes = ['bubble', 'sky', 'sakura'];
    var theme = themes[Math.floor(Math.random() * themes.length)];

    document.body.classList.add('theme-' + theme);

    if (theme === 'bubble') {
        buildBubbles();
    }

    if (theme === 'sakura') {
        buildSakura();
    }

    console.log('Background theme:', theme);

    function buildBubbles() {
        var container = document.getElementById('bubble-container');
        var classes = ['b1', 'b2', 'b3'];

        classes.forEach(function (className, index) {
            var bubble = document.createElement('div');
            bubble.className = 'bubble ' + className;
            bubble.style.animationDelay = '-' + (index * 1.4 + Math.random() * 1.2) + 's';
            container.appendChild(bubble);
        });
    }

    function buildSakura() {
        var container = document.getElementById('sakura-container');

        for (var i = 0; i < 30; i++) {
            var sakura = document.createElement('div');
            sakura.className = 'sakura';
            sakura.style.left = Math.random() * 100 + 'vw';
            sakura.style.animationDuration = 3 + Math.random() * 5 + 's';
            sakura.style.animationDelay = Math.random() * 6 + 's';
            sakura.style.transform = 'scale(' + (0.7 + Math.random() * 0.8) + ')';
            container.appendChild(sakura);
        }
    }
})();

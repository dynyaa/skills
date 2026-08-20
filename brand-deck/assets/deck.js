/* Навигация, счётчик, анимация цифр. Скрипт сам считает слайды — индексы
   в разметке не нужны, поэтому слайд можно вставить в середину без правок. */
(function () {
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  var bar = document.querySelector('.progress');
  var counter = document.querySelector('.counter');
  var dots = document.querySelector('.dots');
  var i = 0;

  if (dots) {
    slides.forEach(function (_, n) {
      var d = document.createElement('i');
      d.onclick = function () { go(n); };
      dots.appendChild(d);
    });
  }

  function countUp(el) {
    var target = parseFloat(el.dataset.count);
    if (isNaN(target)) return;
    var suffix = el.dataset.suffix || '';
    var prefix = el.dataset.prefix || '';
    var dec = (el.dataset.decimals | 0);
    var dur = 850, t0 = null;
    function frame(ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var v = target * (1 - Math.pow(1 - p, 3));
      el.textContent = prefix + v.toLocaleString('ru-RU', {
        minimumFractionDigits: dec, maximumFractionDigits: dec
      }) + suffix;
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  /* Самый частый способ испортить дек — насыпать в слайд больше, чем влезает:
     на экране докладчика всё видно, а в зале верх и низ обрезаны. Поэтому
     содержимое, которое не помещается, ужимается, а факт фиксируется в консоли
     и в data-fit — по нему легко найти перегруженные слайды. */
  function fit(s) {
    var w = s.querySelector('.wrap');
    if (!w) return;
    w.style.setProperty('--fit', 1);
    var pad = parseFloat(getComputedStyle(s).paddingTop) || 0;
    var avail = s.clientHeight - pad * 2;
    var need = w.scrollHeight;
    if (need > avail + 1) {
      var k = Math.max(0.62, avail / need);
      w.style.setProperty('--fit', k.toFixed(3));
      s.dataset.fit = k.toFixed(2);
      console.warn('Слайд ' + (slides.indexOf(s) + 1) + ': содержимое не помещается, '
        + 'ужато до ' + Math.round(k * 100) + '%. Уберите блок или сократите текст.');
    } else {
      delete s.dataset.fit;
    }
  }

  function go(n) {
    if (n < 0 || n >= slides.length || n === i) return;
    slides[i].classList.remove('active');
    i = n;
    var s = slides[i];
    s.classList.add('active');
    // Перезапуск reveal: без сброса анимация не проигрывается повторно
    s.querySelectorAll('[data-r]').forEach(function (el) {
      el.style.animation = 'none';
      void el.offsetWidth;
      el.style.animation = '';
    });
    fit(s);
    s.querySelectorAll('.num[data-count]').forEach(countUp);
    if (bar) bar.style.width = ((i + 1) / slides.length * 100) + '%';
    if (counter) counter.textContent =
      String(i + 1).padStart(2, '0') + ' / ' + String(slides.length).padStart(2, '0');
    if (dots) [].forEach.call(dots.children, function (d, n2) {
      d.classList.toggle('on', n2 === i);
    });
    location.hash = i + 1;
  }

  document.addEventListener('keydown', function (e) {
    if (['ArrowRight', 'ArrowDown', ' ', 'PageDown', 'Enter'].indexOf(e.key) > -1) {
      e.preventDefault(); go(i + 1);
    } else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].indexOf(e.key) > -1) {
      e.preventDefault(); go(i - 1);
    } else if (e.key === 'Home') { go(0); }
    else if (e.key === 'End') { go(slides.length - 1); }
    else if (e.key === 'f' || e.key === 'F') {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
  });

  document.addEventListener('click', function (e) {
    if (e.target.closest('.dots') || e.target.closest('a')) return;
    go(e.clientX < innerWidth * 0.35 ? i - 1 : i + 1);
  });

  var tx = null;
  document.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; }, { passive: true });
  document.addEventListener('touchend', function (e) {
    if (tx === null) return;
    var dx = e.changedTouches[0].clientX - tx;
    if (Math.abs(dx) > 45) go(dx < 0 ? i + 1 : i - 1);
    tx = null;
  }, { passive: true });

  var start = parseInt((location.hash || '').slice(1), 10);
  slides[0].classList.add('active');
  go(start > 0 && start <= slides.length ? start - 1 : 0);
  if (start === 1 || !start) { // go() выходит рано, если индекс совпал
    slides[0].classList.add('active');
    if (bar) bar.style.width = (1 / slides.length * 100) + '%';
    if (counter) counter.textContent = '01 / ' + String(slides.length).padStart(2, '0');
    if (dots && dots.children[0]) dots.children[0].classList.add('on');
    fit(slides[0]);
    slides[0].querySelectorAll('.num[data-count]').forEach(countUp);
  }
  addEventListener('resize', function () { if (slides[i]) fit(slides[i]); });
  window.__deckReady = true;
})();

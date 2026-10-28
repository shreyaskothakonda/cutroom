// Cutroom scene runtime. Every scene page loads this first.
//
// The renderer injects window.__SCENE__ = {width, height, fps, duration, params, words}
// and then calls window.renderFrame(t) once per frame. Nothing animates on its own:
// GSAP timelines are paused and seeked, Three.js renders on demand.
(function () {
  const S = window.__SCENE__ || { width: 1920, height: 1080, fps: 30, duration: 5, params: {}, words: [] };
  const root = document.documentElement;
  const portrait = S.height > S.width;
  root.classList.add(portrait ? 'portrait' : 'landscape');
  root.style.setProperty('--w', S.width + 'px');
  root.style.setProperty('--h', S.height + 'px');
  // One unit = 1% of the short side, so type scales the same in both formats.
  root.style.setProperty('--u', Math.min(S.width, S.height) / 100 + 'px');

  const frameHooks = [];
  const waits = [];
  let resolveReady;
  window.__ready = new Promise((r) => (resolveReady = r));

  const RS = {
    scene: S,
    params: S.params || {},
    portrait,
    duration: S.duration,
    onFrame(fn) { frameHooks.push(fn); },
    // A paused GSAP timeline driven by the frame clock.
    timeline(opts) {
      const tl = gsap.timeline({ paused: true, ...opts });
      frameHooks.push((t) => { tl.seek(Math.min(t, tl.duration() || t), false); });
      return tl;
    },
    wait(promise) { waits.push(promise); },
    loadImage(src) {
      const p = new Promise((res, rej) => {
        const img = new Image();
        img.onload = () => res(img);
        img.onerror = () => rej(new Error('image failed: ' + src));
        img.src = src;
      });
      waits.push(p);
      return p;
    },
    // Split text into word spans for staggered reveals.
    splitWords(el) {
      const words = el.textContent.trim().split(/\s+/);
      el.textContent = '';
      return words.map((w, i) => {
        const s = document.createElement('span');
        s.className = 'rs-word';
        s.textContent = w;
        el.appendChild(s);
        if (i < words.length - 1) el.appendChild(document.createTextNode(' '));
        return s;
      });
    },
    async start() {
      await document.fonts.ready;
      await Promise.all(waits);
      await window.renderFrame(0);
      resolveReady(true);
    },
  };
  window.RS = RS;

  // Captions: word-timed, chunked into short lines, current word highlighted.
  const words = S.words || [];
  let capEl = null;
  const chunks = [];
  if (words.length && RS.params.captions !== false) {
    const maxWords = portrait ? 4 : 7;
    let cur = [];
    words.forEach((w, i) => {
      cur.push(i);
      const endOfClause = /[.,!?;:]$/.test(w.w);
      if (cur.length >= maxWords || endOfClause || i === words.length - 1) {
        chunks.push(cur);
        cur = [];
      }
    });
    document.addEventListener('DOMContentLoaded', () => {
      capEl = document.createElement('div');
      capEl.className = 'rs-captions';
      capEl.dataset.qa = 'captions';
      document.body.appendChild(capEl);
    });
  }
  let shownChunk = -1;
  function drawCaptions(t) {
    if (!capEl) return;
    const ci = chunks.findIndex((c) => t >= words[c[0]].start - 0.05 && t <= words[c[c.length - 1]].end + 0.25);
    if (ci !== shownChunk) {
      shownChunk = ci;
      capEl.replaceChildren();
      if (ci >= 0) chunks[ci].forEach((wi, k) => {
        const s = document.createElement('span');
        s.dataset.wi = wi;
        s.textContent = words[wi].w;
        if (k) capEl.append(' ');
        capEl.append(s);
      });
      capEl.style.opacity = ci < 0 ? 0 : 1;
    }
    if (ci >= 0) {
      capEl.querySelectorAll('span').forEach((s) => {
        const w = words[+s.dataset.wi];
        s.classList.toggle('on', t >= w.start - 0.03 && t < w.end + 0.08);
        s.classList.toggle('past', t >= w.end + 0.08);
      });
    }
  }

  window.renderFrame = async (t) => {
    // Only await real promises. GSAP timelines are thenables that resolve on completion.
    for (const fn of frameHooks) {
      const r = fn(t);
      if (r instanceof Promise) await r;
    }
    drawCaptions(t);
  };

  // Boxes of labelled elements, for overlap QA. Text boxes use their ink, not their block.
  window.__layout = () =>
    [...document.querySelectorAll('[data-qa]')].map((el) => {
      let r = el.getBoundingClientRect();
      if (el.dataset.qaInk !== undefined || el.classList.contains('rs-captions')) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const ink = range.getBoundingClientRect();
        if (ink.width > 0) r = ink;
      }
      let o = 1, n = el;
      while (n && n !== document) { o *= +getComputedStyle(n).opacity; n = n.parentNode; }
      return {
        id: el.dataset.qa, layer: el.dataset.layer || 'fg',
        x: r.x, y: r.y, w: r.width, h: r.height,
        visible: o > 0.1 && r.width > 0 && el.textContent.trim().length + el.children.length > 0,
      };
    });
})();

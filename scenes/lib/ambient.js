// Slow drifting colour blobs behind the content. Driven by the frame clock.
function rsAmbient(container, colors) {
  const cs = colors || [getComputedStyle(document.documentElement).getPropertyValue('--accent'),
                        getComputedStyle(document.documentElement).getPropertyValue('--accent-2'), '#ff7a59'];
  const W = RS.scene.width, H = RS.scene.height;
  const blobs = cs.map((c, i) => {
    const b = document.createElement('div');
    b.className = 'rs-blob';
    b.style.background = c;
    container.appendChild(b);
    return { el: b, phase: i * 2.1, rx: 0.32 + i * 0.07, ry: 0.22 + i * 0.05 };
  });
  const g = document.createElement('div');
  g.className = 'rs-grain';
  container.appendChild(g);
  RS.onFrame((t) => {
    blobs.forEach((b, i) => {
      const x = W * (0.5 + b.rx * Math.cos(t * 0.35 + b.phase)) - b.el.offsetWidth / 2;
      const y = H * (0.45 + b.ry * Math.sin(t * 0.28 + b.phase * 1.3)) - b.el.offsetHeight / 2;
      b.el.style.transform = `translate(${x}px, ${y}px)`;
    });
  });
}

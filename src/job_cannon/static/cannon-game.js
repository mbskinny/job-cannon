// Easter egg: double-click the cannon logo for an artillery duel, with an interview question to mull over meanwhile.
(function () {
  const QUESTIONS = [
    "Tell me about yourself.",
    "Why do you want to work here?",
    "Why are you leaving your current role?",
    "Describe a project you're proud of. What was your specific contribution?",
    "Tell me about a time you disagreed with a teammate. How did you resolve it?",
    "Tell me about a time you failed. What did you learn?",
    "How do you prioritise when everything feels urgent?",
    "What would your last manager say is your biggest area for growth?",
    "Describe a time you had to learn something new quickly.",
    "Tell me about a time you received difficult feedback. What did you do with it?",
    "Give an example of a time you influenced a decision without having authority.",
    "Describe a situation where the requirements were unclear. How did you proceed?",
    "Tell me about a time you went beyond what was asked of you.",
    "How do you handle a tight deadline you don't think is achievable?",
    "Describe a mistake you made at work and how you handled it.",
    "Tell me about a time you had to explain something complex to a non-expert.",
    "What kind of work environment brings out your best?",
    "Where do you see yourself in three to five years?",
    "What's a strength of yours that doesn't show up on your résumé?",
    "Tell me about a time you improved a process or way of working.",
    "Describe a time you had to deliver bad news to a stakeholder.",
    "How do you decide when something is good enough to ship?",
    "Tell me about a conflict between two priorities and the trade-off you made.",
    "Describe the best team you've worked on. What made it work?",
    "Tell me about a time you helped a colleague grow.",
    "What's something you changed your mind about recently, and why?",
    "Describe a time you used data to make or change a decision.",
    "How do you stay current in your field?",
    "What questions do you have for us?",
    "What are your salary expectations, and how did you arrive at them?",
  ];

  const W = 800, H = 450;
  const G = 300;                 // gravity, px/s²
  const DT = 1 / 240;            // physics step; four steps per 60 Hz frame
  const STEPS_PER_FRAME = 4;
  const SPEED_PER_POWER = 6;     // px/s per power point
  const MAX_WIND = 40;           // px/s² either way
  // Streamers on poles between the cannons show the wind: limp in a calm, nearly level and rippling fast in a gale.
  const STREAMER_POLES = [W / 2 - 140, W / 2 + 140];   // clear of both cannons, which sit within 220 px of their edge
  const POLE = 34;
  const STREAMER = 30;
  const BLAST = 28;              // crater radius
  // Damage, out of MAX_HP: a direct hit takes DIRECT_DAMAGE, a burst within SPLASH px of a cannon up to SPLASH_DAMAGE
  // (less the further off it lands), and a cannon whose ground is blown away takes 1 per 3 px it falls past the first 10.
  const MAX_HP = 100;
  const DIRECT_DAMAGE = 45;
  const SPLASH = BLAST + 30;
  const SPLASH_DAMAGE = 35;
  // Power-ups: a crate floats over the field now and then, and a ball that flies through it collects it for the shooter.
  // Repair heals at once; Big shot and Sights are held for the shooter's next shot (one at a time, a new one replaces it).
  const CRATE = 13;              // crate half-size; the ball collects it within CRATE + 4
  const CRATE_CHANCE = 0.4;      // chance a crate appears at the start of a turn, when there isn't one
  const PERKS = { repair: "Repair", big: "Big shot", sights: "Sights" };
  const REPAIR = 25;
  const BIG = 1.5;               // Big shot's blast radius and damage multiplier
  // Cannons are the header logo (templates/partials/logo.html), drawn in its 120-unit space at LOGO_SCALE px per unit.
  // A cannon's (x, y) is where its wheel touches the ground: logo point (50, 103.5).
  const LOGO_SCALE = 0.7;
  const LOGO_ORIGIN = [50, 103.5];
  const LOGO_PIVOT = [52, 71];                          // the barrel turns about this point on its axis
  const BARREL = 45 * LOGO_SCALE;                       // pivot to muzzle
  const PIVOT_DX = (LOGO_PIVOT[0] - LOGO_ORIGIN[0]) * LOGO_SCALE;
  const PIVOT_DY = (LOGO_ORIGIN[1] - LOGO_PIVOT[1]) * LOGO_SCALE;
  const CENTER_DY = 20 * LOGO_SCALE;                    // hitbox centre, roughly the wheel hub
  const HITBOX = 30 * LOGO_SCALE;
  const FOOT = 18;                                      // half-width of the cannon's footing
  const BARREL_PATH = new Path2D("M34 60 L93 63 L93 79 L34 82 Z");
  const SPOKES_PATH = new Path2D("M50 70 V98 M36 84 H64 M40.1 74.1 L59.9 93.9 M59.9 74.1 L40.1 93.9");

  let dlg, canvas, ctx, els, colors, fluttering = false, animating = 0;
  let ground, cannons, turn, wind, ball, trail, boom, popups, crate, aim, message, busy, over, cpuError, gameId = 0, qIndex = -1;

  // --- Trigger: a single click on the logo still navigates, a double-click opens the game. ---
  let navTimer;
  document.addEventListener("click", (e) => {
    const mark = e.target.closest(".brand .logo-mark");
    if (!mark || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    clearTimeout(navTimer);
    if (e.detail >= 2) open();
    else {
      const href = mark.closest("a").href;
      navTimer = setTimeout(() => { location.href = href; }, 250);
    }
  });

  function open() {
    if (!dlg) build();
    readColors();
    dlg.showModal();
    newGame();
    if (!fluttering) { fluttering = true; requestAnimationFrame(flutter); }
  }

  // Redraws every frame while the dialog is open so the streamers move; animate() does the drawing during shots.
  function flutter() {
    if (!dlg.open) { fluttering = false; return; }
    if (!animating) draw();
    requestAnimationFrame(flutter);
  }

  function build() {
    dlg = document.createElement("dialog");
    dlg.className = "cannon-game";
    dlg.setAttribute("aria-label", "Cannon duel");
    dlg.innerHTML = `
      <article>
        <header>
          <button aria-label="Close" rel="prev" data-close></button>
          <strong>Cannon duel</strong>
        </header>
        <canvas width="${W}" height="${H}"></canvas>
        <div class="cg-controls">
          <label>Angle <output data-angle-out></output>°<input type="range" min="0" max="90" step="1" data-angle></label>
          <label>Power <output data-power-out></output><input type="range" min="5" max="100" step="1" data-power></label>
          <button data-fire>Fire</button>
        </div>
        <div class="cg-options">
          <label><input type="checkbox" role="switch" data-twop> 2 players</label>
          <a href="#" data-new>New game</a>
          <small>←/→ angle · ↑/↓ power (Shift: faster) · Space to fire</small>
        </div>
        <footer class="cg-question">
          <small>Think about this while you aim</small>
          <p data-q></p>
          <a href="#" data-next-q>Another question</a>
        </footer>
      </article>`;
    document.body.append(dlg);
    canvas = dlg.querySelector("canvas");
    ctx = canvas.getContext("2d");
    const q = (sel) => dlg.querySelector(sel);
    els = {
      angle: q("[data-angle]"), power: q("[data-power]"), angleOut: q("[data-angle-out]"),
      powerOut: q("[data-power-out]"), fire: q("[data-fire]"), twop: q("[data-twop]"), question: q("[data-q]"),
    };

    q("[data-close]").addEventListener("click", () => dlg.close());
    dlg.addEventListener("close", () => { gameId++; });
    els.angle.addEventListener("input", () => { if (canAim()) { current().angle = +els.angle.value; sync(); } });
    els.power.addEventListener("input", () => { if (canAim()) { current().power = +els.power.value; sync(); } });
    els.fire.addEventListener("click", () => { if (canAim()) fire(); });
    els.twop.addEventListener("change", newGame);
    q("[data-new]").addEventListener("click", (e) => { e.preventDefault(); newGame(); });
    q("[data-next-q]").addEventListener("click", (e) => { e.preventDefault(); nextQuestion(); });
    // On the document, not the dialog: disabling Fire mid-shot drops focus to <body>.
    document.addEventListener("keydown", onKey);
  }

  function onKey(e) {
    if (!dlg.open) return;
    const step = e.shiftKey ? 5 : 1;
    const moves = { ArrowLeft: ["angle", step], ArrowRight: ["angle", -step], ArrowUp: ["power", step], ArrowDown: ["power", -step] };
    if (e.key in moves || e.key === " ") e.preventDefault(); else return;
    if (over && e.key === " ") return newGame();
    if (!canAim()) return;
    if (e.key === " ") return fire();
    const [field, delta] = moves[e.key];
    const c = current();
    // "Left" always tips the barrel towards the left of the screen, whichever way the cannon faces.
    const d = field === "angle" && c.dir < 0 ? -delta : delta;
    c[field] = field === "angle" ? clamp(c.angle + d, 0, 90) : clamp(c.power + d, 5, 100);
    sync();
  }

  function readColors() {
    const s = getComputedStyle(document.documentElement);
    const v = (name) => s.getPropertyValue(name).trim();
    colors = {
      sky: v("--jc-paper"), ground: v("--jc-field-border"), edge: v("--jc-ink-soft"), ink: v("--jc-ink"),
      brass: v("--jc-brass"), p1: v("--jc-applied"), p2: v("--jc-rejected"), trail: v("--jc-rule"),
    };
  }

  // --- Game state ---
  function newGame() {
    gameId++;
    makeTerrain();
    // Each cannon sits 40–220 px in from its edge, so they end up 360–720 px apart.
    const inset = () => 40 + Math.floor(Math.random() * 181);
    cannons = [
      { x: inset(), dir: 1, angle: 45, power: 60, color: colors.p1, name: isCpu() ? "You" : "Player 1", trail: null },
      { x: W - inset(), dir: -1, angle: 45, power: 60, color: colors.p2, name: isCpu() ? "Computer" : "Player 2", trail: null },
    ];
    for (const c of cannons) { flatten(c.x); c.y = restY(c.x); c.hp = MAX_HP; c.alive = true; c.perk = null; }
    turn = Math.random() < 0.5 ? 0 : 1;
    over = false; busy = false; ball = null; boom = null; popups = []; crate = null; aim = null; cpuError = 20;
    nextQuestion();
    startTurn();
  }

  function makeTerrain() {
    ground = new Float32Array(W);
    const waves = [1, 2, 3].map((k) => ({ f: (k * Math.PI * 2) / W * (0.6 + Math.random()), a: 40 / k * Math.random(), p: Math.random() * 6.3 }));
    const hill = H * (0.15 + Math.random() * 0.2), mid = W * (0.4 + Math.random() * 0.2), spread = W * (0.1 + Math.random() * 0.08);
    for (let x = 0; x < W; x++) {
      let y = H * 0.72 - hill * Math.exp(-(((x - mid) / spread) ** 2));
      for (const w of waves) y += w.a * Math.sin(x * w.f + w.p);
      ground[x] = clamp(y, H * 0.25, H - 30);
    }
  }

  function flatten(cx) {
    let level = 0;
    for (let x = cx - FOOT; x <= cx + FOOT; x++) level += ground[x];
    level /= 2 * FOOT + 1;
    for (let x = cx - FOOT; x <= cx + FOOT; x++) ground[x] = level;
  }

  // A cannon rests on the highest ground (smallest y) under its wheels.
  function restY(cx) {
    let y = H;
    for (let x = cx - 12; x <= cx + 12; x++) y = Math.min(y, ground[clamp(x, 0, W - 1)]);
    return y;
  }

  function startTurn() {
    wind = Math.round((Math.random() * 2 - 1) * MAX_WIND);
    if (!crate && Math.random() < CRATE_CHANCE) spawnCrate();
    if (isCpu() && turn === 1) {
      busy = true;
      message = "Computer is aiming…";
      sync();
      cpuTurn(gameId);
    } else {
      busy = false;
      message = current().name === "You" ? "Your shot" : `${current().name}’s shot`;
      sync();
    }
  }

  async function cpuTurn(id) {
    await wait(700);
    if (id !== gameId) return;
    const me = cannons[1], target = cannons[0];
    let best = { miss: Infinity };
    for (let angle = 25; angle <= 80; angle += 5) {
      for (let power = 10; power <= 100; power += 1) {
        const r = simulate(me, angle, power, wind);
        const miss = r.hit === target ? 0 : r.hit === "out" ? Infinity : Math.hypot(r.x - target.x, r.y - target.y);
        if (miss < best.miss) best = { miss, angle, power };
      }
    }
    if (best.miss === Infinity) best = { angle: 45, power: 60 };
    // Starts sloppy and tightens up each turn.
    const noise = (Math.random() + Math.random() + Math.random() - 1.5) * cpuError;
    cpuError = Math.max(0.5, cpuError * 0.75);
    me.angle = best.angle;
    me.power = clamp(Math.round(best.power + noise), 5, 100);
    sync();
    await wait(400);
    if (id === gameId) fire();
  }

  // Somewhere between the cannons, clear of the top-of-screen text and well above the ground.
  function spawnCrate() {
    const lo = Math.min(cannons[0].x, cannons[1].x) + 80, hi = Math.max(cannons[0].x, cannons[1].x) - 80;
    if (hi <= lo) return;
    const x = Math.round(lo + Math.random() * (hi - lo));
    const top = 80, bottom = ground[x] - 60;
    if (bottom <= top) return;
    const kinds = Object.keys(PERKS);
    crate = { x, y: Math.round(top + Math.random() * (bottom - top)), kind: kinds[Math.floor(Math.random() * kinds.length)] };
  }

  // --- Physics, shared by the animation and the computer's aiming. ---
  function muzzle(c, angle) {
    const a = (angle * Math.PI) / 180;
    return { x: c.x + (PIVOT_DX + Math.cos(a) * BARREL) * c.dir, y: c.y - PIVOT_DY - Math.sin(a) * BARREL, a };
  }

  function simulate(shooter, angle, power, windAccel, path) {
    const m = muzzle(shooter, angle);
    let x = m.x, y = m.y;
    let vx = Math.cos(m.a) * power * SPEED_PER_POWER * shooter.dir, vy = -Math.sin(m.a) * power * SPEED_PER_POWER;
    let pickup = -1;               // index into path where the ball reaches the crate
    for (let i = 0; i < 40000; i++) {
      vx += windAccel * DT; vy += G * DT;
      x += vx * DT; y += vy * DT;
      if (path && i % STEPS_PER_FRAME === 0) path.push([x, y]);
      if (crate && pickup < 0 && Math.hypot(x - crate.x, y - crate.y) < CRATE + 4) pickup = Math.floor(i / STEPS_PER_FRAME);
      if (x < 0 || x >= W || y >= H) return { hit: "out", x, y, pickup };
      for (const c of cannons) if (c.alive && Math.hypot(x - c.x, y - (c.y - CENTER_DY)) < HITBOX) return { hit: c, x, y, pickup };
      if (y >= ground[Math.floor(x)]) return { hit: "ground", x, y, pickup };
    }
    return { hit: "out", x, y, pickup };
  }

  async function fire() {
    const id = gameId, shooter = current();
    busy = true;
    message = "";
    aim = null;
    const mult = shooter.perk === "big" ? BIG : 1;
    if (shooter.perk === "big" || shooter.perk === "sights") shooter.perk = null;
    const path = [];
    const result = simulate(shooter, shooter.angle, shooter.power, wind, path);
    shooter.trail = path;
    const got = result.pickup >= 0 ? crate : null;
    // Path points are one 60 Hz frame apart; play them back in real time whatever the display's refresh rate.
    if (!await animate(id, (path.length * 1000) / 60, (t) => {
      const i = Math.min(path.length - 1, Math.floor(t * path.length));
      ball = path[i];
      if (got && i >= result.pickup) crate = null;
    })) return;
    ball = null;
    if (got) crate = null;
    popups = [];
    const popup = (x, y, color, text) => popups.push({ x, y, color, text, rise: 0 });
    const above = (c) => c.y - PIVOT_DY - BARREL - 10;
    if (got) popup(got.x, got.y - CRATE - 8, shooter.color, PERKS[got.kind]);

    if (result.hit !== "out") {
      const blast = BLAST * mult, splash = SPLASH * mult;
      if (!await animate(id, 160, (t) => { boom = { x: result.x, y: result.y, r: 4 + t * (blast - 4) }; })) return;
      boom = null;
      carve(result.x, result.y, blast);
      const damage = cannons.map((c) => {
        const d = Math.hypot(result.x - c.x, result.y - (c.y - CENTER_DY));
        return Math.round(mult * (c === result.hit ? DIRECT_DAMAGE : d < splash ? SPLASH_DAMAGE * (1 - d / splash) : 0));
      });
      const before = cannons.map((c) => c.y);
      if (!await settle(id)) return;
      cannons.forEach((c, i) => {
        const dmg = damage[i] + Math.max(0, Math.round((c.y - before[i] - 10) / 3));
        if (!dmg) return;
        c.hp = Math.max(0, c.hp - dmg);
        c.alive = c.hp > 0;
        popup(c.x, above(c), c.color, `−${dmg}`);
      });
    }
    if (got && shooter.alive) {
      if (got.kind === "repair") {
        const heal = Math.min(REPAIR, MAX_HP - shooter.hp);
        shooter.hp += heal;
        if (heal) popup(shooter.x, above(shooter), shooter.color, `+${heal}`);
      } else shooter.perk = got.kind;
    }
    if (popups.length) {
      if (!await animate(id, 700, (t) => { for (const p of popups) p.rise = t; })) return;
      popups = [];
    }

    const other = cannons[1 - turn];
    if (!other.alive || !shooter.alive) {
      over = true;
      const wins = (c) => (c.name === "You" ? "You win!" : `${c.name} wins!`);
      message = other.alive ? `Own goal! ${wins(other)}` : wins(shooter);
      busy = false;
      sync();
      return;
    }
    turn = 1 - turn;
    startTurn();
  }

  function carve(cx, cy, r) {
    for (let x = Math.max(0, Math.ceil(cx - r)); x <= Math.min(W - 1, Math.floor(cx + r)); x++) {
      const bottom = cy + Math.sqrt(r * r - (x - cx) ** 2);
      if (bottom > ground[x]) ground[x] = Math.min(H - 4, Math.max(ground[x], bottom));
    }
  }

  // Cannons whose ground was blown away drop onto the new surface, at 240 px/s.
  function settle(id) {
    const falls = cannons.map((c) => ({ c, from: c.y, to: restY(c.x) }));
    const longest = Math.max(...falls.map((f) => f.to - f.from));
    return animate(id, (longest / 240) * 1000, (t) => {
      for (const f of falls) f.c.y = Math.min(f.to, f.from + t * longest);
    });
  }

  // Calls step(t) with t going 0 → 1 over ms milliseconds, redrawing each frame.
  // Resolves false if the game was closed or restarted meanwhile.
  async function animate(id, ms, step) {
    const start = performance.now();
    animating++;
    try {
      for (;;) {
        const t = ms > 0 ? Math.min(1, (performance.now() - start) / ms) : 1;
        step(t);
        draw();
        if (t >= 1) return true;
        await frame();
        if (id !== gameId) return false;
      }
    } finally {
      animating--;
    }
  }

  // --- Drawing ---
  function draw() {
    ctx.fillStyle = colors.sky;
    ctx.fillRect(0, 0, W, H);

    ctx.fillStyle = colors.trail;
    for (const c of cannons) {
      if (!c.trail) continue;
      for (let i = 0; i < c.trail.length; i += 4) {
        ctx.beginPath(); ctx.arc(c.trail[i][0], c.trail[i][1], 1.5, 0, 7); ctx.fill();
      }
    }

    ctx.beginPath();
    ctx.moveTo(0, H);
    for (let x = 0; x < W; x++) ctx.lineTo(x, ground[x]);
    ctx.lineTo(W, H);
    ctx.closePath();
    ctx.fillStyle = colors.ground;
    ctx.fill();
    ctx.beginPath();
    for (let x = 0; x < W; x++) ctx.lineTo(x, ground[x]);
    ctx.strokeStyle = colors.edge;
    ctx.lineWidth = 2;
    ctx.stroke();

    if (aim) {
      ctx.fillStyle = current().color;
      for (let i = 0; i < aim.length; i += 3) {
        ctx.beginPath(); ctx.arc(aim[i][0], aim[i][1], 2, 0, 7); ctx.fill();
      }
    }
    STREAMER_POLES.forEach(drawStreamer);
    if (crate) drawCrate();
    cannons.forEach(drawCannon);

    if (ball) {
      ctx.fillStyle = colors.ink;
      ctx.beginPath(); ctx.arc(ball[0], ball[1], 4, 0, 7); ctx.fill();
    }
    if (boom) {
      ctx.fillStyle = colors.brass;
      ctx.globalAlpha = 0.85;
      ctx.beginPath(); ctx.arc(boom.x, boom.y, boom.r, 0, 7); ctx.fill();
      ctx.globalAlpha = 1;
    }

    ctx.font = "700 20px 'Source Sans 3', system-ui, sans-serif";
    ctx.textAlign = "center";
    for (const p of popups) {
      ctx.fillStyle = p.color;
      ctx.globalAlpha = 1 - p.rise * 0.6;
      ctx.fillText(p.text, p.x, p.y - p.rise * 30);
    }
    ctx.globalAlpha = 1;

    drawWind();
    drawHealth();
    if (message) {
      ctx.fillStyle = colors.ink;
      ctx.font = `600 ${over ? 30 : 20}px Rokkitt, Georgia, serif`;
      ctx.textAlign = "center";
      ctx.fillText(message, W / 2, over ? H * 0.2 : 32);
      if (over) {
        ctx.font = "16px 'Source Sans 3', system-ui, sans-serif";
        ctx.fillStyle = colors.edge;
        ctx.fillText("Space or “New game” to play again", W / 2, H * 0.2 + 28);
      }
    }
  }

  // The logo artwork, with the player's colour in place of brass. A destroyed cannon is faded, its barrel drooping.
  function drawCannon(c) {
    const isTurn = c.alive && !over && c === current();
    ctx.save();
    ctx.translate(c.x, c.y);
    if (isTurn) {
      ctx.fillStyle = colors.brass;
      const top = -(PIVOT_DY + BARREL + 14);
      ctx.beginPath(); ctx.moveTo(-6, top - 8); ctx.lineTo(6, top - 8); ctx.lineTo(0, top); ctx.closePath(); ctx.fill();
    }
    if (!c.alive) ctx.globalAlpha = 0.4;
    ctx.scale(c.dir * LOGO_SCALE, LOGO_SCALE);
    ctx.translate(-LOGO_ORIGIN[0], -LOGO_ORIGIN[1]);
    const circle = (x, y, r, fill) => { ctx.fillStyle = fill; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); };

    ctx.save();
    ctx.translate(LOGO_PIVOT[0], LOGO_PIVOT[1]);
    ctx.rotate((-(c.alive ? c.angle : -12) * Math.PI) / 180);
    ctx.translate(-LOGO_PIVOT[0], -LOGO_PIVOT[1]);
    ctx.fillStyle = colors.ink;
    ctx.fill(BARREL_PATH);
    ctx.fillStyle = c.color;
    ctx.beginPath(); ctx.roundRect(89, 59, 8, 24, 2); ctx.fill();
    ctx.fillRect(60, 61, 4, 20);
    circle(32, 71, 9, colors.ink);
    circle(22, 71, 4.5, c.color);
    ctx.restore();

    ctx.strokeStyle = colors.ink;
    ctx.lineWidth = 5;
    circle(50, 84, 17, colors.sky);
    ctx.stroke();
    ctx.lineWidth = 2.5;
    ctx.stroke(SPOKES_PATH);
    circle(50, 84, 4.5, c.color);
    ctx.restore();
  }

  function drawWind() {
    const shown = Math.round(wind / 4);
    ctx.fillStyle = colors.edge;
    ctx.font = "600 14px 'Source Sans 3', system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(shown === 0 ? "No wind" : `Wind ${Math.abs(shown)}`, W - 16, H - 14);
    if (shown === 0) return;
    const len = 6 + Math.abs(wind) * 0.8, y = H - 34, x0 = W - 60 - (wind > 0 ? len / 2 : -len / 2), x1 = x0 + Math.sign(wind) * len;
    ctx.strokeStyle = colors.edge;
    ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y);
    ctx.moveTo(x1 - Math.sign(wind) * 7, y - 5); ctx.lineTo(x1, y); ctx.lineTo(x1 - Math.sign(wind) * 7, y + 5);
    ctx.stroke();
  }

  // A pole planted in the ground (it sinks into any crater) with a ribbon blowing off its top. The ribbon swings
  // from hanging straight down to nearly level as the wind rises, and ripples faster and wider.
  function drawStreamer(px) {
    const base = ground[px], top = base - POLE;
    ctx.strokeStyle = colors.ink;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(px, base); ctx.lineTo(px, top); ctx.stroke();

    const s = Math.abs(wind) / MAX_WIND, dir = Math.sign(wind) || 1, t = performance.now() / 1000;
    const lean = s * 1.4, speed = 3 + 12 * s, ripple = 0.12 + 0.3 * s, segs = 10, seg = STREAMER / segs;
    let x = px, y = top + 2;
    ctx.strokeStyle = colors.brass;
    ctx.lineCap = "round";
    for (let i = 1; i <= segs; i++) {
      const f = i / segs;
      const a = lean + ripple * f * Math.sin(t * speed - f * 5 + px);   // angle from hanging straight down
      const nx = x + dir * Math.sin(a) * seg, ny = y + Math.cos(a) * seg;
      ctx.lineWidth = 6 * (1 - f) + 1.5;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(nx, ny); ctx.stroke();
      x = nx; y = ny;
    }
    ctx.lineCap = "butt";
    ctx.fillStyle = colors.ink;
    ctx.beginPath(); ctx.arc(px, top, 2.5, 0, 7); ctx.fill();
  }

  // A brass box with the power-up's symbol and, below it, its name.
  function drawCrate() {
    const { x, y, kind } = crate, s = CRATE;
    ctx.fillStyle = colors.brass;
    ctx.strokeStyle = colors.ink;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.roundRect(x - s, y - s, 2 * s, 2 * s, 4); ctx.fill(); ctx.stroke();
    ctx.fillStyle = ctx.strokeStyle = colors.ink;
    ctx.beginPath();
    if (kind === "repair") { ctx.fillRect(x - 2, y - 7, 4, 14); ctx.fillRect(x - 7, y - 2, 14, 4); }
    else if (kind === "big") { ctx.arc(x, y, 7, 0, 7); ctx.fill(); }
    else { ctx.arc(x, y, 6, 0, 7); ctx.moveTo(x - 9, y); ctx.lineTo(x + 9, y); ctx.moveTo(x, y - 9); ctx.lineTo(x, y + 9); ctx.stroke(); }
    ctx.fillStyle = colors.edge;
    ctx.font = "600 12px 'Source Sans 3', system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(PERKS[kind], x, y + s + 14);
  }

  // Each player's name and health bar, in their own top corner, with any power-up they hold below.
  function drawHealth() {
    const bw = 140, bh = 10, y = 34;
    ctx.font = "600 14px 'Source Sans 3', system-ui, sans-serif";
    cannons.forEach((c, i) => {
      const x = i === 0 ? 16 : W - 16 - bw;
      ctx.fillStyle = colors.edge;
      ctx.textAlign = i === 0 ? "left" : "right";
      ctx.fillText(`${c.name} ${c.hp}`, i === 0 ? x : x + bw, y - 8);
      ctx.fillStyle = c.color;
      ctx.fillRect(x, y, (bw * c.hp) / MAX_HP, bh);
      ctx.strokeStyle = colors.edge;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x, y, bw, bh);
      if (c.perk) {
        ctx.fillStyle = colors.edge;
        ctx.fillText(`${PERKS[c.perk]} ready`, i === 0 ? x : x + bw, y + bh + 16);
      }
    });
  }

  // --- Helpers ---
  function sync() {
    const c = current();
    els.angle.value = c.angle; els.power.value = c.power;
    els.angleOut.value = c.angle; els.powerOut.value = c.power;
    const locked = !canAim();
    aim = null;
    if (!locked && c.perk === "sights") {
      aim = [];
      simulate(c, c.angle, c.power, wind, aim);
      aim.length = Math.ceil(aim.length * 0.4);
    }
    els.angle.disabled = els.power.disabled = els.fire.disabled = locked;
    draw();
  }

  function nextQuestion() {
    let i;
    do i = Math.floor(Math.random() * QUESTIONS.length); while (i === qIndex);
    qIndex = i;
    els.question.textContent = QUESTIONS[i];
  }

  const current = () => cannons[turn];
  const isCpu = () => !els.twop.checked;
  const canAim = () => !busy && !over;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const frame = () => new Promise(requestAnimationFrame);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
})();

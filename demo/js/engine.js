/* engine.js — scripted timeline scheduler + event bus.
   The whole demo is one deterministic screenplay: an ordered list of steps,
   each with a delay from the previous one. The engine plays it, supports
   pause/resume, speed, restart, and loops at the end. Views subscribe to
   named events on the bus; nothing talks to a server. */

"use strict";

export const bus = (() => {
  const subs = new Map();
  return {
    on(type, fn) {
      if (!subs.has(type)) subs.set(type, []);
      subs.get(type).push(fn);
    },
    emit(type, payload) {
      (subs.get(type) || []).forEach(fn => fn(payload));
      (subs.get("*") || []).forEach(fn => fn(type, payload));
    },
  };
})();

export class Engine {
  constructor(script, { loopDelay = 6000 } = {}) {
    this.script = script;        // [{ wait: ms, run: (bus) => void }, ...]
    this.loopDelay = loopDelay;
    this.speed = 1.6;
    this.playing = false;
    this._idx = 0;
    this._timer = null;
    this._epoch = 0;             // bumped on restart to cancel stale timers
  }

  play() {
    if (this.playing) return;
    this.playing = true;
    bus.emit("engine:state", { playing: true });
    this._next();
  }

  pause() {
    this.playing = false;
    clearTimeout(this._timer);
    bus.emit("engine:state", { playing: false });
  }

  toggle() { this.playing ? this.pause() : this.play(); }

  setSpeed(mult) { this.speed = Number(mult) || 1; }

  restart() {
    clearTimeout(this._timer);
    this._idx = 0;
    this._epoch++;
    bus.emit("engine:restart");
    this.playing = true;
    bus.emit("engine:state", { playing: true });
    this._next();
  }

  _next() {
    if (!this.playing) return;
    const epoch = this._epoch;

    if (this._idx >= this.script.length) {
      // End of screenplay — breathe, then loop from a clean slate.
      this._timer = setTimeout(() => {
        if (epoch !== this._epoch) return;
        this.restart();
      }, this.loopDelay / this.speed);
      return;
    }

    const step = this.script[this._idx];
    this._timer = setTimeout(() => {
      if (epoch !== this._epoch) return;
      this._idx++;
      try { step.run(bus); } catch (e) { console.error("demo step failed", e); }
      this._next();
    }, (step.wait ?? 600) / this.speed);
  }
}

/* Typewriter: streams `text` into `el` char-by-char, returns a promise.
   Speed follows the engine multiplier via the cps argument. */
export function typewrite(el, text, { cps = 55, speed = 1 } = {}) {
  return new Promise(resolve => {
    let i = 0;
    const cursor = document.createElement("span");
    cursor.className = "cursor";
    el.appendChild(cursor);
    const tick = () => {
      const step = Math.max(1, Math.round((cps * speed) / 30));
      i = Math.min(text.length, i + step);
      cursor.insertAdjacentText("beforebegin", text.slice(cursor.dataset.done?.length || 0, i));
      cursor.dataset.done = text.slice(0, i);
      if (i < text.length) setTimeout(tick, 1000 / 30);
      else { cursor.remove(); resolve(); }
    };
    tick();
  });
}

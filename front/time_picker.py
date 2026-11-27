"""Sélecteur d'heure à roulettes (composant Streamlit personnalisé).

Un seul bloc « HH : MM », comme sur un téléphone : on fait défiler la roulette
des heures (00 à 23) et celle des minutes (00, 15, 30, 45) ; la valeur au
centre, dans la bande en surbrillance, est celle retenue. Molette, doigt,
clic maintenu et tiré vers le haut ou le bas (avec élan), clic sur une valeur
ou flèches du clavier. Les roulettes tournent en boucle : après 23 vient 00,
après 45 vient 00.

La valeur ("07:45") est renvoyée à Python avec le reste du formulaire, au
moment où il est envoyé. Code de confiance écrit ici : aucune donnée saisie
par l'utilisateur n'est injectée dans le HTML (seuls un libellé fixe et
l'heure "HH:MM" sont passés)."""

from datetime import time as dtime

import streamlit as st

_CSS = """
.label {
  font-family: var(--st-font, sans-serif);
  color: var(--st-text-color, #31333f);
  font-size: 14px;
  margin-bottom: 8px;
}
.picker {
  /* Teinte neutre tirée de la couleur du texte : douce en thème clair comme en sombre. */
  --band: color-mix(in srgb, var(--ink) 9%, transparent);
  --soft: color-mix(in srgb, var(--ink) 35%, transparent);
  --ink: var(--st-text-color, #31333f);
  --field: var(--st-secondary-background-color, #f0f2f6);
  --item: 36px;
  font-family: var(--st-font, sans-serif);
  color: var(--ink);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: calc(var(--item) * 5);
  background: var(--field);
  border-radius: 10px;
  user-select: none;
}
/* Bande du milieu : la valeur retenue. */
.picker::before {
  content: "";
  position: absolute;
  left: 8px;
  right: 8px;
  top: calc(50% - var(--item) / 2);
  height: var(--item);
  border-radius: 8px;
  background: var(--band);
  pointer-events: none;
}
.wheel {
  height: 100%;
  width: 64px;
  overflow-y: scroll;
  scroll-snap-type: y mandatory;
  scrollbar-width: none;
  outline: none;
  /* Les valeurs s'estompent en s'éloignant du centre. */
  mask-image: linear-gradient(transparent, #000 35%, #000 65%, transparent);
  -webkit-mask-image: linear-gradient(transparent, #000 35%, #000 65%, transparent);
}
.wheel::-webkit-scrollbar { display: none; }
.wheel { cursor: grab; }
.wheel.grabbing { cursor: grabbing; }
.wheel:focus-visible { box-shadow: inset 0 0 0 1.5px var(--soft); border-radius: 8px; }
.pad { height: calc(var(--item) * 2); }
.item {
  height: var(--item);
  line-height: var(--item);
  text-align: center;
  font-size: 18px;
  scroll-snap-align: center;
  opacity: 0.45;
  transition: opacity 0.15s, transform 0.15s;
}
.item.selected { opacity: 1; font-size: 22px; font-weight: 600; }
.sep { font-size: 24px; font-weight: 600; }
"""

_JS = """
export default function (component) {
  const { data, setStateValue, parentElement } = component;
  const pad = (n) => String(n).padStart(2, "0");
  const HOURS = Array.from({ length: 24 }, (_, i) => i);
  const MINUTES = [0, 15, 30, 45];
  let [hour, minute] = (data.value || "08:00").split(":").map(Number);
  if (!MINUTES.includes(minute)) minute = 0;

  parentElement.querySelector(".time-picker")?.remove();
  const wrapper = document.createElement("div");
  wrapper.className = "time-picker";
  const title = Object.assign(document.createElement("div"), { className: "label", textContent: data.label || "" });
  const root = document.createElement("div");
  root.className = "picker";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", data.label || "Heure");
  wrapper.append(title, root);
  parentElement.appendChild(wrapper);

  let commitTimer = null;
  const commit = () => {
    clearTimeout(commitTimer);
    commitTimer = setTimeout(() => setStateValue("time", `${pad(hour)}:${pad(minute)}`), 150);
  };

  // Roulette en boucle : la liste est répétée plusieurs fois et, une fois la
  // roulette arrêtée, on revient sans saut visible sur la copie du milieu.
  // 23 est donc suivi de 00, et 00 précédé de 23 (45 / 00 pour les minutes).
  function wheel(values, current, label, onChange) {
    const n = values.length;
    const copies = Math.max(9, Math.ceil(160 / n) | 1); // nombre impair, au moins 160 lignes
    const middle = Math.floor(copies / 2) * n;
    const box = document.createElement("div");
    box.className = "wheel";
    box.tabIndex = 0;
    box.setAttribute("role", "listbox");
    box.setAttribute("aria-label", label);
    box.append(Object.assign(document.createElement("div"), { className: "pad" }));
    const items = [];
    for (let c = 0; c < copies; c++) {
      for (const v of values) {
        const item = document.createElement("div");
        item.className = "item";
        item.textContent = pad(v);
        item.setAttribute("role", "option");
        box.append(item);
        items.push(item);
      }
    }
    box.append(Object.assign(document.createElement("div"), { className: "pad" }));

    const rowHeight = () => items[0].getBoundingClientRect().height || 36;
    let index = middle + Math.max(0, values.indexOf(current));
    const select = (i) => {
      index = Math.min(items.length - 1, Math.max(0, i));
      box.querySelector(".item.selected")?.classList.remove("selected");
      items[index].classList.add("selected");
      box.setAttribute("aria-valuetext", items[index].textContent);
      onChange(values[index % n]);
    };
    const scrollToIndex = (i, smooth) => box.scrollTo({ top: i * rowHeight(), behavior: smooth ? "smooth" : "auto" });

    // Retour discret sur la copie du milieu quand la roulette s'arrête.
    let settleTimer = null;
    const recenter = () => {
      const same = middle + (index % n);
      if (same !== index) { select(same); scrollToIndex(same, false); }
    };

    box.addEventListener("scroll", () => {
      const i = Math.round(box.scrollTop / rowHeight());
      if (i !== index) { select(i); commit(); }
      clearTimeout(settleTimer);
      settleTimer = setTimeout(() => { if (!dragging && !animating) recenter(); }, 200);
    });

    // Glisser à la souris (maintenir le clic et tirer) : défilement continu,
    // élan au relâchement, puis calage sur la valeur la plus proche. Au doigt,
    // le défilement natif du navigateur fait déjà tout cela.
    let dragging = false, animating = false, moved = false, lastY = 0, lastT = 0, velocity = 0, frame = null;
    const stopAnimation = () => { if (frame) cancelAnimationFrame(frame); frame = null; animating = false; };
    const snap = () => {
      box.style.scrollSnapType = "";
      scrollToIndex(Math.round(box.scrollTop / rowHeight()), true);
    };
    box.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      stopAnimation();
      dragging = true; moved = false;
      lastY = e.clientY; lastT = performance.now(); velocity = 0;
      box.style.scrollSnapType = "none";
      box.setPointerCapture(e.pointerId);
      box.classList.add("grabbing");
    });
    box.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const now = performance.now(), dy = e.clientY - lastY;
      if (Math.abs(dy) > 0) moved = true;
      box.scrollTop -= dy;
      velocity = -dy / Math.max(1, now - lastT); // pixels par milliseconde
      lastY = e.clientY; lastT = now;
    });
    const release = () => {
      if (!dragging) return;
      dragging = false;
      box.classList.remove("grabbing");
      if (!moved) { snap(); return; }
      // Élan : la vitesse décroît jusqu'à l'arrêt, puis calage.
      animating = true;
      let v = performance.now() - lastT > 80 ? 0 : velocity, prev = performance.now();
      const step = (now) => {
        const dt = now - prev; prev = now;
        box.scrollTop += v * dt;
        v *= Math.pow(0.993, dt);
        if (Math.abs(v) > 0.02) { frame = requestAnimationFrame(step); return; }
        stopAnimation();
        snap();
      };
      frame = requestAnimationFrame(step);
    };
    box.addEventListener("pointerup", release);
    box.addEventListener("pointercancel", release);

    // Clic simple sur une valeur visible : elle vient au centre.
    items.forEach((it, k) => it.addEventListener("click", () => { if (!moved) scrollToIndex(k, true); }));
    box.addEventListener("keydown", (e) => {
      const step = { ArrowDown: 1, ArrowUp: -1, PageDown: 4, PageUp: -4 }[e.key];
      if (step) { e.preventDefault(); scrollToIndex(index + step, true); }
    });

    select(index);
    // Position de départ, une fois la roulette affichée.
    requestAnimationFrame(() => scrollToIndex(index, false));
    return box;
  }

  const sep = Object.assign(document.createElement("div"), { className: "sep", textContent: ":" });
  root.append(
    wheel(HOURS, hour, "Heures", (v) => { hour = v; }),
    sep,
    wheel(MINUTES, minute, "Minutes", (v) => { minute = v; }),
  );
}
"""

_picker = st.components.v2.component("roulettes_heure", css=_CSS, js=_JS)


def time_wheel(label: str, default: dtime, key: str) -> dtime:
    """Affiche le bloc « heures : minutes » à roulettes et renvoie l'heure choisie."""
    default_text = default.strftime("%H:%M")
    result = _picker(
        key=key,
        data={"label": label, "value": st.session_state.get(f"{key}-value", default_text)},
        default={"time": default_text},
        on_time_change=lambda: None,
    )
    text = result.time or default_text
    st.session_state[f"{key}-value"] = text
    hour, minute = (int(part) for part in text.split(":"))
    return dtime(hour, minute)

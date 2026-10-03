// Draws the dashboard charts from the JSON the page carries (#dash-data). Plain SVG, no
// libraries, so it works on a kiosk network without internet. Every chart also has a table.
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const css = (name) => getComputedStyle(document.querySelector(".dash")).getPropertyValue(name).trim();

  function svg(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    if (parent) parent.appendChild(el);
    return el;
  }

  function niceMax(max) {
    if (max <= 0) return 1;
    const step = Math.pow(10, Math.floor(Math.log10(max)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= max) return m * step;
    return 10 * step;
  }

  function ticks(max, count) {
    const out = [];
    for (let i = 0; i <= count; i++) out.push((max / count) * i);
    return out;
  }

  const fmtNumber = (v) => (Math.round(v * 10) / 10).toLocaleString();
  const fmtMoney = (v) => "$" + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // a bar with a 4px rounded data end and a square end on the baseline
  function barPath(x, y, w, h, roundTop) {
    const r = Math.min(4, w / 2, h);
    if (!roundTop || r <= 0) return `M${x},${y}h${w}v${h}h${-w}z`;
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}z`;
  }
  function hbarPath(x, y, w, h) {
    const r = Math.min(4, h / 2, w);
    if (r <= 0) return `M${x},${y}h${w}v${h}h${-w}z`;
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}z`;
  }

  function tooltip(host) {
    const tip = document.createElement("div");
    tip.className = "dash-tip";
    tip.hidden = true;
    host.appendChild(tip);
    return {
      show(html, x, y) {
        tip.innerHTML = html;
        tip.hidden = false;
        const w = tip.offsetWidth, hostW = host.clientWidth;
        tip.style.left = Math.max(0, Math.min(x + 12, hostW - w)) + "px";
        tip.style.top = Math.max(0, y - tip.offsetHeight - 8) + "px";
      },
      hide() { tip.hidden = true; },
    };
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const swatch = (color) => `<i style="background:${color}"></i>`;

  function legend(host, series) {
    if (series.length < 2) return;
    const ul = document.createElement("ul");
    ul.className = "dash-legend";
    for (const s of series) ul.insertAdjacentHTML("beforeend", `<li>${swatch(s.color)}${esc(s.name)}</li>`);
    host.appendChild(ul);
  }

  function empty(host, text) {
    host.innerHTML = `<p class="dash-empty">${esc(text)}</p>`;
  }

  // Columns along a category axis; several series are stacked.
  function columns(host, { labels, tipLabels, series, rows, fmt, height, emptyText, labelEvery }) {
    host.innerHTML = "";
    const totals = rows.map((r) => series.reduce((sum, s) => sum + (r[s.key] || 0), 0));
    if (!totals.some((t) => t > 0)) return empty(host, emptyText);
    legend(host, series);
    const W = host.clientWidth, H = height || 200;
    const m = { top: 8, right: 4, bottom: 22, left: 44 };
    const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
    const max = niceMax(Math.max(...totals));
    const y = (v) => m.top + plotH - (v / max) * plotH;
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img" }, host);
    for (const t of ticks(max, 4)) {
      svg("line", { class: t ? "grid" : "baseline", x1: m.left, x2: W - m.right, y1: y(t), y2: y(t) }, root);
      svg("text", { x: m.left - 6, y: y(t) + 4, "text-anchor": "end" }, root).textContent = fmt(t, true);
    }
    const band = plotW / rows.length;
    const bw = Math.max(2, Math.min(24, band - 2));
    const every = labelEvery || Math.ceil(rows.length / Math.max(1, Math.floor(plotW / 48)));
    const tip = tooltip(host);
    rows.forEach((r, i) => {
      const x = m.left + band * i + (band - bw) / 2;
      const g = svg("g", {}, root);
      let base = 0;
      const drawn = series.filter((s) => r[s.key] > 0);
      drawn.forEach((s, j) => {
        const v = r[s.key];
        const y0 = y(base), y1 = y(base + v);
        // 2px surface gap between stacked segments
        const gap = j > 0 ? 2 : 0;
        const h = Math.max(0, y0 - y1 - gap);
        if (h > 0) svg("path", { class: "mark", d: barPath(x, y1, bw, h, j === drawn.length - 1), fill: s.color }, g);
        base += v;
      });
      if (i % every === 0) {
        svg("text", { x: m.left + band * i + band / 2, y: H - 6, "text-anchor": "middle" }, root).textContent = labels[i];
      }
      const hit = svg("rect", { class: "hit", x: m.left + band * i, y: m.top, width: band, height: plotH }, root);
      hit.addEventListener("mousemove", (e) => {
        const box = host.getBoundingClientRect();
        const lines = series.map((s) => `<div>${swatch(s.color)}${esc(s.name)}: ${fmt(r[s.key] || 0)}</div>`).join("");
        const total = series.length > 1 ? `<div>Total: ${fmt(totals[i])}</div>` : "";
        tip.show(`<b>${esc((tipLabels || labels)[i])}</b>${lines}${total}`, e.clientX - box.left, e.clientY - box.top);
        g.querySelectorAll(".mark").forEach((p) => p.classList.add("on"));
      });
      hit.addEventListener("mouseleave", () => { tip.hide(); g.querySelectorAll(".mark").forEach((p) => p.classList.remove("on")); });
    });
  }

  // Horizontal bars, one series, value at the tip.
  function bars(host, { rows, fmt, color, emptyText, colors }) {
    host.innerHTML = "";
    if (!rows.length || !rows.some((r) => r.value > 0)) return empty(host, emptyText);
    const W = host.clientWidth, rowH = 28;
    const labelW = Math.min(200, W * 0.4);
    const valueW = 56;
    const H = rows.length * rowH;
    const max = Math.max(...rows.map((r) => r.value));
    const plotW = W - labelW - valueW;
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img" }, host);
    svg("line", { class: "baseline", x1: labelW, x2: labelW, y1: 0, y2: H }, root);
    const tip = tooltip(host);
    rows.forEach((r, i) => {
      const yTop = i * rowH + (rowH - 16) / 2;
      const label = svg("text", { x: labelW - 8, y: yTop + 12, "text-anchor": "end", class: "value" }, root);
      // about 6px a character at 11px; the full name is in the tooltip and the table
      const fit = Math.floor((labelW - 8) / 6);
      label.textContent = r.label.length > fit ? r.label.slice(0, fit - 1) + "…" : r.label;
      const w = max ? (r.value / max) * plotW : 0;
      const fill = (colors && colors[i]) || color;
      if (w > 0) svg("path", { class: "mark", d: hbarPath(labelW, yTop, w, 16), fill }, root);
      svg("text", { x: labelW + w + 6, y: yTop + 12, class: "value" }, root).textContent = fmt(r.value);
      const hit = svg("rect", { class: "hit", x: 0, y: i * rowH, width: W, height: rowH }, root);
      hit.addEventListener("mousemove", (e) => {
        const box = host.getBoundingClientRect();
        tip.show(`<b>${esc(r.label)}</b>${swatch(fill)}${fmt(r.value)}${r.note ? " " + esc(r.note) : ""}`, e.clientX - box.left, e.clientY - box.top);
      });
      hit.addEventListener("mouseleave", () => tip.hide());
    });
  }

  // Lines over time with optional limit lines (e.g. a fridge's safe maximum).
  function lines(host, { series, limits, fmt, emptyText, height }) {
    host.innerHTML = "";
    series = series.filter((s) => s.points.length);
    if (!series.length) return empty(host, emptyText);
    legend(host, series);
    const W = host.clientWidth, H = height || 220;
    const m = { top: 8, right: 8, bottom: 22, left: 44 };
    const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
    const times = series.flatMap((s) => s.points.map((p) => p[0]));
    const t0 = Math.min(...times), t1 = Math.max(...times, t0 + 3600e3);
    const values = series.flatMap((s) => s.points.map((p) => p[1])).concat(limits.map((l) => l.value));
    let lo = Math.floor(Math.min(...values) - 1), hi = Math.ceil(Math.max(...values) + 1);
    const x = (t) => m.left + ((t - t0) / (t1 - t0)) * plotW;
    const y = (v) => m.top + plotH - ((v - lo) / (hi - lo)) * plotH;
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img" }, host);
    const step = Math.max(1, Math.ceil((hi - lo) / 4));
    for (let v = lo; v <= hi; v += step) {
      svg("line", { class: v === lo ? "baseline" : "grid", x1: m.left, x2: W - m.right, y1: y(v), y2: y(v) }, root);
      svg("text", { x: m.left - 6, y: y(v) + 4, "text-anchor": "end" }, root).textContent = fmt(v, true);
    }
    const dayMs = 86400e3;
    const nDays = Math.max(1, Math.round((t1 - t0) / dayMs));
    const everyDays = Math.ceil(nDays / Math.max(1, Math.floor(plotW / 64)));
    const first = new Date(t0); first.setHours(0, 0, 0, 0);
    for (let d = new Date(first.getTime() + dayMs), i = 0; d.getTime() <= t1; d = new Date(d.getTime() + dayMs), i++) {
      if (i % everyDays) continue;
      svg("text", { x: x(d.getTime()), y: H - 6, "text-anchor": "middle" }, root).textContent =
        d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    }
    for (const l of limits) {
      svg("line", { class: "limit", x1: m.left, x2: W - m.right, y1: y(l.value), y2: y(l.value) }, root);
      svg("text", { x: W - m.right, y: y(l.value) - 4, "text-anchor": "end", class: "value" }, root).textContent = l.label;
    }
    for (const s of series) {
      // break the line where readings are missing for more than two hours
      let d = "", prev = null;
      for (const [t, v] of s.points) {
        d += (prev === null || t - prev > 2 * 3600e3 ? "M" : "L") + x(t).toFixed(1) + "," + y(v).toFixed(1);
        prev = t;
      }
      svg("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, root);
      const [lt, lv] = s.points[s.points.length - 1];
      svg("circle", { cx: x(lt), cy: y(lv), r: 4, fill: s.color, stroke: css("--surface"), "stroke-width": 2 }, root);
    }
    const cross = svg("line", { class: "crosshair", y1: m.top, y2: m.top + plotH, visibility: "hidden" }, root);
    const tip = tooltip(host);
    const hit = svg("rect", { class: "hit", x: m.left, y: m.top, width: plotW, height: plotH }, root);
    hit.addEventListener("mousemove", (e) => {
      const box = host.getBoundingClientRect();
      const t = t0 + ((e.clientX - box.left - m.left) / plotW) * (t1 - t0);
      let nearest = null;
      for (const s of series) for (const p of s.points) if (!nearest || Math.abs(p[0] - t) < Math.abs(nearest - t)) nearest = p[0];
      cross.setAttribute("x1", x(nearest)); cross.setAttribute("x2", x(nearest)); cross.setAttribute("visibility", "visible");
      const rowsHtml = series.map((s) => {
        const p = s.points.find((q) => q[0] === nearest);
        return p ? `<div>${swatch(s.color)}${esc(s.name)}: ${fmt(p[1])}</div>` : "";
      }).join("");
      const when = new Date(nearest).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
      tip.show(`<b>${esc(when)}</b>${rowsHtml}`, e.clientX - box.left, e.clientY - box.top);
    });
    hit.addEventListener("mouseleave", () => { tip.hide(); cross.setAttribute("visibility", "hidden"); });
  }

  function draw() {
    const data = JSON.parse(document.getElementById("dash-data").textContent);
    const at = (name) => document.querySelector(`[data-chart="${name}"]`);
    const slot = (n) => css(`--series-${n}`);
    const day = (iso) => new Date(iso + "T00:00:00");
    const dayLabels = data.daily.map((d) => day(d.date).toLocaleDateString(undefined, { day: "numeric", month: "short" }));
    const dayTips = data.daily.map((d) => day(d.date).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }));

    columns(at("daily-status"), {
      labels: dayLabels, tipLabels: dayTips, rows: data.daily, fmt: (v) => fmtNumber(v),
      emptyText: "No orders in this period.",
      series: [
        { key: "COLLECTED", name: "Collected", color: slot(1) },
        { key: "PAID", name: "Paid, not collected", color: slot(2) },
        { key: "PENDING", name: "Waiting for payment", color: slot(3) },
        { key: "CANCELLED", name: "Cancelled", color: css("--neutral") },
      ],
    });
    columns(at("daily-revenue"), {
      labels: dayLabels, tipLabels: dayTips, rows: data.daily, height: 160,
      fmt: (v, axis) => (axis ? "$" + fmtNumber(v) : fmtMoney(v)),
      emptyText: "No paid orders in this period.",
      series: [{ key: "revenue", name: "Revenue", color: slot(1) }],
    });
    columns(at("hourly"), {
      labels: data.hourly.map((_, h) => String(h).padStart(2, "0")),
      tipLabels: data.hourly.map((_, h) => `${String(h).padStart(2, "0")}:00 to ${String(h + 1).padStart(2, "0")}:00`),
      rows: data.hourly.map((v) => ({ orders: v })), height: 180, labelEvery: 3, fmt: (v) => fmtNumber(v),
      emptyText: "No orders in this period.",
      series: [{ key: "orders", name: "Orders", color: slot(1) }],
    });
    bars(at("drinks"), {
      rows: data.drinks.map((d) => ({ label: d.name, value: d.cups })), color: slot(1),
      fmt: (v) => fmtNumber(v), emptyText: "No paid orders in this period.",
    });
    bars(at("cancellations"), {
      rows: data.cancellations.map((c) => ({ label: c.who, value: c.orders })), color: slot(1),
      fmt: (v) => fmtNumber(v), emptyText: "No cancelled orders in this period.",
    });
    bars(at("grades"), {
      rows: data.grades.map((g) => ({ label: g.grade.length === 1 ? "Grade " + g.grade : g.grade, value: g.cups })),
      color: slot(1), fmt: (v) => fmtNumber(v), emptyText: "No paid orders in this period.",
    });
    bars(at("stock"), {
      rows: data.stock.map((s) => ({ label: s.name, value: s.days_left, note: "days left" })),
      color: slot(1), fmt: (v) => fmtNumber(v) + " d",
      emptyText: "No orders used any stock in this period.",
    });
    const limits = [...new Set(data.temperatures.map((t) => t.max_c).filter((v) => v !== null))]
      .map((v) => ({ value: v, label: `Safe limit ${v} °C` }));
    lines(at("temperatures"), {
      series: data.temperatures.slice(0, 8).map((t, i) => ({
        name: t.name, color: slot(i + 1), points: t.points.map(([iso, v]) => [Date.parse(iso), v]),
      })),
      limits, fmt: (v, axis) => (axis ? v + "°" : v.toFixed(1) + " °C"),
      emptyText: "No fridge readings yet. They arrive from the kiosk's sensors once the edge service runs.",
    });
  }

  function start() {
    document.querySelectorAll("[data-autosubmit]").forEach((el) =>
      el.addEventListener("change", () => el.form.requestSubmit()));
    draw();
    let width = window.innerWidth, timer;
    window.addEventListener("resize", () => {
      if (window.innerWidth === width) return;
      width = window.innerWidth;
      clearTimeout(timer);
      timer = setTimeout(draw, 150);
    });
    // redraw when the admin's theme toggle changes the colours
    new MutationObserver(draw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

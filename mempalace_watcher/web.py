from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
from threading import Thread
from urllib.parse import parse_qs, urlparse
import os

from .config import AppConfig
from .service import WatcherService


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>MemPalace Watcher</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

    :root {
      color-scheme: dark;
      --bg: #020617;
      --bg2: #07111f;
      --panel: rgba(15, 23, 42, 0.78);
      --panel-strong: rgba(10, 16, 28, 0.96);
      --line: rgba(148, 163, 184, 0.16);
      --text: #f8fafc;
      --muted: #94a3b8;
      --fresh: #22c55e;
      --stale: #f59e0b;
      --needs: #fb7185;
      --error: #fda4af;
      --accent: #38bdf8;
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.32);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Fira Sans", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.12), transparent 30%),
        radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.1), transparent 24%),
        linear-gradient(180deg, var(--bg), var(--bg2));
      color: var(--text);
      min-height: 100vh;
    }
    .shell { max-width: 1640px; margin: 0 auto; padding: 24px; }
    .topbar {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 3vw, 42px);
      letter-spacing: -0.03em;
      line-height: 1;
      font-family: "Fira Code", Consolas, "Cascadia Mono", monospace;
    }
    .subtitle { color: var(--muted); margin-top: 8px; max-width: 70ch; }
    .toolbar { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .toolbar-stack { display: grid; justify-items: end; gap: 8px; }
    .panel-head-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .action-status { min-height: 1.2em; color: var(--muted); font-size: 13px; text-align: right; }
    .action-status.busy { color: var(--accent); }
    .action-status.ok { color: var(--fresh); }
    .action-status.error { color: var(--error); }
    .scan-banner {
      position: relative;
      overflow: hidden;
      margin-bottom: 18px;
      padding: 18px;
      border-radius: 22px;
      border: 1px solid rgba(125, 211, 252, 0.18);
      background:
        radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.16), transparent 32%),
        radial-gradient(circle at 80% 0%, rgba(34, 197, 94, 0.13), transparent 26%),
        linear-gradient(135deg, rgba(15, 23, 42, 0.88), rgba(8, 15, 28, 0.96));
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }
    .scan-banner::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.12), transparent),
        linear-gradient(180deg, transparent 45%, rgba(255,255,255,0.04), transparent 55%);
      transform: translateX(-40%);
      animation: scan-sheen 3.8s linear infinite;
      pointer-events: none;
    }
    .scan-banner .scan-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
      gap: 18px;
      position: relative;
      z-index: 1;
    }
    .scan-banner .scan-left {
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .scan-kicker {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 11px;
    }
    .scan-title {
      font-family: "Fira Code", Consolas, "Cascadia Mono", monospace;
      font-size: clamp(22px, 2.3vw, 34px);
      letter-spacing: -0.04em;
      line-height: 1.05;
    }
    .scan-subtitle { color: var(--muted); line-height: 1.55; max-width: 62ch; }
    .scan-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    .scan-meta span {
      border: 1px solid rgba(148, 163, 184, 0.16);
      background: rgba(255,255,255,0.03);
      padding: 7px 10px;
      border-radius: 999px;
    }
    .scan-visual {
      display: grid;
      gap: 12px;
      align-content: start;
      justify-items: stretch;
    }
    .scan-radar {
      position: relative;
      min-height: 132px;
      border-radius: 18px;
      border: 1px solid rgba(148, 163, 184, 0.16);
      background:
        radial-gradient(circle at center, rgba(56, 189, 248, 0.12), transparent 48%),
        radial-gradient(circle at center, rgba(255,255,255,0.05), transparent 55%),
        rgba(4, 10, 18, 0.76);
      overflow: hidden;
    }
    .scan-radar::before,
    .scan-radar::after {
      content: "";
      position: absolute;
      inset: 12%;
      border-radius: 999px;
      border: 1px solid rgba(56, 189, 248, 0.16);
      animation: radar-pulse 2.8s ease-in-out infinite;
    }
    .scan-radar::after {
      inset: 24%;
      animation-delay: .9s;
    }
    .scan-beam {
      position: absolute;
      inset: 0;
      background: conic-gradient(from 90deg, transparent, rgba(56, 189, 248, 0.18), transparent 28%);
      animation: radar-spin 5.2s linear infinite;
      mix-blend-mode: screen;
    }
    .scan-dot {
      position: absolute;
      left: 50%;
      top: 50%;
      width: 14px;
      height: 14px;
      margin-left: -7px;
      margin-top: -7px;
      border-radius: 999px;
      background: #7dd3fc;
      box-shadow: 0 0 24px #7dd3fc;
      animation: dot-breathe 1.45s ease-in-out infinite;
    }
    .scan-progress-shell {
      display: grid;
      gap: 8px;
    }
    .scan-progress {
      height: 12px;
      overflow: hidden;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.14);
      background: rgba(148, 163, 184, 0.10);
    }
    .scan-progress-fill {
      height: 100%;
      width: 0%;
      border-radius: inherit;
      background: linear-gradient(90deg, rgba(125, 211, 252, 0.95), rgba(34, 197, 94, 0.95), rgba(125, 211, 252, 0.95));
      background-size: 220% 100%;
      box-shadow: 0 0 30px rgba(56, 189, 248, 0.28);
      transition: width 180ms ease;
      animation: scan-wave 2s linear infinite;
    }
    .scan-progress-copy {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    body.scan-active .summary-hero,
    body.scan-active .panel,
    body.scan-active .scan-banner {
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.38), 0 0 0 1px rgba(56, 189, 248, 0.04) inset;
    }
    body.scan-active .metric,
    body.scan-active .scan-banner {
      animation: scan-breathe 2.2s ease-in-out infinite;
    }
    body.scan-active tbody tr.current-scan {
      background: linear-gradient(90deg, rgba(56, 189, 248, 0.11), rgba(34, 197, 94, 0.06));
      box-shadow: inset 0 0 0 1px rgba(125, 211, 252, 0.20);
    }
    body.scan-active tbody tr.current-scan td:first-child::before {
      content: "";
      position: absolute;
      inset: 8px auto 8px 8px;
      width: 3px;
      border-radius: 999px;
      background: linear-gradient(180deg, rgba(125, 211, 252, 0.9), rgba(34, 197, 94, 0.9));
      box-shadow: 0 0 18px rgba(125, 211, 252, 0.8);
    }
    body.scan-active tbody tr.current-scan td {
      position: relative;
    }
    .scan-banner .scan-grid {
      grid-template-columns: 1fr;
      gap: 12px;
    }
    .scan-banner::before {
      inset: auto -12% 0 -12%;
      height: 2px;
      background: linear-gradient(90deg, transparent, rgba(125, 211, 252, 0.42), rgba(34, 197, 94, 0.38), transparent);
      transform: translateX(-18%);
      animation: scan-line 3.8s linear infinite;
    }
    .scan-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .scan-progress-shell {
      display: grid;
      gap: 8px;
    }
    .scan-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    body.scan-active .scan-banner,
    body.scan-active .metric {
      animation: none;
    }
    button, input, textarea {
      font: inherit;
    }
    .btn {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 12px;
      cursor: pointer;
      transition: transform 160ms ease, background 160ms ease, border-color 160ms ease, color 160ms ease, opacity 160ms ease;
      box-shadow: var(--shadow);
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(125, 211, 252, 0.45); background: rgba(255,255,255,0.08); }
    .btn.primary { background: linear-gradient(135deg, rgba(125, 211, 252, 0.22), rgba(50, 213, 131, 0.18)); }
    .btn:disabled {
      cursor: progress;
      opacity: 0.72;
      transform: none;
      box-shadow: none;
    }
    .summary {
      display: grid;
      grid-template-columns: minmax(300px, 1.1fr) minmax(0, 2fr);
      gap: 12px;
      margin-bottom: 18px;
    }
    .summary-hero,
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }
    .summary-hero {
      display: grid;
      gap: 14px;
      align-content: start;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.04), transparent),
        radial-gradient(circle at top right, rgba(56, 189, 248, 0.10), transparent 35%),
        var(--panel);
    }
    .summary-kicker {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.16em;
      font-size: 11px;
    }
    .summary-total {
      font-size: clamp(42px, 5vw, 64px);
      line-height: 0.95;
      letter-spacing: -0.05em;
      font-family: "Fira Code", Consolas, "Cascadia Mono", monospace;
    }
    .summary-copy {
      color: var(--muted);
      max-width: 32ch;
      line-height: 1.55;
    }
    .summary-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .metric .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.14em; }
    .metric .value { font-size: 28px; font-weight: 700; margin-top: 2px; font-family: "Fira Code", Consolas, "Cascadia Mono", monospace; }
    .metric .foot { color: var(--muted); font-size: 13px; line-height: 1.5; }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(340px, 0.9fr);
      gap: 18px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
      overflow: hidden;
    }
    .panel-head {
      padding: 18px 18px 14px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,0.03), transparent);
    }
    .panel-head h2 { margin: 0; font-size: 16px; text-transform: uppercase; letter-spacing: 0.14em; color: var(--muted); }
    .searchbar {
      display: flex;
      gap: 10px;
      padding: 16px 18px 0;
      flex-wrap: wrap;
    }
    .searchbar input, .searchbar select, .settings input, .settings textarea {
      border: 1px solid var(--line);
      background: rgba(4, 10, 18, 0.62);
      color: var(--text);
      border-radius: 12px;
      padding: 10px 12px;
      outline: none;
    }
    .searchbar input { flex: 1 1 280px; }
    .searchbar select { min-width: 170px; }
    .table-wrap { overflow: auto; max-height: calc(100vh - 280px); }
    table { width: 100%; border-collapse: collapse; }
    thead th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: rgba(8, 15, 28, 0.95);
      color: var(--muted);
      text-align: left;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      border-bottom: 1px solid var(--line);
      padding: 12px 14px;
    }
    tbody td {
      padding: 14px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      vertical-align: top;
    }
    th:nth-child(5),
    td:nth-child(5) {
      min-width: 170px;
    }
    tbody tr {
      cursor: pointer;
      transition: background 140ms ease, transform 140ms ease;
    }
    tbody tr:hover { background: rgba(255,255,255,0.04); }
    tbody tr.selected { background: rgba(125, 211, 252, 0.09); }
    .path { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; color: var(--muted); word-break: break-all; }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid transparent;
    }
    .status::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: currentColor;
      box-shadow: 0 0 18px currentColor;
    }
    .fresh { color: var(--fresh); background: rgba(50, 213, 131, 0.08); border-color: rgba(50, 213, 131, 0.18); }
    .stale { color: var(--stale); background: rgba(253, 176, 34, 0.09); border-color: rgba(253, 176, 34, 0.18); }
    .needs-refresh { color: var(--needs); background: rgba(251, 113, 133, 0.09); border-color: rgba(251, 113, 133, 0.18); }
    .error { color: var(--error); background: rgba(253, 164, 175, 0.09); border-color: rgba(253, 164, 175, 0.18); }
    .paused { color: #cbd5e1; background: rgba(148, 163, 184, 0.08); border-color: rgba(148, 163, 184, 0.18); }
    .inspector {
      display: grid;
      gap: 14px;
    }
    .section {
      padding: 18px;
      border-bottom: 1px solid var(--line);
    }
    .section:last-child { border-bottom: 0; }
    .section-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .detail-name { font-size: 22px; margin: 0 0 8px; }
    .detail-path { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; color: var(--muted); word-break: break-all; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .chip {
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 6px 10px;
      font-size: 12px;
      color: var(--text);
      background: rgba(255,255,255,0.04);
      white-space: nowrap;
    }
    .pending-cell {
      display: grid;
      gap: 4px;
    }
    .pending-title {
      font-size: 13px;
      line-height: 1.15;
      font-weight: 700;
      white-space: nowrap;
    }
    .pending-detail {
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 11px;
      line-height: 1.2;
      color: var(--muted);
      white-space: nowrap;
      word-break: normal;
      overflow-wrap: normal;
    }
    .reasons, .events {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 8px;
    }
    .reasons li, .events li {
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--line);
      color: var(--text);
    }
    .events small { display: block; color: var(--muted); margin-top: 4px; }
    .progress-shell {
      display: grid;
      min-width: 180px;
      gap: 6px;
    }
    .progress-copy {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    .progress-track {
      position: relative;
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(148, 163, 184, 0.12);
      border: 1px solid rgba(148, 163, 184, 0.14);
    }
    .progress-fill {
      position: absolute;
      inset: 0 auto 0 0;
      width: 0%;
      border-radius: inherit;
      background: linear-gradient(90deg, rgba(125, 211, 252, 0.95), rgba(50, 213, 131, 0.95));
      transition: width 180ms linear;
    }
    .progress-shell.running .progress-fill {
      background: linear-gradient(90deg, rgba(125, 211, 252, 0.95), rgba(50, 213, 131, 0.95), rgba(125, 211, 252, 0.95));
      background-size: 200% 100%;
      animation: progress-shift 1.6s linear infinite;
    }
    .progress-shell.done .progress-fill {
      width: 100%;
    }
    .progress-shell.running .progress-copy span:last-child {
      color: var(--accent);
    }
    .progress-shell.scan .progress-track {
      background: rgba(96, 165, 250, 0.14);
      border-color: rgba(96, 165, 250, 0.22);
    }
    .progress-shell.scan .progress-fill {
      background: linear-gradient(90deg, rgba(96, 165, 250, 0.96), rgba(59, 130, 246, 0.96), rgba(34, 197, 94, 0.94));
      background-size: 220% 100%;
    }
    .progress-shell.scan .progress-copy span:first-child {
      color: #bfdbfe;
    }
    tbody tr.refreshing {
      background: linear-gradient(90deg, rgba(56, 189, 248, 0.09), rgba(34, 197, 94, 0.05));
      box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.12);
    }
    tbody tr.scanning {
      background: linear-gradient(90deg, rgba(59, 130, 246, 0.10), rgba(99, 102, 241, 0.06));
      box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.16);
    }
    .row-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      position: relative;
    }
    .menu-toggle {
      width: 40px;
      height: 40px;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      line-height: 1;
      font-family: "Fira Code", Consolas, "Cascadia Mono", monospace;
    }
    .project-menu {
      position: absolute;
      right: calc(100% + 12px);
      top: 50%;
      transform: translateY(-50%);
      min-width: 188px;
      padding: 8px;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: var(--panel-strong);
      box-shadow: var(--shadow);
      display: none;
      z-index: 40;
    }
    .project-menu.open { display: grid; gap: 6px; }
    .menu-status {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(255,255,255,0.04);
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.10em;
    }
    .menu-status span:last-child {
      color: var(--text);
    }
    .menu-status.running {
      background: rgba(56, 189, 248, 0.12);
      color: #bae6fd;
    }
    .menu-status.done {
      background: rgba(34, 197, 94, 0.12);
      color: #bbf7d0;
    }
    .menu-status.error {
      background: rgba(251, 113, 133, 0.12);
      color: #fecdd3;
    }
    .project-menu .menu-item {
      width: 100%;
      box-shadow: none;
      padding: 9px 11px;
      border-radius: 10px;
      text-align: left;
      font-size: 13px;
      background: rgba(255,255,255,0.04);
    }
    .project-menu .menu-item:hover {
      background: rgba(255,255,255,0.09);
    }
      .project-menu .menu-item.danger {
        color: #fecaca;
      }
      .project-menu .menu-item.danger:hover {
        background: rgba(251, 113, 133, 0.12);
      }
      .log-card {
        display: grid;
        gap: 10px;
        margin-top: 16px;
        padding: 16px;
        border-radius: 18px;
        border: 1px solid rgba(125, 211, 252, 0.14);
        background:
          linear-gradient(180deg, rgba(15, 23, 42, 0.78), rgba(8, 15, 28, 0.96));
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
      }
      .log-card-head {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: flex-start;
      }
      .log-card-head .section-title {
        margin-bottom: 4px;
      }
      .log-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }
      .log-status {
        min-height: 1.1em;
        color: var(--muted);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .log-status.ok { color: var(--fresh); }
      .log-status.error { color: var(--error); }
      .project-log-shell {
        overflow: hidden;
        max-height: 420px;
        opacity: 1;
        transition: max-height 220ms ease, opacity 220ms ease, transform 220ms ease;
      }
      .project-log-shell.collapsed {
        max-height: 0;
        opacity: 0;
        transform: translateY(-4px);
      }
      .project-log-scroll {
        margin: 0;
        padding: 14px;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.14);
        background: rgba(2, 6, 23, 0.76);
        color: var(--text);
        font-family: "Fira Code", Consolas, "Cascadia Mono", monospace;
        font-size: 12px;
        line-height: 1.65;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        overflow: auto;
        max-height: 360px;
      }
      @keyframes scan-line {
        0% { transform: translateX(-18%); opacity: 0.18; }
        50% { opacity: 0.82; }
        100% { transform: translateX(18%); opacity: 0.18; }
      }
    @keyframes radar-spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    @keyframes radar-pulse {
      0%, 100% { transform: scale(0.96); opacity: 0.45; }
      50% { transform: scale(1.03); opacity: 0.9; }
    }
    @keyframes dot-breathe {
      0%, 100% { transform: scale(0.85); }
      50% { transform: scale(1.12); }
    }
    @keyframes scan-wave {
      from { background-position: 0% 0%; }
      to { background-position: 220% 0%; }
    }
    @keyframes scan-breathe {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-1px); }
    }
    @keyframes progress-shift {
      from { background-position: 0% 0%; }
      to { background-position: 200% 0%; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
    }
    .settings {
      display: grid;
      gap: 10px;
    }
    .settings label { display: grid; gap: 6px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
    .settings textarea { min-height: 104px; resize: vertical; }
    .settings-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .settings-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding-top: 4px;
    }
    .toggle { display: flex; align-items: center; gap: 8px; color: var(--text); text-transform: none; letter-spacing: 0; }
    .note { color: var(--muted); font-size: 12px; line-height: 1.5; }
    .empty {
      padding: 26px 18px;
      color: var(--muted);
      text-align: center;
    }
    @media (max-width: 1200px) {
      .summary { grid-template-columns: 1fr; }
      .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .workspace { grid-template-columns: 1fr; }
      .table-wrap { max-height: none; }
    }
    @media (max-width: 720px) {
      .shell { padding: 16px; }
      .topbar { flex-direction: column; }
      .toolbar { justify-content: flex-start; }
      .summary-grid { grid-template-columns: 1fr; }
      .settings-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div>
        <h1>MemPalace Watcher</h1>
        <div class="subtitle">Discovery, drift scoring, refresh control, and local visibility for every project that keeps MemPalace data.</div>
      </div>
        <div class="toolbar-stack">
          <div class="toolbar">
            <button class="btn primary" onclick="action('/api/actions/scan', {}, 'Rescan')">Rescan</button>
          </div>
          <div id="actionStatus" class="action-status"></div>
      </div>
    </div>
    <div id="summary" class="summary"></div>
    <div id="scanBanner" class="scan-banner"></div>
    <div class="workspace">
      <div class="panel">
          <div class="panel-head">
            <h2>Projects</h2>
            <div class="panel-head-actions">
              <div class="note" id="scan-note">Live status updates every few seconds.</div>
            <button class="btn" id="refreshAllButton" onclick="refreshAllProjects(this)">Refresh all</button>
            </div>
          </div>
        <div class="searchbar">
          <input id="search" placeholder="Search by project name or path" oninput="loadProjects()" />
          <select id="statusFilter" onchange="loadProjects()">
            <option value="">All statuses</option>
            <option value="fresh">Fresh</option>
            <option value="stale">Stale</option>
            <option value="needs refresh">Needs refresh</option>
            <option value="error">Error</option>
            <option value="paused">Paused</option>
          </select>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Project</th>
                <th>Status</th>
                <th>Drift</th>
                <th>Age</th>
                <th>Pending changes</th>
                <th>Refresh</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="projects"></tbody>
          </table>
        </div>
      </div>
      <div class="panel inspector">
        <div class="section" id="detail">
          <div class="section-title">Selected project</div>
          <div class="empty">Pick a project from the table.</div>
        </div>
        <div class="section">
          <div class="section-title">Settings</div>
          <div class="settings">
            <label>
              Project roots
              <textarea id="projectRoots" placeholder="One path per line"></textarea>
            </label>
            <div class="settings-row">
              <label>
                Stale threshold hours
                <input id="staleThreshold" type="number" min="1" step="1" />
              </label>
              <label>
                Refresh threshold
                <input id="refreshThreshold" type="number" min="1" step="1" />
              </label>
              <label>
                Watch interval seconds
                <input id="watchInterval" type="number" min="10" step="10" />
              </label>
              <label>
                Server port
                <input id="serverPort" type="number" min="1" step="1" />
              </label>
            </div>
            <label class="toggle">
              <input id="autoRefresh" type="checkbox" />
              Auto refresh stale projects
            </label>
            <div class="note">Settings are stored in state/config.json. Project tracking persists across restarts per user profile.</div>
            <div class="settings-actions">
              <button class="btn primary" onclick="reloadConfig()">Save settings</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
<script>
  let selectedPath = '';
  let selectedProjectData = null;
  let openProjectMenuKey = '';
  let projectLogExpandedByPath = new Map();
  let projectLogScrollByPath = new Map();
  let projectLogStatusState = {message: '', tone: ''};
  let projectLogStatusTimer = null;
  let optimisticRefreshStates = new Map();
  let optimisticScanStates = new Map();
  let pendingScanPaths = new Set();
  let lastProjectInteractionAt = 0;
let actionStatusTimer = null;
let latestScanState = null;
let latestRefreshingPaths = [];
let latestScanningPaths = [];
let pendingRefreshPaths = new Set();

function setActionStatus(message, tone = '') {
  const status = document.getElementById('actionStatus');
  if (!status) return;
  if (actionStatusTimer) {
    clearTimeout(actionStatusTimer);
    actionStatusTimer = null;
  }
  status.className = `action-status ${tone}`.trim();
  status.textContent = message || '';
  if (message && tone !== 'error') {
    actionStatusTimer = setTimeout(() => {
      status.className = 'action-status';
      status.textContent = '';
      actionStatusTimer = null;
    }, 3500);
  }
}

function fmtHours(value) {
  if (value === null || value === undefined) return 'n/a';
  if (value < 1) return `${Math.round(value * 60)}m`;
  return `${value.toFixed(1)}h`;
}

function fmtTime(value) {
  if (!value) return 'n/a';
  return new Date(value).toLocaleString();
}

function fmtDurationMs(value) {
  if (value === null || value === undefined) return 'n/a';
  const ms = Math.max(0, Number(value) || 0);
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins ? `${hours}h ${mins}m` : `${hours}h`;
}

function pendingCopy(count, critical = 0) {
  const total = Number(count || 0);
  const criticalCount = Number(critical || 0);
  const filesLabel = total === 1 ? 'changed file' : 'changed files';
  const criticalLabel = criticalCount === 1 ? 'critical change' : 'critical changes';
  return {
    title: `${total} ${filesLabel}`,
    detail: criticalCount ? `${criticalCount} ${criticalLabel}` : 'No critical changes',
  };
}

function statusClass(status) {
  return status === 'needs refresh' ? 'needs-refresh' : status;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function jsString(value) {
  return JSON.stringify(String(value ?? ''))
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;');
}

function progressMarkup(progress = {}) {
  const active = !!progress.active;
  const percent = Math.max(0, Math.min(100, Number(progress.percent ?? 0)));
  const mode = progress.kind === 'scan' ? 'scan' : 'refresh';
  const phase = active ? (progress.phase || (mode === 'scan' ? 'Scanning' : 'Running')) : (progress.done ? (mode === 'scan' ? 'Scan complete' : 'Complete') : 'Idle');
  const predicted = Number(progress.predicted_ms ?? progress.predicted_duration_ms ?? 0);
  const lastDuration = Number(progress.last_duration_ms ?? progress.last_refresh_duration_ms ?? 0);
  const detail = active
    ? (progress.message ? escapeHtml(progress.message) : (mode === 'scan' ? 'Inspecting project' : 'Working'))
    : (progress.done && mode === 'scan'
      ? escapeHtml(progress.message || 'Scan complete')
      : (progress.done && lastDuration
        ? `Last ${fmtDurationMs(lastDuration)}`
        : predicted
          ? `Predicted ${fmtDurationMs(predicted)}`
          : (mode === 'scan' ? 'Scan complete' : 'Standing by')));
  const classes = ['progress-shell', active ? 'running' : '', progress.done ? 'done' : ''].filter(Boolean).join(' ');
  return `
    <div class="${classes}">
      <div class="progress-copy">
        <span>${escapeHtml(phase)}</span>
        <span>${active ? `${percent}%` : (progress.done ? '100%' : '0%')}</span>
      </div>
      <div class="note" style="margin: 0; text-transform: none; letter-spacing: 0; font-size: 12px;">${detail}</div>
      <div class="progress-track">
        <div class="progress-fill" style="width: ${active ? percent : (progress.done ? 100 : 0)}%"></div>
      </div>
    </div>
  `;
}

function refreshMenuMarkup(progress = {}) {
  const active = !!progress.active;
  const done = !!progress.done;
  const error = !!progress.error;
  const percent = Math.max(0, Math.min(100, Number(progress.percent ?? 0)));
  const predicted = Number(progress.predicted_ms ?? progress.predicted_duration_ms ?? 0);
  const tone = error ? 'error' : done ? 'done' : active ? 'running' : '';
  const label = error ? 'Failed' : done ? 'Complete' : active ? (progress.phase || 'Running') : 'Idle';
  const detail = error ? 'Check log' : active ? `${percent}%` : done ? '100%' : (predicted ? `ETA ${fmtDurationMs(predicted)}` : '0%');
  return `<div class="menu-status ${tone}"><span>${escapeHtml(label)}</span><span>${escapeHtml(detail)}</span></div>`;
}

function effectiveRefreshState(path, progress = {}) {
  if (progress.active || progress.done) {
    pendingRefreshPaths.delete(path);
    clearOptimisticRefreshState(path);
    return progress;
  }
  const optimistic = optimisticRefreshStates.get(path);
  if (optimistic) {
    return {
      ...progress,
      ...optimistic,
      active: optimistic.active ?? progress.active ?? false,
      done: optimistic.done ?? progress.done ?? false,
    };
  }
  if (pendingRefreshPaths.has(path)) {
    return {
      ...progress,
      active: true,
      done: false,
      percent: Math.max(Number(progress.percent ?? 0), 2),
      phase: progress.phase || 'Queued',
      message: progress.message || 'Starting refresh',
    };
  }
  return progress;
}

function setOptimisticRefreshState(path, state) {
  optimisticRefreshStates.set(path, {
    active: true,
    done: false,
    percent: 3,
    phase: 'Queued',
    message: 'Starting refresh',
    ...state,
  });
}

function clearOptimisticRefreshState(path) {
  optimisticRefreshStates.delete(path);
}

function effectiveScanState(path, scan = {}) {
  if (scan.active || scan.done) {
    pendingScanPaths.delete(path);
    clearOptimisticScanState(path);
    return scan;
  }
  const optimistic = optimisticScanStates.get(path);
  if (optimistic) {
    return {
      ...scan,
      ...optimistic,
      active: optimistic.active ?? scan.active ?? false,
      done: optimistic.done ?? scan.done ?? false,
    };
  }
  if (pendingScanPaths.has(path)) {
    return {
      ...scan,
      kind: 'scan',
      active: true,
      done: false,
      percent: Math.max(Number(scan.percent ?? 0), 2),
      phase: scan.phase || 'Queued',
      message: scan.message || 'Starting scan',
    };
  }
  return scan;
}

function displayScanState(path, scan = {}) {
  const normalized = effectiveScanState(path, scan);
  const pending = pendingScanPaths.has(path);
  const active = !!normalized.active || pending;
  const done = !!normalized.done && !active ? true : !!normalized.done;
  const phase = normalized.phase || (done ? 'Scan complete' : active ? (pending ? 'Queued' : 'Scanning') : 'Idle');
  const message = normalized.message || (done ? 'Scan complete' : active ? (pending ? 'Starting scan' : 'Inspecting project') : 'Ready to scan');
  const percent = active
    ? Math.max(2, Number(normalized.percent ?? 0) || 0)
    : (done ? 100 : Math.max(0, Number(normalized.percent ?? 0) || 0));
  return {
    ...normalized,
    kind: 'scan',
    active,
    done,
    phase,
    message,
    percent,
  };
}

function setOptimisticScanState(path, state) {
  optimisticScanStates.set(path, {
    kind: 'scan',
    active: true,
    done: false,
    percent: 5,
    phase: 'Queued',
    message: 'Starting scan',
    ...state,
  });
}

function clearOptimisticScanState(path) {
  optimisticScanStates.delete(path);
}

function markProjectInteraction() {
  lastProjectInteractionAt = Date.now();
}

function isProjectUiBusy() {
  if (openProjectMenuKey) return true;
  const active = document.activeElement;
  if (!active) return false;
  if (!active.closest?.('.workspace')) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(active.tagName) || Date.now() - lastProjectInteractionAt < 1500;
}

function scanStatusMarkup(progress = {}) {
  const active = !!progress.active;
  const done = !!progress.done;
  const error = !!progress.error;
  const percent = Math.max(0, Math.min(100, Number(progress.percent ?? 0)));
  const tone = error ? 'error' : done ? 'done' : active ? 'running' : '';
  const label = error ? 'Failed' : done ? 'Complete' : active ? (progress.phase || 'Scanning') : 'Idle';
  const detail = error ? 'Check log' : active ? `${percent}%` : done ? 'Done' : 'Standing by';
  return `<div class="menu-status ${tone}"><span>${escapeHtml(label)}</span><span>${escapeHtml(detail)}</span></div>`;
}

function scanMarkup(scan = {}) {
  const active = !!scan.active;
  const percent = Math.max(0, Math.min(100, Number(scan.percent ?? 0)));
  const total = Number(scan.total ?? 0);
  const completed = Number(scan.completed ?? 0);
  const currentName = scan.current_name || 'Idle';
  const phase = scan.phase || (active ? 'Scanning' : 'Idle');
  const message = scan.message || (active ? 'Inspecting project roots' : 'Ready to scan');
  const cadence = active ? `${completed}/${total || '—'} projects` : 'Idle';
  return `
      <div class="scan-grid">
        <div class="scan-header">
          <div class="scan-left">
            <div class="scan-kicker">Scan status</div>
            <div class="scan-title">${active ? 'Rescan running' : 'Scanner idle'}</div>
            <div class="scan-subtitle">${escapeHtml(message)}</div>
          </div>
          <div class="scan-meta">
            <span>${escapeHtml(phase)}</span>
            <span>${escapeHtml(cadence)}</span>
            <span>${active ? `Current: ${escapeHtml(currentName)}` : `Last: ${escapeHtml(scan.finished_at || scan.updated_at || 'n/a')}`}</span>
          </div>
        </div>
        <div class="scan-progress-shell">
          <div class="scan-row">
            <span>${active ? 'Scanning' : 'Standby'}</span>
            <span>${percent}%</span>
          </div>
          <div class="scan-progress">
            <div class="scan-progress-fill" style="width: ${percent}%"></div>
          </div>
        </div>
    </div>
  `;
}

function applyScanState(scan) {
  latestScanState = scan || null;
  document.body.classList.toggle('scan-active', !!scan?.active);
  const banner = document.getElementById('scanBanner');
  if (banner) {
    banner.innerHTML = scanMarkup(scan || {});
  }
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: {'Content-Type': 'application/json'},
    ...options,
  });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && parsed.error) {
        throw new Error(parsed.error);
      }
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(raw);
      }
      throw error;
    }
    throw new Error(raw);
  }
  return response.json();
}

function hideProjectMenus() {
  openProjectMenuKey = '';
  document.querySelectorAll('.project-menu.open').forEach((menu) => {
    menu.classList.remove('open');
  });
}

function toggleProjectMenu(event, key) {
  event.stopPropagation();
  const menu = document.querySelector(`.project-menu[data-menu="${key}"]`);
  if (!menu) return;
  const open = menu.classList.contains('open');
  hideProjectMenus();
  if (!open) {
    openProjectMenuKey = key;
    menu.classList.add('open');
  }
}

async function refreshProject(path, label = 'Refresh project') {
  hideProjectMenus();
  setOptimisticRefreshState(path, {
    phase: 'Queued',
    message: 'Starting refresh',
    percent: 3,
  });
  pendingRefreshPaths.add(path);
  loadProjects().catch(() => {});
  try {
    await action('/api/actions/refresh', {path}, label);
  } catch (error) {
    pendingRefreshPaths.delete(path);
    clearOptimisticRefreshState(path);
    loadProjects().catch(() => {});
    throw error;
  }
}

async function scanProject(path, label = 'Scan project') {
  hideProjectMenus();
  setOptimisticScanState(path, {
    phase: 'Queued',
    message: 'Starting scan',
    percent: 3,
  });
  pendingScanPaths.add(path);
  if (selectedPath !== path) {
    selectedPath = path;
    selectProject(path).catch(() => {});
  }
  loadProjects().catch(() => {});
  try {
    await action('/api/actions/scan-project', {path}, label);
  } catch (error) {
    pendingScanPaths.delete(path);
    clearOptimisticScanState(path);
    loadProjects().catch(() => {});
    throw error;
  }
}

async function pauseProject(path, paused) {
  hideProjectMenus();
  await action('/api/actions/pause', {path, paused}, paused ? 'Pause' : 'Resume');
}

async function openProject(path) {
  hideProjectMenus();
  await action('/api/actions/open', {path}, 'Open folder');
}

async function action(url, payload, label = 'Action') {
    setActionStatus(`${label} running...`, 'busy');
    try {
      const result = await requestJSON(url, {method: 'POST', body: JSON.stringify(payload)});
    if (result?.already_running) {
      setActionStatus(`${label} already running`, 'ok');
    } else if (Array.isArray(result?.started)) {
      setActionStatus(`${label} started: ${result.started.length} project(s)`, 'ok');
    } else if (result?.scan?.active) {
      setActionStatus(`${label} started`, 'ok');
    } else if (result?.refresh?.active) {
      setActionStatus(`${label} started`, 'ok');
    } else {
      setActionStatus(`${label} complete`, 'ok');
    }
    await refreshAll();
  } catch (error) {
    setActionStatus(`${label} failed: ${error.message}`, 'error');
    throw error;
    }
  }

  async function refreshAllProjects(button) {
    const originalLabel = button?.textContent || 'Refresh all';
    if (button) {
      button.disabled = true;
      button.textContent = 'Refreshing all...';
      button.setAttribute('aria-busy', 'true');
    }
    try {
      const result = await action('/api/actions/refresh-all', {}, 'Refresh all');
      const started = Array.isArray(result?.started) ? result.started.length : 0;
      if (started) {
        setActionStatus(`Refresh all started: ${started} project(s)`, 'ok');
      } else {
        setActionStatus('Refresh all: nothing to start', 'ok');
      }
      return result;
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalLabel;
        button.removeAttribute('aria-busy');
      }
    }
  }

  function projectLogExpanded(path) {
    return projectLogExpandedByPath.has(path) ? projectLogExpandedByPath.get(path) : true;
  }

  function setProjectLogExpanded(path, expanded) {
    projectLogExpandedByPath.set(path, !!expanded);
  }

  function rememberProjectLogScroll(path) {
    if (!path) return;
    const scroller = document.querySelector('.project-log-scroll');
    if (!scroller) return;
    projectLogScrollByPath.set(path, scroller.scrollTop);
  }

  function restoreProjectLogScroll(path) {
    if (!path) return;
    const scroller = document.querySelector('.project-log-scroll');
    if (!scroller) return;
    const remembered = projectLogScrollByPath.get(path);
    if (remembered === undefined) return;
    scroller.scrollTop = remembered;
  }

  function renderProjectLogStatus() {
    const status = document.getElementById('projectLogStatus');
    if (!status) return;
    status.className = `log-status ${projectLogStatusState.tone}`.trim();
    status.textContent = projectLogStatusState.message || '';
  }

  function clearProjectLogStatus() {
    if (projectLogStatusTimer) {
      clearTimeout(projectLogStatusTimer);
      projectLogStatusTimer = null;
    }
    projectLogStatusState = {message: '', tone: ''};
    renderProjectLogStatus();
  }

  function setProjectLogStatus(message, tone = '') {
    if (projectLogStatusTimer) {
      clearTimeout(projectLogStatusTimer);
      projectLogStatusTimer = null;
    }
    projectLogStatusState = {message: message || '', tone: tone || ''};
    renderProjectLogStatus();
    if (message) {
      projectLogStatusTimer = setTimeout(() => {
        projectLogStatusState = {message: '', tone: ''};
        renderProjectLogStatus();
        projectLogStatusTimer = null;
      }, tone === 'error' ? 5000 : 3000);
    }
  }

  function projectLogText(data) {
    if (!data) return '';
    if (typeof data.log_text === 'string' && data.log_text.trim()) {
      return data.log_text;
    }
    if (Array.isArray(data.log_lines) && data.log_lines.length) {
      return data.log_lines.join('\\n');
    }
    const lines = [];
    lines.push(`Project: ${data.name || 'n/a'}`);
    lines.push(`Path: ${data.path || 'n/a'}`);
    lines.push(`Status: ${data.last_status || data.status || 'n/a'}`);
    lines.push(`Drift: ${data.drift_score ?? 0}`);
    lines.push(`Age: ${fmtHours(data.age_hours ?? 0)}`);
    lines.push(`Last refresh: ${fmtTime(data.last_refresh)}`);
    lines.push(`Last refresh duration: ${fmtDurationMs(data.last_refresh_duration_ms)}`);
    lines.push(`Predicted refresh duration: ${fmtDurationMs(data.refresh_avg_duration_ms)}`);
    lines.push(`Refresh runs: ${data.refresh_count ?? 0}`);
    lines.push('');
    lines.push('Recent events:');
    for (const event of data.events || []) {
      const stamp = fmtTime(event.created_at);
      const duration = event.duration_ms ? ` (${event.duration_ms}ms)` : '';
      const message = event.message ? ` - ${event.message}` : '';
      lines.push(`${stamp} [${event.kind}] ${event.status}${duration}${message}`);
    }
    return lines.join('\\n');
  }

  async function copyTextToClipboard(text) {
    const payload = String(text || '');
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      try {
        await navigator.clipboard.writeText(payload);
        return;
      } catch (error) {
        // Fall through to the textarea fallback below.
      }
    }
    const textarea = document.createElement('textarea');
    textarea.value = payload;
    textarea.setAttribute('readonly', 'readonly');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch (error) {
      copied = false;
    } finally {
      textarea.remove();
    }
    if (!copied) {
      throw new Error('Clipboard copy failed');
    }
  }

  async function copySelectedProjectLog() {
    if (!selectedProjectData) {
      setProjectLogStatus('Select a project first', 'error');
      return;
    }
    try {
      await copyTextToClipboard(projectLogText(selectedProjectData));
      setProjectLogStatus('Log copied', 'ok');
    } catch (error) {
      setProjectLogStatus(`Copy failed: ${error.message}`, 'error');
      throw error;
    }
  }

  function toggleProjectLog(path) {
    if (!path) return;
    const next = !projectLogExpanded(path);
    setProjectLogExpanded(path, next);
    if (selectedProjectData && selectedProjectData.path === path) {
      renderProjectDetail(selectedProjectData);
    }
  }

  function projectLogMarkup(data) {
    const expanded = projectLogExpanded(data.path);
    const text = projectLogText(data);
    const lineCount = Array.isArray(data.log_lines) ? data.log_lines.length : (text ? text.split('\\n').length : 0);
    const buttonLabel = expanded ? 'Collapse log' : 'Expand log';
    return `
      <div class="log-card">
        <div class="log-card-head">
          <div>
            <div class="section-title">Project log</div>
            <div class="note">${lineCount ? `${lineCount} line(s) of operational history.` : 'No project log yet.'}</div>
          </div>
          <div class="log-actions">
            <button class="btn" onclick="toggleProjectLog(${jsString(data.path)})">${buttonLabel}</button>
            <button class="btn primary" onclick="copySelectedProjectLog()">Copy log</button>
          </div>
        </div>
        <div id="projectLogStatus" class="log-status ${projectLogStatusState.tone}">${escapeHtml(projectLogStatusState.message || '')}</div>
        <div class="project-log-shell ${expanded ? 'expanded' : 'collapsed'}">
          <pre class="project-log-scroll">${escapeHtml(text || 'No project log yet.')}</pre>
        </div>
      </div>
    `;
  }

  function renderProjectDetail(data) {
    if (!data) return;
    const detail = document.getElementById('detail');
    if (!detail) return;
    const path = data.path;
    if (selectedProjectData && selectedProjectData.path === path) {
      rememberProjectLogScroll(path);
    }
    const refresh = effectiveRefreshState(path, {
      ...(data.refresh || {}),
      predicted_ms: data.refresh_avg_duration_ms ?? data.last_refresh_duration_ms ?? 0,
      last_duration_ms: data.last_refresh_duration_ms ?? 0,
    });
    const scan = displayScanState(path, data.scan || {});
    selectedProjectData = data;
    detail.innerHTML = `
      <div class="section-title">Selected project</div>
      <h3 class="detail-name">${data.name}</h3>
      <div class="detail-path">${data.path}</div>
      <div class="chips">
        <span class="status ${statusClass(data.last_status || data.status || 'fresh')}">${data.last_status || data.status || 'fresh'}</span>
        <span class="chip">Drift ${data.drift_score ?? 0}</span>
        <span class="chip">Age ${fmtHours(data.age_hours ?? 0)}</span>
        <span class="chip">${pendingCopy(data.change_count, data.critical_change_count).title}</span>
        <span class="chip">${pendingCopy(data.change_count, data.critical_change_count).detail}</span>
        <span class="chip">Last refresh ${fmtTime(data.last_refresh)}</span>
        <span class="chip">Last run ${fmtDurationMs(data.last_refresh_duration_ms)}</span>
        <span class="chip">Predicted ${fmtDurationMs(data.refresh_avg_duration_ms)}</span>
        <span class="chip">Runs ${data.refresh_count ?? 0}</span>
      </div>
      <div style="margin-top: 14px;">
        ${progressMarkup(refresh)}
        ${(scan.active || scan.done) ? `<div style="margin-top: 10px;">${progressMarkup(scan)}</div>` : ''}
      </div>
      ${projectLogMarkup(data)}
    `;
    renderProjectLogStatus();
    requestAnimationFrame(() => restoreProjectLogScroll(path));
  }

async function loadSummary() {
  const data = await requestJSON('/api/summary');
  latestRefreshingPaths = Array.isArray(data.refreshing_paths) ? data.refreshing_paths.map(String) : [];
  latestScanningPaths = Array.isArray(data.scanning_paths) ? data.scanning_paths.map(String) : [];
  applyScanState(data.scan || null);
  const summary = document.getElementById('summary');
  summary.innerHTML = `
    <section class="summary-hero">
      <div class="summary-kicker">Fleet overview</div>
      <div class="summary-total">${data.total || 0}</div>
      <div class="summary-copy">Tracked projects with live refresh visibility and drift scoring.</div>
      <div class="summary-pills">
        <span class="status fresh">Fresh ${data.fresh || 0}</span>
        <span class="status needs-refresh">Needs ${data['needs refresh'] || 0}</span>
        <span class="status stale">Stale ${data.stale || 0}</span>
      </div>
    </section>
    <div class="summary-grid">
      ${[
        ['Refreshing', data.refreshing || 0, 'currently running'],
        ['Error', data.error || 0, 'failed refreshes'],
        ['Paused', data.paused || 0, 'manual exclusions'],
        ['Scanning', data.scanning || 0, 'single-project scans'],
        ['Fresh', data.fresh || 0, 'safe to ignore'],
        ['Stale', data.stale || 0, 'should be refreshed soon'],
        ['Needs refresh', data['needs refresh'] || 0, 'auto-refresh candidates'],
      ].map(([label, value, foot]) => `
        <div class="metric">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          <div class="foot">${foot}</div>
        </div>
      `).join('')}
    </div>
  `;
}

async function loadProjects() {
  const q = document.getElementById('search').value;
  const status = document.getElementById('statusFilter').value;
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (status) params.set('status', status);
  const data = await requestJSON(`/api/projects?${params.toString()}`);
  const tbody = document.getElementById('projects');
  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">No projects match the current filters.</td></tr>`;
    return;
  }
  const currentScanPath = latestScanState?.active ? String(latestScanState.current_path || '') : '';
  const refreshingPaths = new Set(latestRefreshingPaths);
  const scanningPaths = new Set(latestScanningPaths);
  tbody.innerHTML = data.map((item) => {
    const refresh = effectiveRefreshState(item.path, item.refresh);
    const scan = displayScanState(item.path, item.scan || {});
    const menuKey = encodeURIComponent(item.path);
    const menuOpen = openProjectMenuKey === menuKey;
    const scanning = scan.active || scan.done || scanningPaths.has(item.path) || pendingScanPaths.has(item.path);
    const displayProgress = scanning ? scan : refresh;
    const rowClass = [
      selectedPath === item.path ? 'selected' : '',
      currentScanPath === item.path ? ' current-scan' : '',
      refreshingPaths.has(item.path) || pendingRefreshPaths.has(item.path) ? ' refreshing' : '',
      scanning ? ' scanning' : '',
    ].join('');
    return `
    <tr class="${rowClass}" onclick="selectProject(${jsString(item.path)})">
      <td>
        <div><strong>${item.name}</strong></div>
        <div class="path">${item.path}</div>
      </td>
      <td><span class="status ${statusClass(item.status)}">${item.status}</span></td>
      <td>${item.drift_score}</td>
      <td>${fmtHours(item.age_hours)}</td>
      <td>
        <div class="pending-cell">
          <div class="pending-title">${pendingCopy(item.change_count, item.critical_change_count).title}</div>
          <div class="pending-detail">${pendingCopy(item.change_count, item.critical_change_count).detail}</div>
        </div>
      </td>
      <td>${progressMarkup(displayProgress)}</td>
      <td>
        <div class="row-actions">
          <button class="btn menu-toggle" aria-label="Project menu" onclick="toggleProjectMenu(event, ${jsString(menuKey)})">⋮</button>
          <div class="project-menu ${menuOpen ? 'open' : ''}" data-menu="${menuKey}" onclick="event.stopPropagation();">
              ${scanStatusMarkup(scan)}
              ${refreshMenuMarkup({
                ...refresh,
                predicted_ms: item.refresh_avg_duration_ms ?? item.last_refresh_duration_ms ?? 0,
                last_duration_ms: item.last_refresh_duration_ms ?? 0,
              })}
              <button class="btn menu-item" onclick="refreshProject(${jsString(item.path)}, 'Refresh memory')">Refresh memory</button>
              <button class="btn menu-item" onclick="scanProject(${jsString(item.path)}, 'Scan project')">Scan changes</button>
              <button class="btn menu-item" onclick="pauseProject(${jsString(item.path)}, ${item.paused ? 'false' : 'true'})">${item.paused ? 'Resume' : 'Pause'}</button>
              <button class="btn menu-item danger" onclick="openProject(${jsString(item.path)})">Open folder</button>
            </div>
        </div>
      </td>
    </tr>
  `;
  }).join('');
}

  async function selectProject(path) {
    if (selectedProjectData && selectedProjectData.path && selectedProjectData.path !== path) {
      rememberProjectLogScroll(selectedProjectData.path);
    }
    const changedSelection = selectedPath !== path;
    selectedPath = path;
    hideProjectMenus();
    const data = await requestJSON(`/api/project?path=${encodeURIComponent(path)}`);
    if (selectedPath !== path) return;
    if (changedSelection) {
      clearProjectLogStatus();
    }
    renderProjectDetail(data);
  }

async function loadConfig() {
  const data = await requestJSON('/api/config');
  document.getElementById('projectRoots').value = (data.project_roots || []).join('\\n');
  document.getElementById('staleThreshold').value = data.stale_threshold_hours;
  document.getElementById('refreshThreshold').value = data.refresh_threshold;
  document.getElementById('watchInterval').value = data.watch_interval_seconds;
  document.getElementById('serverPort').value = data.server_port;
  document.getElementById('autoRefresh').checked = !!data.auto_refresh;
}

async function reloadConfig() {
  const payload = {
    project_roots: document.getElementById('projectRoots').value.split('\\n').map((s) => s.trim()).filter(Boolean),
    stale_threshold_hours: Number(document.getElementById('staleThreshold').value),
    refresh_threshold: Number(document.getElementById('refreshThreshold').value),
    watch_interval_seconds: Number(document.getElementById('watchInterval').value),
    server_port: Number(document.getElementById('serverPort').value),
    auto_refresh: document.getElementById('autoRefresh').checked,
  };
  await requestJSON('/api/config', {method: 'POST', body: JSON.stringify(payload)});
  setActionStatus('Settings saved', 'ok');
  await refreshAll();
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadProjects()]);
  if (selectedPath) {
    try { await selectProject(selectedPath); } catch (_) {}
  }
}

async function refreshSummaryOnly() {
  await loadSummary();
}

function hasActiveProjectWork() {
  return latestRefreshingPaths.length > 0 || latestScanningPaths.length > 0 || pendingRefreshPaths.size > 0 || pendingScanPaths.size > 0;
}

async function refreshProjectsIfActive() {
  if (isProjectUiBusy() || !hasActiveProjectWork()) return;
  await loadProjects();
  if (selectedPath) {
    try { await selectProject(selectedPath); } catch (_) {}
  }
}

async function refreshProjectsIfIdle() {
  if (isProjectUiBusy() || hasActiveProjectWork()) return;
  await loadProjects();
  if (selectedPath) {
    try { await selectProject(selectedPath); } catch (_) {}
  }
}

async function boot() {
  await loadConfig();
  await refreshAll();
  applyScanState(latestScanState);
  setInterval(refreshSummaryOnly, 500);
  setInterval(refreshProjectsIfActive, 500);
  setInterval(refreshProjectsIfIdle, 4000);
}

boot().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<pre style="color:#fca5a5;padding:24px;">${error.stack || error}</pre>`;
});

document.addEventListener('click', hideProjectMenus);
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    hideProjectMenus();
  }
});
document.addEventListener('pointerdown', (event) => {
  if (event.target.closest?.('.workspace')) {
    markProjectInteraction();
  }
}, true);
document.addEventListener('focusin', (event) => {
  if (event.target.closest?.('.workspace')) {
    markProjectInteraction();
  }
}, true);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    service: WatcherService

    def _json(self, data: object, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/summary":
            summary = self.service.summary()
            summary["refreshing"] = self.service.active_refresh_count()
            summary["scanning"] = self.service.active_project_scan_count()
            summary["refreshing_paths"] = [
                path
                for path, state in self.service.all_refresh_states().items()
                if state.get("active")
            ]
            summary["scanning_paths"] = [
                path
                for path, state in self.service.all_project_scan_states().items()
                if state.get("active")
            ]
            summary["scan"] = self.service.scan_state()
            self._json(summary)
            return

        if parsed.path == "/api/projects":
            params = parse_qs(parsed.query)
            query = (params.get("q", [""])[0] or "").strip().lower()
            status = (params.get("status", [""])[0] or "").strip().lower()
            items = []
            for row in self.service.db.list_projects():
                item = dict(row)
                item["path"] = item["path"]
                item["status"] = "paused" if item["paused"] else (item["last_status"] or "fresh")
                item["drift_score"] = item["drift_score"] or 0
                item["age_hours"] = item["age_hours"] or 0
                item["refresh"] = self.service.refresh_state(item["path"])
                item["scan"] = self.service.project_scan_state(item["path"])
                if query and query not in item["name"].lower() and query not in item["path"].lower():
                    continue
                if status and status != item["status"].lower():
                    continue
                items.append(item)
            self._json(items)
            return

        if parsed.path == "/api/project":
            params = parse_qs(parsed.query)
            path = params.get("path", [""])[0]
            if not path:
                self._json({"error": "missing path"}, status=400)
                return
            try:
                detail = self.service.project_detail(path)
            except FileNotFoundError:
                self._json({"error": "not found"}, status=404)
                return
            detail["status"] = "paused" if detail.get("paused") else (detail.get("last_status") or "fresh")
            detail["refresh"] = self.service.refresh_state(path)
            detail["scan"] = self.service.project_scan_state(path)
            self._json(detail)
            return

        if parsed.path == "/api/config":
            self._json(self.service.config.to_dict())
            return

        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/api/actions/scan":
            state = self.service.start_scan()
            self._json({"ok": True, "scan": state})
            return
        if parsed.path == "/api/actions/scan-project":
            path = str(payload.get("path", ""))
            state = self.service.start_scan_project(path)
            self._json({"ok": True, "scan": state})
            return
        if parsed.path == "/api/actions/refresh-stale":
            state = self.service.start_refresh_stale()
            self._json(state)
            return
        if parsed.path == "/api/actions/refresh-all":
            state = self.service.start_refresh_all_projects()
            self._json(state)
            return
        if parsed.path == "/api/actions/refresh":
            path = str(payload.get("path", ""))
            if self.service.refresh_state(path).get("active"):
                self._json({"ok": True, "already_running": True, "refresh": self.service.refresh_state(path)})
                return
            state = self.service.start_refresh_project(path)
            self._json({"ok": True, "queued": True, "refresh": state})
            return
        if parsed.path == "/api/actions/pause":
            path = str(payload.get("path", ""))
            paused = bool(payload.get("paused", True))
            self.service.set_paused(path, paused)
            self._json({"ok": True})
            return
        if parsed.path == "/api/actions/open":
            path = str(payload.get("path", ""))
            if path:
                os.startfile(path)  # type: ignore[attr-defined]
            self._json({"ok": True})
            return
        if parsed.path == "/api/actions/shutdown":
            stop_event = getattr(self.server, "stop_event", None)
            if stop_event is not None:
                try:
                    stop_event.set()
                except Exception:
                    pass
            try:
                Thread(target=self.server.shutdown, daemon=True).start()
            except Exception:
                pass
            self._json({"ok": True})
            return
        if parsed.path == "/api/config":
            config = self.service.update_config(payload)
            self._json(config.to_dict())
            return
        self._json({"error": "not found"}, status=404)

    def log_message(self, *_args) -> None:
        return


def build_server(service: WatcherService, stop_event, port: int | None = None) -> ThreadingHTTPServer:
    Handler.service = service
    address = (service.config.server_host, service.config.server_port if port is None else port)
    server = ThreadingHTTPServer(address, Handler)
    server.timeout = 1
    server.stop_event = stop_event
    server.daemon_threads = True
    server.block_on_close = False
    return server

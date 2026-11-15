/* First Words: Home Assistant sidebar panel.
 *
 * Ported from the approved Apps Script UI (Index.html + App.html). The markup,
 * CSS and the recording / trim / WAV / chunked-upload logic are kept as they
 * were; what changed is the transport (hass.fetchWithAuth instead of
 * google.script.run), identity (the HA user instead of a PIN and picker), and
 * an offline queue in IndexedDB for when HA or the NAS can't be reached.
 *
 * Plain web component, no build step. The CSS and markup are joined string
 * arrays, not template literals, so the file contains no backticks at all.
 */
(function () {
'use strict';
if (customElements.get('first-words-panel')) return;

var VERSION = '0.2.4';

var CSS = [
':host{',
'  --bg:#F6F4EF; --card:#FFFFFF; --line:#ECE8DF; --line2:#D8D3C8;',
'  --ink:#1E2A3A; --muted:#5B6472; --label:#4A5260; --soft:#C9D2E0;',
'  --gold:#E9A23B; --gold-soft:#F6DDB0; --gold-ink:#6B4200;',
'  --teal-soft:#DDEFEA; --teal-ink:#1F5A4E; --blue-soft:#E4E8F6; --blue-ink:#2D3E7A;',
'  --danger:#A3261B;',
'  --display:"Bricolage Grotesque",system-ui,sans-serif;',
'  --safe-b:env(safe-area-inset-bottom,0px);',
'  display:block;position:relative;height:calc(100vh - var(--fw-top,0px));height:calc(100dvh - var(--fw-top,0px));overflow:hidden;transform:translateZ(0);',
'  background:var(--bg);color:var(--ink);color-scheme:light;',
'}',
'*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}',
'.scroller{height:100%;overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 Inter,system-ui,-apple-system,sans-serif}',
'button,input,textarea{font:inherit;color:inherit}',
'button{cursor:pointer}',
'a{color:var(--ink)}',
'[hidden]{display:none!important}',
'.app{max-width:520px;margin:0 auto;min-height:100%;position:relative}',
'.view{padding-bottom:calc(150px + var(--safe-b))}',
'.topbar{display:flex;align-items:center;gap:8px;padding:16px 12px 8px}',
'.topbar h1{margin:0;font:800 22px/1.1 var(--display);flex:1}',
'.icon-btn{width:44px;height:44px;border-radius:22px;border:none;background:transparent;display:flex;align-items:center;justify-content:center;flex:0 0 44px}',
'.icon-btn.ring{background:var(--card);border:1px solid #E2DED5}',
'.icon-btn svg{width:22px;height:22px}',
'.eyebrow{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}',
'.sub{font-size:14px;color:var(--muted)}',
'.hero{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:20px 24px 8px}',
'.hero h1{margin:2px 0;font:800 34px/1.05 var(--display)}',
'.hero .lead{display:flex;align-items:flex-start;gap:4px;min-width:0}',
'.menu{margin:-6px 0 0 -14px;color:var(--ink)}',
'.banner{margin:8px 16px 0;padding:12px 14px;border-radius:14px;background:#FBE9E7;color:var(--danger);font-size:14px;font-weight:600;line-height:1.35}',
'.banner.info{background:var(--gold-soft);color:var(--gold-ink)}',
'',
'/* list */',
'.month{margin:18px 24px 8px;font-size:13px;font-weight:600;color:var(--muted)}',
'.words{list-style:none;margin:0 16px;padding:0;display:flex;flex-direction:column;gap:8px}',
'.wcard{background:var(--card);border:1px solid var(--line);border-radius:18px;display:flex;align-items:center;gap:10px;padding:10px 12px 10px 10px}',
'.play{width:44px;height:44px;border-radius:22px;border:none;background:var(--ink);display:flex;align-items:center;justify-content:center;flex:0 0 44px}',
'.play svg{width:18px;height:18px;fill:#fff}',
'.play.off{background:#E2DED5}',
'.play.off svg{fill:#8A8F98}',
'.wopen{flex:1;min-width:0;display:flex;align-items:center;gap:8px;border:none;background:none;text-align:left;padding:4px 0;min-height:44px}',
'.wtext{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}',
'.wword{font:600 22px/1.1 var(--display);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
'.wmeta{font-size:13px;color:var(--muted)}',
'.chip{font-size:12px;font-weight:600;padding:5px 10px;border-radius:999px;white-space:nowrap;background:var(--blue-soft);color:var(--blue-ink)}',
'.chip.c0{background:var(--teal-soft);color:var(--teal-ink)}',
'.chip.both{background:linear-gradient(90deg,var(--teal-soft),var(--blue-soft));color:var(--ink)}',
'.chip.first{background:var(--gold-soft);color:var(--gold-ink)}',
'.chip.pending{background:#EFEDE8;color:var(--label)}',
'.empty{margin:48px 32px;text-align:center;color:var(--muted)}',
'.empty strong{display:block;font:800 24px/1.2 var(--display);color:var(--ink);margin-bottom:6px}',
'',
'/* bottom bar */',
'.bottombar{position:fixed;left:0;right:0;bottom:0;padding:14px 20px calc(18px + var(--safe-b));background:var(--bg);border-top:1px solid #E2DED5;z-index:5}',
'.bottombar .inner{max-width:480px;margin:0 auto;display:flex;flex-direction:column;gap:6px}',
'.cta{height:60px;border-radius:30px;border:none;background:var(--gold);color:var(--ink);display:flex;align-items:center;justify-content:center;gap:10px;font-weight:600;font-size:17px;width:100%;text-decoration:none}',
'.cta svg{width:22px;height:22px}',
'.cta.dark{background:var(--ink);color:#fff;height:56px}',
'.cta:disabled{opacity:.6}',
'.helper{font-size:12px;color:var(--muted);text-align:center}',
'.quick{height:44px;border:none;background:none;font-size:15px;font-weight:600;color:var(--ink);text-decoration:underline;text-underline-offset:3px}',
'.play.cap{background:var(--gold-soft)}',
'.play.cap svg{fill:none;stroke:var(--gold-ink);width:20px;height:20px}',
'.capture{display:flex;align-items:center;gap:12px;background:var(--bg);border:none;border-radius:20px;padding:10px 14px 10px 10px;text-align:left;width:100%;color:var(--ink)}',
'.capture .pbtn svg{fill:none;stroke:var(--ink);width:22px;height:22px}',
'.capture .tx{display:flex;flex-direction:column;gap:2px;min-width:0}',
'.capture b{font-size:16px;font-weight:600}',
'.capture small{font-size:13px;color:var(--muted)}',
'.form.attach>:not(#keep-wrap){display:none!important}',
'',
'/* clip card */',
'.clip{margin:4px 16px 0;background:var(--ink);color:#fff;border-radius:24px;padding:20px;display:flex;flex-direction:column;align-items:center;gap:14px}',
'.clip .status{font-size:13px;font-weight:600;color:var(--soft)}',
'.clip .timer{font:600 40px/1 var(--display)}',
'.recbtn{width:84px;height:84px;border-radius:42px;border:4px solid #fff;background:var(--gold);display:flex;align-items:center;justify-content:center}',
'.recbtn svg{width:32px;height:32px}',
'.recbtn .stop{width:26px;height:26px;border-radius:6px;background:var(--ink)}',
'.ghost{height:44px;padding:0 16px;border-radius:22px;border:1px solid #4A5A73;background:transparent;color:#fff;font-size:15px;font-weight:600;display:inline-flex;align-items:center;gap:8px}',
'.ghost svg{width:18px;height:18px}',
'.livewave{width:100%;height:48px;display:block}',
'.clip video{width:100%;max-height:240px;border-radius:14px;background:#000;display:block;object-fit:contain}',
'.trim{width:100%;display:flex;flex-direction:column;gap:10px}',
'.ov{position:relative;height:36px;border-radius:8px;background:#263449;touch-action:none;overflow:hidden}',
'.ov canvas,.dt canvas{position:absolute;inset:0;width:100%;height:100%;display:block}',
'.ov .win{position:absolute;top:0;bottom:0;border:2px solid var(--gold);border-radius:8px;background:rgba(233,162,59,.18)}',
'.dt{position:relative;height:84px;border-radius:12px;background:#263449;touch-action:none}',
'.dt .sel{position:absolute;top:0;bottom:0;background:rgba(233,162,59,.22);border-top:2px solid var(--gold);border-bottom:2px solid var(--gold)}',
'.dt .h{position:absolute;top:-6px;bottom:-6px;width:44px;margin-left:-22px;display:flex;justify-content:center;touch-action:none}',
'.dt .h::before{content:"";width:6px;border-radius:3px;background:var(--gold)}',
'.dt .ph{position:absolute;top:0;bottom:0;width:2px;background:#fff;pointer-events:none}',
'.trimrow{display:flex;align-items:center;gap:10px;width:100%}',
'.trimrow .len{flex:1;font-size:13px;color:var(--soft);font-variant-numeric:tabular-nums}',
'.pbtn{width:52px;height:52px;border-radius:26px;border:none;background:var(--gold);display:flex;align-items:center;justify-content:center;flex:0 0 52px}',
'.pbtn svg{width:20px;height:20px;fill:var(--ink)}',
'.tiny{font-size:12px;color:var(--soft);text-align:center}',
'',
'/* form */',
'.form{padding:16px 20px 0;display:flex;flex-direction:column;gap:12px}',
'.field{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:600;color:var(--label)}',
'.field input,.field textarea{border-radius:14px;border:1px solid var(--line2);background:var(--card);padding:0 14px;height:48px;font-size:16px;font-weight:400;color:var(--ink);width:100%;-webkit-appearance:none;appearance:none}',
'.field input.big{font-size:20px;font-weight:600}',
'.field textarea{height:auto;min-height:72px;padding:12px 14px;resize:vertical}',
'.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}',
'.seg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}',
'.seg button{height:44px;border-radius:14px;border:1px solid var(--line2);background:var(--card);font-size:15px;font-weight:600}',
'.seg button[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:#fff}',
'.toggle{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;font-size:15px}',
'.toggle input{width:22px;height:22px;accent-color:var(--ink);flex:0 0 22px}',
'',
'/* detail */',
'.dcard{margin:8px 16px 0;background:var(--card);border:1px solid var(--line);border-radius:28px;padding:28px 22px 22px;display:flex;flex-direction:column;gap:20px}',
'.dword{font:800 72px/.95 var(--display);letter-spacing:-.02em;word-break:break-word}',
'.dsound{font-size:16px;color:var(--muted);margin-top:6px}',
'.player{display:flex;align-items:center;gap:12px;background:var(--bg);border-radius:20px;padding:10px 14px 10px 10px}',
'.player canvas{flex:1;height:40px;min-width:0;display:block}',
'.player .t{font-size:13px;font-weight:600;color:var(--label);font-variant-numeric:tabular-nums}',
'.facts{margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 12px}',
'.facts dt{font-size:12px;font-weight:600;color:var(--muted)}',
'.facts dd{margin:2px 0 0;font-size:16px;font-weight:500}',
'.notes{margin:0;font-size:15px;line-height:1.45;white-space:pre-wrap}',
'.lbl{font-size:12px;font-weight:600;color:var(--muted);margin-bottom:4px}',
'.linkcard{margin:12px 16px 0;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px 16px;display:flex;align-items:center;gap:12px;text-decoration:none;width:calc(100% - 32px);text-align:left}',
'.linkcard .ic{width:40px;height:40px;border-radius:12px;background:var(--teal-soft);display:flex;align-items:center;justify-content:center;flex:0 0 40px}',
'.linkcard .ic svg{width:20px;height:20px}',
'.linkcard .tx{display:flex;flex-direction:column;gap:2px;min-width:0}',
'.linkcard b{font-size:15px;font-weight:600}',
'.linkcard small{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
'.dvideo{margin:12px 16px 0;width:calc(100% - 32px);max-height:60vh;border-radius:18px;background:#000;display:block}',
'',
'/* saved */',
'.folder{margin:8px 16px 0;background:var(--ink);color:#fff;border-radius:24px;padding:20px;display:flex;flex-direction:column;gap:14px}',
'.folder .row{display:flex;align-items:center;gap:12px}',
'.folder .ic{width:44px;height:44px;border-radius:14px;background:var(--gold);display:flex;align-items:center;justify-content:center;flex:0 0 44px}',
'.folder small{color:var(--soft);font-size:13px;word-break:break-all}',
'.h2{margin:22px 24px 8px;font-size:13px;font-weight:600;color:var(--muted)}',
'.actions{margin:0 16px;display:flex;flex-direction:column;gap:8px}',
'.action{height:52px;border-radius:16px;background:var(--card);border:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 16px;font-size:15px;font-weight:600;text-decoration:none;color:var(--ink);width:100%}',
'.action svg{width:18px;height:18px}',
'.result{margin:8px 16px 0;font-size:14px}',
'.fine{margin:20px 24px;font-size:13px;line-height:1.45;color:var(--muted)}',
'.linkbtn{border:none;background:none;padding:0;text-decoration:underline;color:var(--ink);font-size:13px;font-weight:600}',
'',
'/* dialog, toast, upload bar */',
'dialog{border:none;border-radius:24px;padding:0;width:min(440px,calc(100% - 24px));background:var(--bg);color:var(--ink);font:16px/1.4 Inter,system-ui,-apple-system,sans-serif}',
'dialog::backdrop{background:rgba(20,26,36,.45)}',
'.dlg{padding:18px 18px 20px;display:flex;flex-direction:column;gap:12px}',
'.dlg .head{display:flex;align-items:center;justify-content:space-between}',
'.dlg h2{margin:0;font:800 20px var(--display)}',
'.danger{height:48px;border-radius:14px;border:1px solid #E5C4C0;background:#fff;color:var(--danger);font-weight:600}',
'.toast{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(110px + var(--safe-b));background:var(--ink);color:#fff;padding:12px 16px;border-radius:14px;font-size:14px;max-width:calc(100% - 32px);z-index:20;box-shadow:0 6px 24px rgba(0,0,0,.2);font-family:Inter,system-ui,sans-serif}',
'.upbar{position:fixed;left:12px;right:12px;top:12px;z-index:15;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.12);display:flex;flex-direction:column;gap:8px;font-size:14px;max-width:496px;margin:0 auto;font-family:Inter,system-ui,sans-serif}',
'.upbar .bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden}',
'.upbar .bar i{display:block;height:100%;width:0;background:var(--gold);transition:width .3s}',
'.upbar .row{display:flex;justify-content:space-between;align-items:center;gap:8px}',
'.spin{width:22px;height:22px;border:3px solid #4A5A73;border-top-color:var(--gold);border-radius:50%;animation:sp 1s linear infinite}',
'@keyframes sp{to{transform:rotate(360deg)}}',
'',
'/* wide: a laptop, beside HA\'s sidebar. Sized by the panel\'s own width, not the window\'s. */',
'.scroller{container-type:inline-size;container-name:fw}',
'@container fw (min-width: 760px){',
'  .app{max-width:none}',
'  #v-list{max-width:1040px;margin:0 auto}',
'  #v-add,#v-detail,#v-saved{max-width:600px;margin:0 auto}',
'  .hero{padding:32px 32px 8px}',
'  .month{margin:24px 32px 10px}',
'  .words{margin:0 24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:10px}',
'  .banner{margin:8px 24px 0}',
'  .wcard:hover{border-color:var(--line2)}',
'  .empty{max-width:520px;margin:64px auto}',
'  .bottombar .inner{max-width:420px}',
'  .dword{font-size:88px}',
'}'
].join('\n');

var I_MIC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>';
var I_BACK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>';
var I_X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
var I_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>';
var I_VIDEO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/></svg>';
var I_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="#1F5A4E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>';

var HTML = [
'<div class="scroller" id="scroller"><div class="app">',

'  <section id="v-list" class="view" hidden>',
'    <div class="hero">',
'      <div class="lead"><span id="menu-slot" class="menu"></span><div>',
'        <span class="eyebrow">First words</span>',
'        <h1 id="list-title"></h1>',
'        <span class="sub" id="list-sub">Loading…</span>',
'      </div></div>',
'      <button class="icon-btn ring" type="button" data-go="saved" aria-label="Where it\'s saved">',
'        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 18a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 9.5a4 4 0 0 1-.5 8.5Z"/><path d="m9.5 13.5 2 2 3.5-3.5"/></svg>',
'      </button>',
'    </div>',
'    <div class="banner" id="banner" hidden role="alert"></div>',
'    <div id="list"></div>',
'    <div class="bottombar"><div class="inner">',
'      <button class="cta" type="button" data-go="add">' + I_MIC + '<span id="cta-label">Said something new</span></button>',
'      <button class="quick" type="button" data-go="quick">Just add a word · record it later</button>',
'    </div></div>',
'  </section>',

'  <section id="v-add" class="view" hidden>',
'    <div class="topbar">',
'      <button class="icon-btn" type="button" id="add-close" aria-label="Close">' + I_X + '</button>',
'      <h1 id="add-title">New word</h1>',
'    </div>',
'    <div class="clip" id="clip-card">',
'      <div id="c-empty" style="display:flex;flex-direction:column;align-items:center;gap:14px">',
'        <span class="status">Catch it while it\'s fresh</span>',
'        <button class="recbtn" type="button" id="rec-start" aria-label="Start recording">',
'          <svg viewBox="0 0 24 24" fill="none" stroke="#1E2A3A" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>',
'        </button>',
'        <span class="tiny">Tap to record</span>',
'        <label class="ghost" for="file-in">' + I_VIDEO + 'Use a video or voice memo</label>',
'        <input id="file-in" type="file" accept="video/*,audio/*" style="position:absolute;width:1px;height:1px;opacity:0;pointer-events:none">',
'      </div>',
'      <div id="c-rec" hidden style="width:100%;display:flex;flex-direction:column;align-items:center;gap:14px">',
'        <span class="status">Recording</span>',
'        <span class="timer" id="rec-time">0:00</span>',
'        <canvas class="livewave" id="live" aria-hidden="true"></canvas>',
'        <button class="recbtn" type="button" id="rec-stop" aria-label="Stop recording"><span class="stop"></span></button>',
'        <span class="tiny">Tap to stop</span>',
'      </div>',
'      <div id="c-load" hidden style="display:flex;flex-direction:column;align-items:center;gap:12px;padding:24px 0">',
'        <div class="spin" aria-hidden="true"></div>',
'        <span class="status" id="load-msg">Getting the audio…</span>',
'      </div>',
'      <div id="c-trim" class="trim" hidden>',
'        <video id="vid" playsinline preload="auto" hidden></video>',
'        <audio id="aud" preload="auto" hidden></audio>',
'        <div class="ov" id="ov" hidden aria-label="Whole video. Drag to find the moment."><canvas id="ov-c"></canvas><div class="win" id="ov-win"></div></div>',
'        <div class="dt" id="dt">',
'          <canvas id="dt-c"></canvas>',
'          <div class="sel" id="sel"></div>',
'          <div class="ph" id="ph"></div>',
'          <div class="h" id="h-start" role="slider" tabindex="0" aria-label="Clip start"></div>',
'          <div class="h" id="h-end" role="slider" tabindex="0" aria-label="Clip end"></div>',
'        </div>',
'        <div class="trimrow">',
'          <button class="pbtn" type="button" id="sel-play" aria-label="Play the clip">' + I_PLAY + '</button>',
'          <span class="len" id="sel-len">—</span>',
'          <button class="ghost" type="button" id="redo">Redo</button>',
'        </div>',
'        <span class="tiny" id="trim-hint">Drag the gold edges to keep just the word</span>',
'      </div>',
'    </div>',
'    <div class="form" id="add-form">',
'      <label class="field"><span id="f-word-lbl">What did they say?</span>',
'        <input id="f-word" class="big" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" maxlength="60">',
'      </label>',
'      <div class="grid2">',
'        <label class="field">How it sounded',
'          <input id="f-sounded" type="text" autocomplete="off" autocapitalize="none" placeholder="e.g. baw" maxlength="60">',
'        </label>',
'        <label class="field">Date',
'          <input id="f-date" type="date">',
'        </label>',
'      </div>',
'      <div class="field" role="group" aria-labelledby="heard-lbl">',
'        <span id="heard-lbl">Who heard it</span>',
'        <div class="seg" id="heard-seg"></div>',
'        <input id="f-heard-other" type="text" placeholder="Who?" hidden maxlength="40">',
'      </div>',
'      <label class="field">Notes',
'        <textarea id="f-notes" rows="2" placeholder="What was happening?" maxlength="1000"></textarea>',
'      </label>',
'      <label class="toggle" id="keep-wrap" hidden>',
'        <input type="checkbox" id="f-keep" checked>',
'        <span id="keep-label">Keep the full video too</span>',
'      </label>',
'    </div>',
'    <div class="bottombar"><div class="inner">',
'      <button class="cta dark" type="button" id="save">Save word</button>',
'      <span class="helper" id="save-helper"></span>',
'    </div></div>',
'  </section>',

'  <section id="v-detail" class="view" hidden>',
'    <div class="topbar">',
'      <button class="icon-btn" type="button" data-go="list" aria-label="Back to all words">' + I_BACK + '</button>',
'      <span class="sub" style="flex:1;text-align:center;font-weight:600" id="d-pos"></span>',
'      <button class="icon-btn" type="button" id="d-edit" aria-label="Edit">',
'        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/></svg>',
'      </button>',
'    </div>',
'    <div class="dcard">',
'      <div><div class="dword" id="d-word"></div><div class="dsound" id="d-sound"></div></div>',
'      <div class="player" id="d-player">',
'        <button class="pbtn" type="button" id="d-play" aria-label="Play recording">' + I_PLAY + '</button>',
'        <canvas id="d-wave" aria-hidden="true"></canvas>',
'        <span class="t" id="d-time"></span>',
'      </div>',
'      <button class="capture" type="button" id="d-capture" hidden>',
'        <span class="pbtn" aria-hidden="true">' + I_MIC + '</span>',
'        <span class="tx"><b>Capture it</b><small id="d-capture-sub">Record it, or pull it from a video</small></span>',
'      </button>',
'      <dl class="facts">',
'        <div><dt>Date</dt><dd id="d-date"></dd></div>',
'        <div><dt>Heard by</dt><dd id="d-heard"></dd></div>',
'        <div id="d-age-wrap"><dt id="d-age-lbl">Age</dt><dd id="d-age"></dd></div>',
'        <div><dt>Added by</dt><dd id="d-added"></dd></div>',
'      </dl>',
'      <div id="d-notes-wrap"><div class="lbl">Notes</div><p class="notes" id="d-notes"></p></div>',
'    </div>',
'    <div class="linkcard" id="d-audio-link">',
'      <span class="ic">' + I_CHECK + '</span>',
'      <span class="tx"><b id="d-saved-title">Saved</b><small id="d-audio-name"></small></span>',
'    </div>',
'    <button class="linkcard" type="button" id="d-video-link" hidden>',
'      <span class="ic" style="background:var(--gold-soft)"><svg viewBox="0 0 24 24" fill="none" stroke="#6B4200" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/></svg></span>',
'      <span class="tx"><b>Watch the video</b><small id="d-video-name">Plays here</small></span>',
'    </button>',
'    <video class="dvideo" id="d-video" controls playsinline preload="metadata" hidden></video>',
'  </section>',

'  <section id="v-saved" class="view" hidden>',
'    <div class="topbar">',
'      <button class="icon-btn" type="button" data-go="list" aria-label="Back to all words">' + I_BACK + '</button>',
'      <h1>Where it\'s saved</h1>',
'    </div>',
'    <div class="folder">',
'      <div class="row">',
'        <span class="ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1E2A3A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg></span>',
'        <span style="display:flex;flex-direction:column;gap:2px;min-width:0"><b style="font-size:17px" id="s-nas"></b><small id="s-folder-name"></small></span>',
'      </div>',
'      <div style="display:flex;align-items:center;gap:8px;font-size:14px">',
'        <svg id="s-ok" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8FD3BF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
'        <span id="s-status"></span>',
'      </div>',
'    </div>',
'    <div class="h2">Keep it forever</div>',
'    <div class="actions">',
'      <button class="action" type="button" id="s-zip">Make a backup .zip',
'        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
'      </button>',
'      <button class="action" type="button" id="s-book">Make a printable keepsake',
'        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 9V4h10v5M7 17H5a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-2M7 14h10v6H7Z"/></svg>',
'      </button>',
'    </div>',
'    <div class="result" id="s-result"></div>',
'    <p class="fine"><span id="s-fine"></span> You\'re signed in as <b id="s-who"></b>. <span id="s-ver"></span></p>',
'  </section>',
'</div></div>',

'<dialog id="edit">',
'  <form class="dlg" method="dialog" id="edit-form">',
'    <div class="head"><h2>Edit word</h2><button class="icon-btn" type="button" id="e-close" aria-label="Close">' + I_X + '</button></div>',
'    <label class="field">Word<input id="e-word" class="big" type="text" maxlength="60" autocapitalize="none"></label>',
'    <div class="grid2">',
'      <label class="field">How it sounded<input id="e-sounded" type="text" maxlength="60" autocapitalize="none"></label>',
'      <label class="field">Date<input id="e-date" type="date"></label>',
'    </div>',
'    <label class="field">Heard by<input id="e-heard" type="text" maxlength="40"></label>',
'    <label class="field">Notes<textarea id="e-notes" rows="3" maxlength="1000"></textarea></label>',
'    <button class="cta dark" type="button" id="e-save">Save changes</button>',
'    <button class="danger" type="button" id="e-delete">Delete this word</button>',
'  </form>',
'</dialog>',
'<div class="upbar" id="upbar" hidden role="status">',
'  <div class="row"><span id="up-text">Saving video…</span><button class="linkbtn" type="button" id="up-retry" hidden>Retry</button></div>',
'  <div class="bar"><i id="up-fill"></i></div>',
'</div>',
'<div class="toast" id="toast" hidden role="status"></div>'
].join('\n');

/* Fonts: @import inside a shadow root is unreliable, so load them in the document. */
function ensureFonts() {
  if (document.getElementById('first-words-fonts')) return;
  var l = document.createElement('link');
  l.id = 'first-words-fonts';
  l.rel = 'stylesheet';
  l.href = 'https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Inter:wght@400;500;600&display=swap';
  document.head.appendChild(l);
}

/* ================================================================ offline queue (IndexedDB) */
var Q = (function () {
  var dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise(function (resolve, reject) {
      if (!window.indexedDB) return reject(new Error('no indexedDB'));
      var r = indexedDB.open('first-words', 1);
      r.onupgradeneeded = function () { r.result.createObjectStore('queue', { keyPath: 'key' }); };
      r.onsuccess = function () { resolve(r.result); };
      r.onerror = function () { reject(r.error); };
    });
    dbp.catch(function () { dbp = null; });
    return dbp;
  }
  function tx(mode, fn) {
    return db().then(function (d) {
      return new Promise(function (resolve, reject) {
        var t = d.transaction('queue', mode), s = t.objectStore('queue'), out;
        var r = fn(s);
        if (r) r.onsuccess = function () { out = r.result; };
        t.oncomplete = function () { resolve(out); };
        t.onerror = t.onabort = function () { reject(t.error || new Error('IndexedDB failed')); };
      });
    });
  }
  return {
    put: function (item) { return tx('readwrite', function (s) { return s.put(item); }); },
    del: function (key) { return tx('readwrite', function (s) { return s.delete(key); }); },
    all: function () { return tx('readonly', function (s) { return s.getAll(); }).then(function (r) { return r || []; }); }
  };
})();

/* ================================================================ the app */
function createApp(host, root) {
var $ = function (id) { return root.getElementById(id); };
var C = { child: '', birthday: '', people: [], storageName: 'the NAS', offsite: '' };
function nas() { return C.storageName || 'the NAS'; }
function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
var S = { words: [], view: '', current: null, upload: null, loaded: false, storage: null, user: '', pending: [] };
var A = { mode: 'empty', clip: null, heard: '', previewing: false, raf: 0 };
var MIN_SEL = 0.2;
var WIN = 8;
var CHUNK = 256 * 1024 * 16; // 4 MB video chunks: well under HA's 16 MB request cap
var PLAY_SVG = I_PLAY;
var PAUSE_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
function uuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16);
  });
}

/* ---- transport */
function req(method, path, body, headers) {
  var init = { method: method, headers: headers || {} };
  if (body !== undefined) init.body = body;
  return Promise.resolve().then(function () {
    return host.hass.fetchWithAuth('/api/first_words' + path, init);
  }).then(function (r) {
    return r.text().then(function (t) {
      var j = null;
      try { j = t ? JSON.parse(t) : null; } catch (e) {}
      if (!r.ok) {
        var err = new Error((j && j.error) || ('Home Assistant answered ' + r.status + '.'));
        err.status = r.status; err.data = j;
        err.retryable = r.status >= 502 || r.status === 0 || (j && j.storage === 'unavailable');
        throw err;
      }
      return j;
    });
  }, function (e) {
    var err = new Error("Can't reach Home Assistant.");
    err.retryable = true; err.offline = true;
    throw err;
  });
}
function jsonReq(method, path, obj) {
  return req(method, path, JSON.stringify(obj), { 'Content-Type': 'application/json' });
}

var toastTimer = 0;
function toast(msg, ms) {
  var t = $('toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { t.hidden = true; }, ms || 3400);
}

/* ---- dates */
function todayStr() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function parseD(s) {
  var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}
function fmtDate(s, opts) {
  var d = parseD(s);
  return d ? d.toLocaleDateString('en-US', opts) : s;
}
function ageText(dateStr) {
  var b = parseD(C.birthday), d = parseD(dateStr);
  if (!b || !d || d < b) return '';
  var months = (d.getFullYear() - b.getFullYear()) * 12 + (d.getMonth() - b.getMonth());
  if (d.getDate() < b.getDate()) months--;
  var anchor = new Date(b.getFullYear(), b.getMonth() + months, b.getDate());
  var weeks = Math.floor((d - anchor) / (7 * 864e5));
  if (months < 1) return Math.floor((d - b) / (7 * 864e5)) + ' weeks';
  if (months < 24) return months + ' months' + (weeks > 0 ? ', ' + weeks + (weeks === 1 ? ' week' : ' weeks') : '');
  var y = Math.floor(months / 12), mo = months % 12;
  return y + ' years' + (mo ? ', ' + mo + ' months' : '');
}
function clock(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
}
function clockTenths(sec) {
  sec = Math.max(0, sec || 0);
  var m = Math.floor(sec / 60), s = sec - m * 60;
  return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1);
}
function mb(bytes) { var m = bytes / 1048576; return m < 10 ? m.toFixed(1) + ' MB' : Math.round(m) + ' MB'; }

/* ---- audio context (resumed inside taps so iPhones allow sound) */
var actx = null;
function getCtx() {
  // iOS mutes Web Audio while the ring switch is on silent unless the page asks to be
  // treated as media playback (Safari 17+). Without this, clips play silently.
  try { if (navigator.audioSession && navigator.audioSession.type !== 'playback') navigator.audioSession.type = 'playback'; } catch (e) {}
  if (!actx) {
    var AC = window.AudioContext || window.webkitAudioContext;
    actx = new AC();
  }
  if (actx.state === 'suspended') actx.resume();
  return actx;
}
function decode(ab) {
  return new Promise(function (resolve, reject) {
    var p = getCtx().decodeAudioData(ab, resolve, reject);
    if (p && p.then) p.then(resolve, reject);
  });
}
/* ---- pull the AAC track out of an MP4 / QuickTime (.mov) file as ADTS.
 * WebKit (iPhone Safari, the HA app) refuses decodeAudioData on a .mov even though
 * the sound inside is plain AAC, which it decodes happily once it is unwrapped.
 * Returns an ArrayBuffer of ADTS frames, or null if there's no AAC track to pull. */
function mp4AudioToAdts(ab) {
  try {
    var dv = new DataView(ab), u8 = new Uint8Array(ab);
    var fourcc = function (o) { return String.fromCharCode(u8[o], u8[o + 1], u8[o + 2], u8[o + 3]); };
    var boxes = function (start, end) {
      var out = [], o = start;
      while (o + 8 <= end) {
        var size = dv.getUint32(o), type = fourcc(o + 4), hdr = 8;
        if (size === 1) { size = dv.getUint32(o + 8) * 4294967296 + dv.getUint32(o + 12); hdr = 16; }
        else if (size === 0) size = end - o;
        if (size < hdr || o + size > end) break;
        out.push({ type: type, start: o, body: o + hdr, end: o + size });
        o += size;
      }
      return out;
    };
    var child = function (box, type) {
      var b = boxes(box.body, box.end);
      for (var i = 0; i < b.length; i++) if (b[i].type === type) return b[i];
      return null;
    };
    var path = function (box, types) {
      for (var i = 0; box && i < types.length; i++) box = child(box, types[i]);
      return box;
    };
    var moov = boxes(0, ab.byteLength).filter(function (b) { return b.type === 'moov'; })[0];
    if (!moov) return null;
    var traks = boxes(moov.body, moov.end).filter(function (b) { return b.type === 'trak'; });
    for (var t = 0; t < traks.length; t++) {
      var hdlr = path(traks[t], ['mdia', 'hdlr']);
      if (!hdlr || fourcc(hdlr.body + 8) !== 'soun') continue;
      var stbl = path(traks[t], ['mdia', 'minf', 'stbl']);
      var stsd = stbl && child(stbl, 'stsd');
      if (!stsd || fourcc(stsd.body + 12) !== 'mp4a') continue;
      // The esds sits directly in the mp4a entry (MP4) or inside its 'wave' atom (QuickTime): find it by scanning.
      var entryEnd = stsd.body + 8 + dv.getUint32(stsd.body + 8), esds = -1;
      for (var k = stsd.body + 16; k + 4 <= entryEnd; k++) if (fourcc(k) === 'esds') { esds = k + 8; break; }
      if (esds < 0) continue;
      // ES descriptor -> DecoderConfig -> DecoderSpecificInfo (AudioSpecificConfig)
      var q = esds, asc = -1;
      var desc = function () { var tag = u8[q++], len = 0, c; do { c = u8[q++]; len = (len << 7) | (c & 0x7f); } while (c & 0x80); return { tag: tag, len: len }; };
      var d = desc(); if (d.tag !== 3) continue;
      var fl = u8[q + 2]; q += 3;
      if (fl & 0x80) q += 2; if (fl & 0x40) q += 1 + u8[q]; if (fl & 0x20) q += 2;
      d = desc(); if (d.tag !== 4) continue;
      q += 13;
      d = desc(); if (d.tag !== 5) continue;
      asc = q;
      var aot = u8[asc] >> 3, sfi = ((u8[asc] & 7) << 1) | (u8[asc + 1] >> 7), ch = (u8[asc + 1] >> 3) & 15;
      if (aot < 1 || aot > 4 || sfi > 12 || ch < 1 || ch > 7) return null;  // not plain AAC: let the fallback handle it
      // sample table: sizes, chunk offsets, samples per chunk
      var stsz = child(stbl, 'stsz'), stsc = child(stbl, 'stsc'), stco = child(stbl, 'stco'), co64 = child(stbl, 'co64');
      if (!stsz || !stsc || !(stco || co64)) continue;
      var fixed = dv.getUint32(stsz.body + 4), n = dv.getUint32(stsz.body + 8);
      var sizeOf = function (i) { return fixed || dv.getUint32(stsz.body + 12 + 4 * i); };
      var co = stco || co64, nChunks = dv.getUint32(co.body + 4);
      var chunkOff = function (i) { return stco ? dv.getUint32(co.body + 8 + 4 * i) : dv.getUint32(co.body + 8 + 8 * i) * 4294967296 + dv.getUint32(co.body + 12 + 8 * i); };
      var nsc = dv.getUint32(stsc.body + 4), sc = [];
      for (var e = 0; e < nsc; e++) sc.push([dv.getUint32(stsc.body + 8 + 12 * e), dv.getUint32(stsc.body + 12 + 12 * e)]);
      var total = 0;
      for (var z = 0; z < n; z++) total += sizeOf(z) + 7;
      var out = new Uint8Array(total), w = 0, sample = 0;
      for (var c = 0; c < nChunks && sample < n; c++) {
        var per = 0;
        for (var r = 0; r < sc.length; r++) if (sc[r][0] <= c + 1) per = sc[r][1];
        var off = chunkOff(c);
        for (var j = 0; j < per && sample < n; j++, sample++) {
          var sz = sizeOf(sample), fl7 = sz + 7;
          if (off + sz > ab.byteLength) return null;
          out[w] = 0xFF; out[w + 1] = 0xF1;
          out[w + 2] = ((aot - 1) << 6) | (sfi << 2) | (ch >> 2);
          out[w + 3] = ((ch & 3) << 6) | (fl7 >> 11);
          out[w + 4] = (fl7 >> 3) & 0xFF;
          out[w + 5] = ((fl7 & 7) << 5) | 0x1F;
          out[w + 6] = 0xFC;
          out.set(u8.subarray(off, off + sz), w + 7);
          w += fl7; off += sz;
        }
      }
      return sample ? out.buffer.slice(0, w) : null;
    }
  } catch (err) { /* malformed: fall through */ }
  return null;
}
function decodeMedia(ab, isVideo) {
  // A video's sound: unwrap the AAC track first (small, and decodable everywhere).
  if (isVideo) {
    var adts = mp4AudioToAdts(ab);
    if (adts) return decode(adts).catch(function () { return decode(ab); });
    return decode(ab);
  }
  // Audio files (voice memos are .m4a): decode as-is; if refused, try unwrapping.
  return decode(ab.slice(0)).catch(function () {
    var adts = mp4AudioToAdts(ab);
    if (!adts) throw new Error('decode');
    return decode(adts);
  });
}
function monoSlice(buf, s, e) {
  var sr = buf.sampleRate, a = Math.max(0, Math.floor(s * sr)), b = Math.min(buf.length, Math.floor(e * sr));
  var n = Math.max(0, b - a), out = new Float32Array(n), chs = buf.numberOfChannels;
  for (var c = 0; c < chs; c++) {
    var d = buf.getChannelData(c);
    for (var i = 0; i < n; i++) out[i] += d[a + i] / chs;
  }
  var fade = Math.min(Math.floor(sr * 0.012), Math.floor(n / 2));
  for (var j = 0; j < fade; j++) { var g = j / fade; out[j] *= g; out[n - 1 - j] *= g; }
  return out;
}
function encodeWav(samples, sr) {
  var n = samples.length, view = new DataView(new ArrayBuffer(44 + n * 2));
  function str(o, s) { for (var i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); }
  str(0, 'RIFF'); view.setUint32(4, 36 + n * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sr, true); view.setUint32(28, sr * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); str(36, 'data'); view.setUint32(40, n * 2, true);
  for (var i = 0, o = 44; i < n; i++, o += 2) {
    var v = clamp(samples[i], -1, 1);
    view.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return new Blob([view], { type: 'audio/wav' });
}
function makePeaks(buf, pps) {
  var n = Math.max(1, Math.ceil(buf.duration * pps)), out = new Float32Array(n), step = buf.sampleRate / pps;
  for (var c = 0; c < buf.numberOfChannels; c++) {
    var d = buf.getChannelData(c);
    for (var i = 0; i < n; i++) {
      var m = out[i], a = Math.floor(i * step), b = Math.min(d.length, Math.floor((i + 1) * step));
      for (var j = a; j < b; j += 2) { var v = d[j] < 0 ? -d[j] : d[j]; if (v > m) m = v; }
      out[i] = m;
    }
  }
  var max = 0.05;
  for (var k = 0; k < n; k++) if (out[k] > max) max = out[k];
  for (var q = 0; q < n; q++) out[q] /= max;
  return out;
}
function peakAt(peaks, pps, t0, t1) {
  var a = Math.floor(t0 * pps), b = Math.max(a + 1, Math.ceil(t1 * pps)), m = 0;
  for (var i = a; i < b && i < peaks.length; i++) if (i >= 0 && peaks[i] > m) m = peaks[i];
  return m;
}
function fitCanvas(cv) {
  var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  }
  var g = cv.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  return { g: g, w: w, h: h };
}
function bar(g, x, w, h, H, color) {
  var y = (H - h) / 2;
  g.fillStyle = color;
  if (g.roundRect) { g.beginPath(); g.roundRect(x, y, w, h, w / 2); g.fill(); }
  else g.fillRect(x, y, w, h);
}

/* ================================================================ playback of saved clips */
var P = { src: null, id: null, raf: 0, onEnd: null };
var fallbackEl = new Audio();
var clipCache = new Map();

function stopPlay() {
  if (P.src) { try { P.src.onended = null; P.src.stop(); } catch (e) {} P.src = null; }
  try { fallbackEl.pause(); } catch (e) {}
  cancelAnimationFrame(P.raf);
  var cb = P.onEnd; P.id = null; P.onEnd = null;
  if (cb) cb();
}
function playBuffer(buf, from, to, id, onTick, onEnd) {
  stopPlay();
  var c = getCtx(), s = c.createBufferSource();
  s.buffer = buf; s.connect(c.destination);
  P.src = s; P.id = id; P.onEnd = onEnd;
  var t0 = c.currentTime, dur = Math.max(0.01, to - from);
  s.onended = function () { if (P.src === s) { P.src = null; stopPlay(); } };
  s.start(0, from, dur);
  (function tick() {
    if (P.src !== s) return;
    if (onTick) onTick(from + Math.min(c.currentTime - t0, dur));
    P.raf = requestAnimationFrame(tick);
  })();
}
function playEntry(entry, id, onFrac, onEnd) {
  if (entry.buf) {
    playBuffer(entry.buf, 0, entry.buf.duration, id, function (t) { if (onFrac) onFrac(t / entry.buf.duration); }, onEnd);
    return;
  }
  stopPlay();
  P.id = id; P.onEnd = onEnd;
  fallbackEl.src = entry.url;
  fallbackEl.onended = function () { if (P.id === id) stopPlay(); };
  fallbackEl.play().catch(function () { if (P.id === id) stopPlay(); });
  (function tick() {
    if (P.id !== id) return;
    if (onFrac && fallbackEl.duration && isFinite(fallbackEl.duration)) onFrac(fallbackEl.currentTime / fallbackEl.duration);
    P.raf = requestAnimationFrame(tick);
  })();
}
function decodeEntry(blob) {
  return blob.arrayBuffer().then(function (ab) {
    return decode(ab.slice(0)).then(function (buf) {
      return { buf: buf, peaks: makePeaks(buf, 100) };
    }, function () {
      return { buf: null, peaks: null, url: URL.createObjectURL(blob) };
    });
  });
}
function loadSaved(w) {
  if (clipCache.has(w.id)) return clipCache.get(w.id);
  var p;
  if (w._pending) {
    p = w._audio ? decodeEntry(w._audio) : Promise.reject(new Error('No recording.'));
  } else {
    p = Promise.resolve().then(function () {
      return host.hass.fetchWithAuth('/api/first_words/audio/' + encodeURIComponent(w.id));
    }).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) {
        throw new Error(j.error || "Couldn't load the recording.");
      });
      return r.blob();
    }, function () { throw new Error("Can't reach Home Assistant."); }).then(decodeEntry);
  }
  clipCache.set(w.id, p);
  p.catch(function () { clipCache.delete(w.id); });
  return p;
}
function setPlayIcon(btn, playing) {
  if (!btn) return;
  btn.innerHTML = playing ? PAUSE_SVG : PLAY_SVG;
  btn.setAttribute('aria-label', playing ? 'Pause' : 'Play recording');
}

/* ================================================================ navigation */
function show(v) {
  ['list', 'add', 'detail', 'saved'].forEach(function (n) { $('v-' + n).hidden = n !== v; });
  S.view = v;
  $('scroller').scrollTop = 0;
}
function go(v) {
  stopPlay();
  stopDetailVideo();
  if (v === 'add') return openAdd('new');
  if (v === 'quick') return openAdd('quick');
  if (v === 'saved') { renderSaved(); return show('saved'); }
  if (v === 'list') { leaveAdd(); renderList(); return show('list'); }
}
root.addEventListener('click', function (e) {
  var t = e.target.closest('[data-go]');
  if (t) go(t.getAttribute('data-go'));
});
function onBeforeUnload(e) {
  if (S.upload || recState) { e.preventDefault(); e.returnValue = ''; }
}
function onResize() {
  if (S.view === 'add' && A.mode === 'trim') drawTrim();
  if (S.view === 'detail') drawDetailWave(lastFrac);
}
function onVisible() {
  if (document.visibilityState !== 'visible') return;
  flushQueue();
  if (!S.synced || (S.loaded && S.view === 'list')) refresh();
}
function onOnline() { flushQueue(); if (!S.synced) refresh(); }
window.addEventListener('beforeunload', onBeforeUnload);
window.addEventListener('resize', onResize);
window.addEventListener('online', onOnline);
document.addEventListener('visibilitychange', onVisible);
var flushTimer = setInterval(function () {
  if (document.visibilityState !== 'visible') return;
  if (S.pending.length) flushQueue();
  else if (!S.synced) refresh();
}, 30000);

/* ================================================================ boot */
function me() {
  var n = String(S.user || '').toLowerCase();
  if (!n) return null;
  return C.people.filter(function (p) {
    var pn = p.name.toLowerCase();
    return pn === n || n.indexOf(pn) === 0 || pn.indexOf(n) === 0;
  })[0] || null;
}
function applyBootstrap(r) {
  S.synced = true;
  C = r.config || C;
  S.words = (r.words || []).slice();
  S.storage = r.storage || null;
  S.user = r.user || (host.hass && host.hass.user && host.hass.user.name) || '';
  S.loaded = true;
  mergePending();
  $('list-title').textContent = C.child;
  $('cta-label').textContent = C.child + ' said something new';
  $('f-word-lbl').textContent = 'What did ' + C.child + ' say?';
  $('d-age-lbl').textContent = C.child + "'s age";
  $('save-helper').textContent = saveHelper();
}
function boot() {
  $('list-title').textContent = '';
  show('list'); renderList();
  loadQueue().then(function () {
    return req('GET', '/words');
  }).then(function (r) {
    applyBootstrap(r);
    if (S.view === 'list') renderList();
    flushQueue();
  }).catch(function (e) {
    S.loaded = true;
    mergePending();
    renderList();
    $('list-sub').textContent = e.message;
  });
}
function refresh() {
  return req('GET', '/words').then(function (r) {
    applyBootstrap(r);
    if (S.view === 'list') renderList();
    else if (S.view === 'detail' && byId(S.current)) renderDetail();
  }).catch(function () {});
}

/* ================================================================ list */
function sortWords() {
  S.words.sort(function (a, b) { return (b.date + b.savedAt).localeCompare(a.date + a.savedAt); });
}
function firstWordId() {
  return S.words.length ? S.words[S.words.length - 1].id : null;
}
function clipLen(w) {
  var a = parseFloat(w.clipStart), b = parseFloat(w.clipEnd);
  return isFinite(a) && isFinite(b) && b > a ? b - a : null;
}
function hasAudio(w) { return !!(w.audioFile || w._audio); }
function renderBanner() {
  var b = $('banner'), st = S.storage, n = S.pending.length;
  if (st && !st.mounted) {
    b.className = 'banner';
    b.textContent = cap(nas()) + " isn't connected to Home Assistant right now. New words are kept on this phone and upload when it's back.";
    b.hidden = false;
  } else if (st && st.error) {
    b.className = 'banner'; b.textContent = st.error; b.hidden = false;
  } else if (n) {
    b.className = 'banner info';
    b.textContent = n + (n === 1 ? ' item is' : ' items are') + ' saved on this phone, waiting to upload.';
    b.hidden = false;
  } else {
    b.hidden = true;
  }
}
function renderList() {
  var list = $('list');
  renderBanner();
  if (!S.loaded) { $('list-sub').textContent = 'Loading…'; list.innerHTML = ''; return; }
  var n = S.words.length;
  $('list-sub').textContent = n ? n + (n === 1 ? ' word' : ' words') + ' so far · newest first' : 'No words yet';
  if (!n) {
    list.innerHTML = '<div class="empty"><strong>Listening…</strong>When ' + esc(C.child || 'they') + ' says a word, tap the button below to record it or pull the sound from a video. Words from before? Use “Just add a word” and capture them later.</div>';
    return;
  }
  var first = firstWordId(), html = '', month = '';
  S.words.forEach(function (w) {
    var m = fmtDate(w.date, { month: 'long', year: 'numeric' });
    if (m !== month) {
      if (month) html += '</ul>';
      html += '<h2 class="month">' + esc(m) + '</h2><ul class="words">';
      month = m;
    }
    var len = clipLen(w), au = hasAudio(w), cap = !au && !w._pending;
    var meta = fmtDate(w.date, { month: 'short', day: 'numeric' }) + ' · ' +
      (au ? (len ? clock(len) + ' clip' : 'clip') : 'no clip yet') + (w.videoFile || w._video ? ' · video' : '');
    var c0 = C.people[0] && w.heardBy === C.people[0].label ? ' c0' : (bothLabel() && w.heardBy === bothLabel() ? ' both' : '');
    html += '<li class="wcard">' +
      (cap
        ? '<button type="button" class="play cap" data-capture="' + esc(w.id) + '" aria-label="Capture ' + esc(w.word) + '">' + I_MIC + '</button>'
        : '<button type="button" class="play' + (au ? '' : ' off') + '" data-play="' + esc(w.id) + '" aria-label="' +
          (au ? 'Play ' + esc(w.word) : 'No recording for ' + esc(w.word)) + '"' + (au ? '' : ' disabled') + '>' + PLAY_SVG + '</button>') +
      '<button type="button" class="wopen" data-open="' + esc(w.id) + '">' +
        '<span class="wtext"><span class="wword">' + esc(w.word) + '</span><span class="wmeta">' + esc(meta) + '</span></span>' +
        (w._pending ? '<span class="chip pending">On this phone</span>' : '') +
        (w.id === first ? '<span class="chip first">First word</span>' : '') +
        (w.heardBy ? '<span class="chip' + c0 + '">' + esc(w.heardBy) + '</span>' : '') +
      '</button></li>';
  });
  html += '</ul>';
  list.innerHTML = html;
}
$('list').addEventListener('click', function (e) {
  var cb = e.target.closest('[data-capture]');
  if (cb) { stopPlay(); openAdd('attach', cb.getAttribute('data-capture')); return; }
  var pb = e.target.closest('[data-play]');
  if (pb) {
    var id = pb.getAttribute('data-play');
    if (P.id === id) { stopPlay(); return; }
    var w = byId(id);
    if (!w || !hasAudio(w)) return;
    getCtx();
    stopPlay();
    pb.style.opacity = '.6';
    loadSaved(w).then(function (entry) {
      pb.style.opacity = '';
      setPlayIcon(pb, true);
      playEntry(entry, id, null, function () { setPlayIcon(pb, false); });
    }).catch(function (err) { pb.style.opacity = ''; toast(err.message); });
    return;
  }
  var ob = e.target.closest('[data-open]');
  if (ob) openDetail(ob.getAttribute('data-open'));
});
function byId(id) {
  for (var i = 0; i < S.words.length; i++) if (S.words[i].id === id) return S.words[i];
  return null;
}
function replaceWord(w) {
  var found = false;
  for (var i = 0; i < S.words.length; i++) if (S.words[i].id === w.id) { S.words[i] = w; found = true; break; }
  if (!found) S.words.push(w);
  sortWords();
  if (S.view === 'detail' && S.current === w.id) renderDetail();
  if (S.view === 'list') renderList();
}

/* ================================================================ add: form */
/* kind: 'new' (record or trim, then the details), 'quick' (details only; capture later),
 * 'attach' (a clip for a word that was written down earlier). */
function openAdd(kind, wordId) {
  resetClip();
  var w = kind === 'attach' ? byId(wordId) : null;
  if (kind === 'attach' && !w) kind = 'new';
  A.kind = kind; A.target = w ? w.id : null;
  $('f-word').value = ''; $('f-sounded').value = ''; $('f-notes').value = '';
  $('f-date').value = todayStr(); $('f-date').max = todayStr();
  var p = me();
  A.heard = p ? p.label : (C.people[0] ? C.people[0].label : '');
  $('f-heard-other').value = ''; renderHeard();
  $('add-title').textContent = kind === 'quick' ? 'Add a word' : kind === 'attach' ? 'Capture “' + w.word + '”' : 'New word';
  $('clip-card').hidden = kind === 'quick';
  $('add-form').classList.toggle('attach', kind === 'attach');
  $('save').textContent = kind === 'attach' ? 'Save recording' : 'Save word';
  $('save-helper').textContent = kind === 'quick' ? 'Add the recording later from the word\'s page'
    : kind === 'attach' ? 'Adds the clip to “' + w.word + '” from ' + fmtDate(w.date, { month: 'short', day: 'numeric' })
    : saveHelper();
  show('add');
}
function saveHelper() { return 'Saves to ' + nas() + (C.offsite ? ' · ' + C.offsite : ''); }
function leaveAdd() {
  stopRec(true);
  stopPreview();
  if (S.view === 'add') resetClip();
}
$('add-close').addEventListener('click', function () {
  if (A.kind === 'attach' && A.target && byId(A.target)) { var id = A.target; leaveAdd(); openDetail(id); return; }
  go('list');
});
/* "Both" = every person heard it, stored readably as e.g. "Mama & Dada". */
function bothLabel() {
  if (C.people.length < 2) return '';
  var l = C.people.map(function (p) { return p.label; });
  return l.length === 2 ? l[0] + ' & ' + l[1] : l.slice(0, -1).join(', ') + ' & ' + l[l.length - 1];
}
function renderHeard() {
  var labels = C.people.map(function (p) { return p.label; }).concat(bothLabel() ? ['Both'] : []).concat(['Other']);
  var other = labels.indexOf(A.heard) === -1 || A.heard === 'Other';
  $('heard-seg').style.gridTemplateColumns = 'repeat(' + Math.min(labels.length, 4) + ',minmax(0,1fr))';
  $('heard-seg').innerHTML = labels.map(function (l) {
    var on = l === 'Other' ? other : l === A.heard;
    return '<button type="button" data-heard="' + esc(l) + '" aria-pressed="' + on + '">' + esc(l) + '</button>';
  }).join('');
  $('f-heard-other').hidden = !other;
}
$('heard-seg').addEventListener('click', function (e) {
  var b = e.target.closest('[data-heard]');
  if (!b) return;
  A.heard = b.getAttribute('data-heard');
  renderHeard();
  if (A.heard === 'Other') $('f-heard-other').focus();
});
function heardValue() {
  if (A.heard === 'Both' && bothLabel()) return bothLabel();
  if (A.heard === 'Other' || C.people.every(function (p) { return p.label !== A.heard; })) {
    return $('f-heard-other').value.trim() || 'Other';
  }
  return A.heard;
}

/* ================================================================ add: clip states */
function setMode(m) {
  A.mode = m;
  $('c-empty').hidden = m !== 'empty';
  $('c-rec').hidden = m !== 'rec';
  $('c-load').hidden = m !== 'load';
  $('c-trim').hidden = m !== 'trim';
}
function resetClip() {
  stopPreview();
  var c = A.clip;
  A.clip = null;
  if (c && c.url && !(S.upload && S.upload.file === c.blob)) URL.revokeObjectURL(c.url);
  ['vid', 'aud'].forEach(function (id) { var el = $(id); el.pause(); el.removeAttribute('src'); el.load(); });
  $('vid').hidden = true; $('ov').hidden = true; $('keep-wrap').hidden = true;
  $('file-in').value = '';
  setMode('empty');
}
$('redo').addEventListener('click', resetClip);

/* ---- recording */
var recState = null;
$('rec-start').addEventListener('click', startRec);
$('rec-stop').addEventListener('click', function () { stopRec(false); });

function pickMime() {
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
  var types = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
  for (var i = 0; i < types.length; i++) if (MediaRecorder.isTypeSupported(types[i])) return types[i];
  return '';
}
function startRec() {
  var c = getCtx();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    toast("This browser can't record here. Use “video or voice memo” instead.");
    return;
  }
  navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true } })
    .then(function (stream) {
      var mime = pickMime();
      var rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      var chunks = [];
      var an = c.createAnalyser(); an.fftSize = 1024;
      var node = c.createMediaStreamSource(stream); node.connect(an);
      recState = { rec: rec, stream: stream, an: an, node: node, t0: performance.now(), raf: 0, hist: [], cancel: false };
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = function () {
        var st = recState; recState = null;
        stream.getTracks().forEach(function (t) { t.stop(); });
        try { node.disconnect(); } catch (e) {}
        if (st) cancelAnimationFrame(st.raf);
        if (st && st.cancel) return;
        var blob = new Blob(chunks, { type: rec.mimeType || mime || 'audio/webm' });
        if (blob.size < 500) { setMode('empty'); toast('Nothing was recorded. Try again.'); return; }
        loadClip(blob, 'rec');
      };
      rec.start(200);
      setMode('rec');
      requestAnimationFrame(drawLive);
    })
    .catch(function () {
      toast('The microphone is blocked here. Allow it for the Home Assistant app in Settings, or use a video or voice memo.', 5000);
    });
}
function stopRec(cancel) {
  if (!recState) return;
  recState.cancel = !!cancel;
  if (recState.rec.state !== 'inactive') recState.rec.stop();
}
function drawLive() {
  var st = recState;
  if (!st) return;
  var el = (performance.now() - st.t0) / 1000;
  $('rec-time').textContent = clock(el);
  if (el > 90) { stopRec(false); return; }
  var data = new Float32Array(st.an.fftSize);
  st.an.getFloatTimeDomainData(data);
  var sum = 0;
  for (var i = 0; i < data.length; i++) sum += data[i] * data[i];
  st.hist.push(Math.min(1, Math.sqrt(sum / data.length) * 6));
  var f = fitCanvas($('live')), nb = Math.floor(f.w / 6);
  if (st.hist.length > nb) st.hist.splice(0, st.hist.length - nb);
  for (var k = 0; k < st.hist.length; k++) {
    bar(f.g, f.w - (st.hist.length - k) * 6, 4, Math.max(4, st.hist[k] * f.h), f.h, '#E9A23B');
  }
  st.raf = requestAnimationFrame(drawLive);
}

/* ---- file (video or voice memo) */
$('file-in').addEventListener('change', function () {
  var f = this.files && this.files[0];
  if (f) { getCtx(); loadClip(f, 'file'); }
});

function mediaReady(el) {
  return new Promise(function (resolve, reject) {
    if (el.readyState >= 1 && isFinite(el.duration) && el.duration > 0) return resolve();
    var done = false;
    function ok() { if (!done) { done = true; cleanup(); resolve(); } }
    function bad() { if (!done) { done = true; cleanup(); reject(new Error('media')); } }
    function cleanup() { el.removeEventListener('loadedmetadata', ok); el.removeEventListener('error', bad); }
    el.addEventListener('loadedmetadata', ok); el.addEventListener('error', bad);
    setTimeout(bad, 20000);
  });
}
function once(el, ev, ms) {
  return new Promise(function (resolve) {
    var t = setTimeout(done, ms);
    function done() { clearTimeout(t); el.removeEventListener(ev, done); resolve(); }
    el.addEventListener(ev, done);
  });
}

function loadClip(blob, kind) {
  var isVideo = kind === 'file' && (/^video\//.test(blob.type) ||
    (!blob.type && /\.(mov|mp4|m4v|webm|3gp)$/i.test(blob.name || '')));
  setMode('load');
  $('load-msg').textContent = isVideo ? 'Opening the video…' : 'Getting the audio…';
  var clip = { blob: blob, kind: kind, isVideo: isVideo, url: URL.createObjectURL(blob), buf: null, peaks: null,
    pps: 200, dur: 0, start: 0, end: 0, v0: 0, v1: 0 };
  clip.el = isVideo ? $('vid') : $('aud');
  var tooBig = blob.size > 250 * 1024 * 1024;

  var decoding = tooBig ? Promise.resolve(null)
    : blob.arrayBuffer().then(function (ab) { return decodeMedia(ab, isVideo); }).catch(function () { return null; });

  return decoding.then(function (buf) {
    clip.buf = buf;
    clip.el.src = clip.url;
    if (isVideo || !buf) return mediaReady(clip.el).catch(function () { if (!buf) throw new Error('open'); });
  }).then(function () {
    clip.dur = clip.buf ? clip.buf.duration : clip.el.duration;
    if (!isFinite(clip.dur) || clip.dur <= 0) throw new Error('open');
    if (clip.buf) clip.peaks = makePeaks(clip.buf, clip.pps);
    if (kind === 'rec' && clip.peaks) {
      var tr = autoTrim(clip); clip.start = tr[0]; clip.end = tr[1];
    } else if (clip.dur <= 6) {
      clip.start = 0; clip.end = clip.dur;
    } else {
      clip.start = 0; clip.end = Math.min(clip.dur, 3);
    }
    var span = Math.min(clip.dur, WIN);
    clip.v0 = 0; clip.v1 = span;
    if (clip.dur <= WIN * 1.25) { clip.v1 = clip.dur; }
    A.clip = clip;
    $('vid').hidden = !isVideo;
    $('ov').hidden = clip.v1 >= clip.dur;
    $('keep-wrap').hidden = !isVideo;
    if (isVideo) {
      $('keep-label').textContent = 'Keep the full video too (' + mb(blob.size) + ')';
      $('f-keep').checked = blob.size < 300 * 1024 * 1024;
    }
    $('trim-hint').textContent = !clip.peaks
      ? 'No waveform for this file. Play it and drag the gold edges.'
      : ($('ov').hidden ? 'Drag the gold edges to keep just the word'
        : 'Drag the top strip to find the moment, then the gold edges');
    if (tooBig) toast('Big video: it may take a while to save on cellular.', 4500);
    setMode('trim');
    requestAnimationFrame(function () { drawTrim(); if (isVideo) seek(clip.start || 0.01, true); });
  }).catch(function () {
    resetClip();
    toast("Couldn't open that file. Try another video or voice memo.", 4500);
  });
}
function autoTrim(clip) {
  var p = clip.peaks, th = 0.12, a = -1, b = -1;
  for (var i = 0; i < p.length; i++) if (p[i] > th) { if (a < 0) a = i; b = i; }
  if (a < 0) return [0, clip.dur];
  var s = Math.max(0, a / clip.pps - 0.2), e = Math.min(clip.dur, (b + 1) / clip.pps + 0.25);
  if (e - s < MIN_SEL) return [0, clip.dur];
  return [s, e];
}

/* ---- trim drawing */
function tToX(t, W) { var c = A.clip; return (t - c.v0) / (c.v1 - c.v0) * W; }
var drawQueued = false;
function queueDraw() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(function () { drawQueued = false; drawTrim(); });
}
function drawTrim() {
  var c = A.clip;
  if (!c || A.mode !== 'trim') return;
  var f = fitCanvas($('dt-c')), W = f.w, step = 5, nb = Math.floor(W / step), span = c.v1 - c.v0;
  for (var i = 0; i < nb; i++) {
    var t0 = c.v0 + i / nb * span, t1 = c.v0 + (i + 1) / nb * span;
    var amp = c.peaks ? peakAt(c.peaks, c.pps, t0, t1) : 0.18;
    var inSel = t1 > c.start && t0 < c.end;
    bar(f.g, i * step + 0.5, 3, Math.max(3, amp * (f.h - 12)), f.h, inSel ? '#E9A23B' : '#5E6E88');
  }
  var xs = tToX(c.start, W), xe = tToX(c.end, W);
  $('sel').style.left = xs + 'px';
  $('sel').style.width = Math.max(0, xe - xs) + 'px';
  $('h-start').style.left = xs + 'px';
  $('h-end').style.left = xe + 'px';
  $('h-start').setAttribute('aria-valuetext', clockTenths(c.start));
  $('h-end').setAttribute('aria-valuetext', clockTenths(c.end));
  $('sel-len').textContent = clockTenths(c.start) + ' – ' + clockTenths(c.end) + ' · ' + (c.end - c.start).toFixed(1) + ' s';
  if (!$('ov').hidden) {
    var o = fitCanvas($('ov-c')), on = Math.floor(o.w / 3);
    for (var k = 0; k < on; k++) {
      var a0 = k / on * c.dur, a1 = (k + 1) / on * c.dur;
      var am = c.peaks ? peakAt(c.peaks, c.pps, a0, a1) : 0.25;
      bar(o.g, k * 3, 2, Math.max(2, am * (o.h - 8)), o.h, '#7F8DA6');
    }
    $('ov-win').style.left = (c.v0 / c.dur * 100) + '%';
    $('ov-win').style.width = ((c.v1 - c.v0) / c.dur * 100) + '%';
  }
}
function showPh(t) {
  var c = A.clip;
  if (!c) return;
  var W = $('dt').clientWidth, x = tToX(t, W);
  $('ph').hidden = x < 0 || x > W;
  $('ph').style.left = x + 'px';
}
function hidePh() { $('ph').hidden = true; }
hidePh();

/* ---- video scrubbing */
var seekBusy = false, seekNext = null, seekTimer = 0;
function seek(t, precise) {
  var c = A.clip;
  if (!c || !c.isVideo) return;
  var el = c.el;
  if (seekBusy && !precise) { seekNext = t; return; }
  seekBusy = true;
  clearTimeout(seekTimer);
  seekTimer = setTimeout(seekDone, 400);
  if (!precise && el.fastSeek) el.fastSeek(t); else el.currentTime = t;
}
function seekDone() {
  seekBusy = false;
  if (seekNext != null) { var t = seekNext; seekNext = null; seek(t); }
}
$('vid').addEventListener('seeked', seekDone);

/* ---- trim gestures: zoomed waveform */
var drag = null;
var dt = $('dt');
dt.addEventListener('pointerdown', function (e) {
  var c = A.clip;
  if (!c) return;
  stopPreview();
  var r = dt.getBoundingClientRect(), x = e.clientX - r.left, W = r.width;
  var xs = tToX(c.start, W), xe = tToX(c.end, W), kind;
  if (e.target === $('h-start')) kind = 'start';
  else if (e.target === $('h-end')) kind = 'end';
  else if (Math.abs(x - xs) < 22 && Math.abs(x - xs) <= Math.abs(x - xe)) kind = 'start';
  else if (Math.abs(x - xe) < 22) kind = 'end';
  else if (x > xs && x < xe) kind = 'move';
  else kind = 'tap';
  drag = { kind: kind, x0: x, W: W, s0: c.start, e0: c.end, span: c.v1 - c.v0, moved: false, t: c.v0 + x / W * (c.v1 - c.v0) };
  try { dt.setPointerCapture(e.pointerId); } catch (err) {}
  e.preventDefault();
});
dt.addEventListener('pointermove', function (e) {
  if (!drag || !A.clip) return;
  var c = A.clip, r = dt.getBoundingClientRect(), x = e.clientX - r.left, dx = x - drag.x0;
  if (Math.abs(dx) > 3) drag.moved = true;
  if (!drag.moved) return;
  var d = dx / drag.W * drag.span;
  if (drag.kind === 'start') { c.start = clamp(drag.s0 + d, 0, c.end - MIN_SEL); seek(c.start); }
  else if (drag.kind === 'end') { c.end = clamp(drag.e0 + d, c.start + MIN_SEL, c.dur); seek(c.end); }
  else if (drag.kind === 'move') {
    var len = drag.e0 - drag.s0, ns = clamp(drag.s0 + d, 0, c.dur - len);
    c.start = ns; c.end = ns + len; seek(c.start);
  }
  keepInView();
  queueDraw();
});
function endDrag() {
  if (!drag || !A.clip) { drag = null; return; }
  var c = A.clip;
  if (drag.kind === 'tap' && !drag.moved) {
    var len = c.end - c.start, ns = clamp(drag.t, 0, Math.max(0, c.dur - len));
    c.start = ns; c.end = Math.min(c.dur, ns + len);
    queueDraw();
  }
  var k = drag.kind;
  drag = null;
  seek(k === 'end' ? c.end : c.start, true);
}
dt.addEventListener('pointerup', endDrag);
dt.addEventListener('pointercancel', endDrag);
function keepInView() {
  var c = A.clip, span = c.v1 - c.v0;
  if (span >= c.dur) return;
  var kind = drag ? drag.kind : '';
  if (kind !== 'end' && c.start < c.v0) {
    c.v0 = Math.max(0, c.start - 0.3); c.v1 = c.v0 + span;
  } else if (kind !== 'start' && c.end > c.v1) {
    c.v1 = Math.min(c.dur, c.end + 0.3); c.v0 = c.v1 - span;
  }
}
['h-start', 'h-end'].forEach(function (id) {
  $(id).addEventListener('keydown', function (e) {
    var c = A.clip;
    if (!c) return;
    var d = e.key === 'ArrowLeft' ? -0.05 : e.key === 'ArrowRight' ? 0.05 : 0;
    if (!d) return;
    e.preventDefault();
    if (id === 'h-start') c.start = clamp(c.start + d, 0, c.end - MIN_SEL);
    else c.end = clamp(c.end + d, c.start + MIN_SEL, c.dur);
    keepInView(); queueDraw(); seek(id === 'h-start' ? c.start : c.end, true);
  });
});

/* ---- trim gestures: whole-video strip */
var odrag = null;
var ov = $('ov');
ov.addEventListener('pointerdown', function (e) {
  var c = A.clip;
  if (!c) return;
  stopPreview();
  var r = ov.getBoundingClientRect(), x = e.clientX - r.left, t = x / r.width * c.dur, span = c.v1 - c.v0;
  if (t < c.v0 || t > c.v1) {
    var nv0 = clamp(t - span / 2, 0, c.dur - span), d = nv0 - c.v0;
    c.v0 = nv0; c.v1 = nv0 + span;
    var len = c.end - c.start;
    c.start = clamp(c.start + d, 0, c.dur - len); c.end = c.start + len;
    seek(c.start); queueDraw();
  }
  odrag = { x0: x, W: r.width, v00: c.v0, s0: c.start, e0: c.end, span: span };
  try { ov.setPointerCapture(e.pointerId); } catch (err) {}
  e.preventDefault();
});
ov.addEventListener('pointermove', function (e) {
  if (!odrag || !A.clip) return;
  var c = A.clip, r = ov.getBoundingClientRect(), x = e.clientX - r.left;
  var nv0 = clamp(odrag.v00 + (x - odrag.x0) / odrag.W * c.dur, 0, c.dur - odrag.span), d = nv0 - odrag.v00;
  c.v0 = nv0; c.v1 = nv0 + odrag.span;
  var len = odrag.e0 - odrag.s0;
  c.start = clamp(odrag.s0 + d, 0, c.dur - len); c.end = c.start + len;
  seek(c.start); queueDraw();
});
function endODrag() { if (odrag && A.clip) seek(A.clip.start, true); odrag = null; }
ov.addEventListener('pointerup', endODrag);
ov.addEventListener('pointercancel', endODrag);

/* ---- preview the selection */
$('sel-play').addEventListener('click', function () {
  if (A.previewing) { stopPreview(); return; }
  var c = A.clip;
  if (!c) return;
  getCtx();
  A.previewing = true;
  setPlayIcon($('sel-play'), true);
  if (c.buf && !c.isVideo) {
    playBuffer(c.buf, c.start, c.end, 'preview', showPh, function () { A.previewing = false; setPlayIcon($('sel-play'), false); hidePh(); });
    return;
  }
  var el = c.el;
  el.muted = false;
  el.currentTime = c.start;
  var p = el.play();
  if (p && p.catch) p.catch(function () { stopPreview(); });
  (function tick() {
    if (!A.previewing) return;
    if (el.currentTime >= c.end || el.ended) { stopPreview(); el.currentTime = c.start; return; }
    showPh(el.currentTime);
    A.raf = requestAnimationFrame(tick);
  })();
});
$('vid').addEventListener('click', function () { $('sel-play').click(); });
function stopPreview() {
  if (!A.previewing) return;
  A.previewing = false;
  cancelAnimationFrame(A.raf);
  var c = A.clip;
  if (c && (c.isVideo || !c.buf)) c.el.pause();
  else if (P.id === 'preview') stopPlay();
  setPlayIcon($('sel-play'), false);
  $('sel-play').setAttribute('aria-label', 'Play the clip');
  hidePh();
}

/* ---- cut the clip */
function exportClip() {
  var c = A.clip;
  if (!c) return Promise.resolve(null);
  if (c.buf) {
    return Promise.resolve({ blob: encodeWav(monoSlice(c.buf, c.start, c.end), c.buf.sampleRate), ext: 'wav' });
  }
  return captureRealtime(c).then(function (blob) {
    var mime = (blob.type || 'audio/webm').split(';')[0];
    var ext = /mp4|aac|m4a/.test(mime) ? 'm4a' : /ogg/.test(mime) ? 'ogg' : 'webm';
    return { blob: blob, ext: ext };
  });
}
/** Fallback when the phone can't decode the file: play the selection and record it. */
function captureRealtime(c) {
  if (!window.MediaRecorder) return Promise.reject(new Error("This phone can't cut audio from that file."));
  $('save').textContent = 'Cutting the clip…';
  var ac = getCtx(), el = c.el;
  if (!el._fwSrc) { el._fwSrc = ac.createMediaElementSource(el); el._fwSrc.connect(ac.destination); }
  var dest = ac.createMediaStreamDestination();
  el._fwSrc.connect(dest);
  var mime = pickMime();
  var rec = mime ? new MediaRecorder(dest.stream, { mimeType: mime }) : new MediaRecorder(dest.stream);
  var chunks = [];
  rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
  var finished = new Promise(function (resolve) {
    rec.onstop = function () {
      try { el._fwSrc.disconnect(dest); } catch (e) {}
      resolve(new Blob(chunks, { type: rec.mimeType || mime || 'audio/webm' }));
    };
  });
  el.pause();
  el.currentTime = c.start;
  return once(el, 'seeked', 1500).then(function () {
    rec.start();
    el.muted = false;
    return el.play();
  }).then(function () {
    (function tick() {
      if (el.currentTime >= c.end || el.ended) { el.pause(); if (rec.state !== 'inactive') rec.stop(); }
      else requestAnimationFrame(tick);
    })();
    return finished;
  });
}

/* ---- save */
function postWord(meta, audio, ext) {
  var fd = new FormData();
  fd.append('meta', JSON.stringify(meta));
  if (audio) fd.append('audio', audio, 'clip.' + (ext || 'wav'));
  return req('POST', '/words', fd);
}
function postAudio(wordId, meta, audio, ext) {
  var fd = new FormData();
  fd.append('meta', JSON.stringify(meta));
  fd.append('audio', audio, 'clip.' + (ext || 'wav'));
  return req('POST', '/audio/' + encodeURIComponent(wordId), fd);
}
function saveAttach() {
  var c = A.clip, id = A.target, w0 = byId(id);
  if (!c) { toast('Record it, or pick a video or voice memo first.'); return; }
  if (recState) { toast('Stop the recording first.'); return; }
  getCtx();
  stopPreview();
  var btn = $('save');
  btn.disabled = true; btn.textContent = 'Saving…';
  var meta = { clipStart: Math.round(c.start * 100) / 100, clipEnd: Math.round(c.end * 100) / 100 };
  var video = c.isVideo && $('f-keep').checked ? c.blob : null;
  var out = null;
  exportClip().then(function (audio) {
    out = audio;
    return postAudio(id, meta, audio.blob, audio.ext);
  }).then(function (w) {
    clipCache.delete(w.id);
    cacheLocalClip(w, c);
    replaceWord(w);
    resetClip();
    openDetail(w.id);
    toast('Captured “' + w.word + '”');
    if (video) uploadVideo(video, w.id);
  }).catch(function (e) {
    if (!e.retryable || !out) { toast(e.message || 'Could not save. Try again.', 5000); return; }
    var item = { key: 'c_' + id, type: 'clip', wordId: id, meta: meta, audio: out.blob, ext: out.ext,
      video: video, queuedAt: new Date().toISOString() };
    return Q.put(item).then(function () {
      S.pending = S.pending.filter(function (x) { return x.key !== item.key; }).concat([item]);
      var w = Object.assign({}, w0, { _audio: item.audio, _clipPending: true, clipStart: meta.clipStart, clipEnd: meta.clipEnd });
      clipCache.delete(id);
      cacheLocalClip(w, c);
      replaceWord(w);
      resetClip();
      openDetail(id);
      toast(e.offline ? 'Saved on this phone. Will upload when home.'
        : 'Saved on this phone. Will upload when ' + nas() + ' is back.', 5000);
    }, function () {
      toast("Couldn't save, and this phone couldn't hold it either. Try again in a moment.", 6000);
    });
  }).then(function () { btn.disabled = false; btn.textContent = 'Save recording'; });
}
$('save').addEventListener('click', function () {
  if (A.kind === 'attach') { saveAttach(); return; }
  var word = $('f-word').value.trim();
  if (!word) { $('f-word').focus(); toast('Type the word ' + (C.child || 'they') + ' said.'); return; }
  if (recState) { toast('Stop the recording first.'); return; }
  getCtx();
  stopPreview();
  var btn = $('save'), c = A.kind === 'quick' ? null : A.clip;
  btn.disabled = true; btn.textContent = 'Saving…';
  var meta = {
    id: uuid(),
    word: word, sounded: $('f-sounded').value.trim(), date: $('f-date').value || todayStr(),
    heardBy: heardValue(), notes: $('f-notes').value.trim(),
    clipStart: c ? Math.round(c.start * 100) / 100 : null, clipEnd: c ? Math.round(c.end * 100) / 100 : null
  };
  var video = c && c.isVideo && $('f-keep').checked ? c.blob : null;
  var clipOut = null;
  exportClip().then(function (audio) {
    clipOut = audio;
    btn.textContent = 'Saving…';
    return postWord(meta, audio && audio.blob, audio && audio.ext);
  }).then(function (w) {
    cacheLocalClip(w, c);
    replaceWord(w);
    resetClip();
    openDetail(w.id);
    toast('Saved “' + w.word + '”');
    if (video) uploadVideo(video, w.id);
  }).catch(function (e) {
    if (!e.retryable || !clipOutReady(clipOut, c)) {
      toast(e.message || 'Could not save. Check your connection and try again.', 5000);
      return;
    }
    // HA or the NAS is unreachable: keep it on the phone and send it later.
    var item = { key: meta.id, type: 'word', meta: meta, audio: clipOut ? clipOut.blob : null,
      ext: clipOut ? clipOut.ext : '', video: video, videoName: video ? (video.name || 'video.mp4') : '',
      queuedAt: new Date().toISOString(), by: S.user };
    return Q.put(item).then(function () {
      S.pending.push(item);
      var w = pendingWord(item);
      cacheLocalClip(w, c);
      replaceWord(w);
      resetClip();
      openDetail(w.id);
      toast(e.offline ? 'Saved on this phone. Will upload when home.'
        : 'Saved on this phone. Will upload when ' + nas() + ' is back.', 5000);
    }, function () {
      toast("Couldn't save, and this phone couldn't hold it either. Try again in a moment.", 6000);
    });
  }).then(function () { btn.disabled = false; btn.textContent = 'Save word'; });
});
function clipOutReady(out, c) { return !c || !!out; }
function cacheLocalClip(w, c) {
  if (c && c.buf && hasAudio(w)) {
    var s = monoSlice(c.buf, c.start, c.end), b = getCtx().createBuffer(1, Math.max(1, s.length), c.buf.sampleRate);
    b.getChannelData(0).set(s);
    clipCache.set(w.id, Promise.resolve({ buf: b, peaks: makePeaks(b, 100) }));
  }
}

/* ---- offline queue */
function pendingWord(item) {
  var m = item.meta;
  return { id: m.id, word: m.word, sounded: m.sounded, date: m.date, heardBy: m.heardBy, notes: m.notes,
    addedBy: item.by || S.user, audioFile: '', videoFile: '', clipStart: m.clipStart, clipEnd: m.clipEnd,
    savedAt: item.queuedAt, _pending: true, _audio: item.audio, _video: !!item.video };
}
function mergePending() {
  S.pending.forEach(function (item) {
    if (item.type === 'word' && !byId(item.meta.id)) S.words.push(pendingWord(item));
    if (item.type === 'clip') {
      var w = byId(item.wordId);
      if (w && !w.audioFile) {
        w._audio = item.audio; w._clipPending = true;
        w.clipStart = item.meta.clipStart; w.clipEnd = item.meta.clipEnd;
      }
    }
  });
  sortWords();
}
function loadQueue() {
  return Q.all().then(function (items) { S.pending = items; }, function () { S.pending = []; });
}
var flushing = null;
function flushQueue() {
  if (flushing || !S.pending.length) return flushing || Promise.resolve();
  flushing = S.pending.slice().reduce(function (p, item) {
    return p.then(function () {
      if (item.type === 'word') {
        return postWord(item.meta, item.audio, item.ext).then(function (w) {
          var old = byId(w.id);
          if (old && old._pending) clipCache.delete(w.id);
          return Q.del(item.key).then(function () {
            S.pending = S.pending.filter(function (x) { return x.key !== item.key; });
            replaceWord(w);
            if (item.video) {
              var v = { key: 'v_' + w.id, type: 'video', wordId: w.id, video: item.video, queuedAt: item.queuedAt };
              return Q.put(v).catch(function () {}).then(function () { S.pending.push(v); });
            }
          });
        }, function (e) {
          if (e.retryable) throw e;  // still unreachable: stop, try the rest later
          // Refused outright (bad data): keep it on the phone, say so, and move on.
          toast('“' + item.meta.word + '” could not upload: ' + e.message, 6000);
        });
      }
      if (item.type === 'clip') {
        return postAudio(item.wordId, item.meta, item.audio, item.ext).then(function (w) {
          clipCache.delete(w.id);
          return Q.del(item.key).then(function () {
            S.pending = S.pending.filter(function (x) { return x.key !== item.key; });
            replaceWord(w);
            if (item.video) {
              var v = { key: 'v_' + w.id, type: 'video', wordId: w.id, video: item.video, queuedAt: item.queuedAt };
              return Q.put(v).catch(function () {}).then(function () { S.pending.push(v); });
            }
          });
        }, function (e) {
          if (e.retryable) throw e;
          if (e.status === 404) {  // the word was deleted meanwhile: nothing to attach to
            return Q.del(item.key).then(function () {
              S.pending = S.pending.filter(function (x) { return x.key !== item.key; });
            });
          }
          toast('A recording could not upload: ' + e.message, 6000);
        });
      }
      if (item.type === 'video' && !S.upload) {
        return new Promise(function (resolve) {
          uploadVideo(item.video, item.wordId, item.token, resolve);
        });
      }
    });
  }, Promise.resolve()).then(function () {
    if (!S.pending.length) toast('Everything on this phone is uploaded.');
  }, function () { /* still unreachable; try again later */ }).then(function () {
    flushing = null;
    renderBanner();
    if (!S.synced) refresh();
  });
  return flushing;
}

/* ---- video upload, in chunks, after the word is safely saved */
function setUp(frac, text) {
  $('upbar').hidden = false;
  $('up-fill').style.width = Math.round(frac * 100) + '%';
  $('up-text').textContent = text || ('Saving video ' + Math.round(frac * 100) + '% · keep this open');
}
function rememberVideo(file, wordId, token) {
  var key = 'v_' + wordId, item = { key: key, type: 'video', wordId: wordId, video: file, token: token || '',
    queuedAt: new Date().toISOString() };
  S.pending = S.pending.filter(function (x) { return x.key !== key; }).concat([item]);
  return Q.put(item).catch(function () {});
}
function forgetVideo(wordId) {
  var key = 'v_' + wordId;
  S.pending = S.pending.filter(function (x) { return x.key !== key; });
  return Q.del(key).catch(function () {});
}
function uploadVideo(file, wordId, token, done) {
  S.upload = { file: file, wordId: wordId, token: token || '' };
  $('up-retry').hidden = true;
  setUp(0, 'Starting video upload…');
  var offset = 0, tries = 0;
  function begin() {
    if (S.upload.token) {
      return req('GET', '/upload/' + S.upload.token).then(function (r) { offset = r.received; }, function (e) {
        if (e.status === 404) { S.upload.token = ''; return begin(); }
        throw e;
      });
    }
    return jsonReq('POST', '/video/' + encodeURIComponent(wordId) + '/start',
      { name: file.name || 'video.mp4', mime: file.type || 'video/mp4', size: file.size })
      .then(function (r) { S.upload.token = r.token; return rememberVideo(file, wordId, r.token); });
  }
  function next() {
    if (offset >= file.size) return req('POST', '/upload/' + S.upload.token + '/finish');
    var end = Math.min(file.size, offset + CHUNK);
    return req('PUT', '/upload/' + S.upload.token + '?offset=' + offset, file.slice(offset, end),
      { 'Content-Type': 'application/octet-stream' })
      .then(function (r) {
        offset = r.received; tries = 0;
        setUp(offset / file.size);
        return next();
      }, function (e) {
        if (e.status === 409 && e.data && typeof e.data.received === 'number') {
          offset = e.data.received; return next();
        }
        if (e.retryable && tries < 3) {
          tries++;
          return new Promise(function (r) { setTimeout(r, 1500 * tries); }).then(next);
        }
        throw e;
      });
  }
  rememberVideo(file, wordId, token)
    .then(begin)
    .then(next)
    .then(function (r) {
      S.upload = null;
      $('upbar').hidden = true;
      if (r && r.word) replaceWord(r.word);
      return forgetVideo(wordId).then(function () { toast('Video saved'); });
    })
    .catch(function (e) {
      setUp(file.size ? offset / file.size : 0, 'Video upload stopped. ' + (e.message || ''));
      $('up-retry').hidden = false;
    })
    .then(function () { if (done) done(); });
}
$('up-retry').addEventListener('click', function () {
  if (S.upload) uploadVideo(S.upload.file, S.upload.wordId, S.upload.token);
});

/* ================================================================ detail */
var lastFrac = 0;
function openDetail(id) {
  stopPlay();
  stopDetailVideo();
  S.current = id;
  lastFrac = 0;
  renderDetail();
  show('detail');
  requestAnimationFrame(function () { drawDetailWave(0); });
  var w = byId(id);
  if (w && hasAudio(w)) loadSaved(w).then(function (entry) {
    if (S.current !== id) return;
    if (entry.buf) $('d-time').textContent = clock(entry.buf.duration);
    drawDetailWave(0);
  }).catch(function () {});
}
function renderDetail() {
  var w = byId(S.current);
  if (!w) { go('list'); return; }
  var chrono = S.words.length - S.words.indexOf(w);
  $('d-pos').textContent = 'Word ' + chrono + ' of ' + S.words.length;
  $('d-word').textContent = w.word;
  $('d-sound').textContent = w.sounded ? 'sounded like “' + w.sounded + '”' : '';
  $('d-sound').hidden = !w.sounded;
  $('d-player').hidden = !hasAudio(w);
  $('d-capture').hidden = hasAudio(w) || !!w._pending;
  $('d-capture-sub').textContent = 'Record it next time you hear it, or pull it from a video';
  var len = clipLen(w);
  $('d-time').textContent = len ? clock(len) : '';
  setPlayIcon($('d-play'), false);
  $('d-date').textContent = fmtDate(w.date, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  $('d-heard').textContent = w.heardBy || '—';
  var age = ageText(w.date);
  $('d-age').textContent = age;
  $('d-age-wrap').hidden = !age;
  $('d-added').textContent = w.addedBy || '—';
  $('d-notes').textContent = w.notes || '';
  $('d-notes-wrap').hidden = !w.notes;
  $('d-edit').hidden = !!w._pending;
  var folder = (S.storage && S.storage.path ? S.storage.path.split('/').pop() : 'First Words');
  if (w._pending || w._clipPending) {
    $('d-saved-title').textContent = w._pending ? 'Saved on this phone' : 'Recording saved on this phone';
    $('d-audio-name').textContent = 'Uploads to ' + nas() + ' when Home Assistant is reachable';
  } else {
    $('d-saved-title').textContent = 'Saved on ' + nas();
    $('d-audio-name').textContent = w.audioFile ? folder + ' / ' + w.audioFile.replace('/', ' / ') : 'Details saved in the First Words log';
  }
  $('d-video-link').hidden = !w.videoFile;
  if (w.videoFile) $('d-video-name').textContent = folder + ' / ' + w.videoFile.replace('/', ' / ');
}
function drawDetailWave(frac) {
  lastFrac = frac || 0;
  var w = byId(S.current), cv = $('d-wave');
  if (!w || !hasAudio(w) || !cv.clientWidth) return;
  var f = fitCanvas(cv), step = 5, nb = Math.floor(f.w / step);
  var entryP = clipCache.get(w.id);
  function paint(peaks) {
    f = fitCanvas(cv);
    for (var i = 0; i < nb; i++) {
      var amp = peaks ? peaks[Math.floor(i / nb * peaks.length)] || 0 : 0.2;
      bar(f.g, i * step, 3, Math.max(4, amp * f.h), f.h, i / nb < lastFrac ? '#E9A23B' : '#B9B3A6');
    }
  }
  paint(null);
  if (entryP) entryP.then(function (e) { if (S.current === w.id) paint(e.peaks); }).catch(function () {});
}
$('d-capture').addEventListener('click', function () {
  var w = byId(S.current);
  if (w) openAdd('attach', w.id);
});
$('d-play').addEventListener('click', function () {
  var w = byId(S.current);
  if (!w || !hasAudio(w)) return;
  if (P.id === 'd_' + w.id) { stopPlay(); return; }
  getCtx();
  stopPlay();
  var btn = $('d-play');
  btn.style.opacity = '.6';
  loadSaved(w).then(function (entry) {
    btn.style.opacity = '';
    setPlayIcon(btn, true);
    playEntry(entry, 'd_' + w.id, drawDetailWave, function () { setPlayIcon(btn, false); drawDetailWave(0); });
  }).catch(function (e) { btn.style.opacity = ''; toast(e.message); });
});
/* Videos can be large, so stream them with a short-lived signed URL instead of fetching a blob. */
function signedUrl(path) {
  return host.hass.callWS({ type: 'auth/sign_path', path: path, expires: 3600 }).then(function (r) {
    var base = (host.hass.auth && host.hass.auth.data && host.hass.auth.data.hassUrl) || '';
    return base + r.path;
  });
}
function stopDetailVideo() {
  var v = $('d-video');
  if (!v.hidden) { v.pause(); v.removeAttribute('src'); v.load(); v.hidden = true; }
}
$('d-video-link').addEventListener('click', function () {
  var w = byId(S.current);
  if (!w || !w.videoFile) return;
  stopPlay();
  signedUrl('/api/first_words/video/' + encodeURIComponent(w.id)).then(function (url) {
    var v = $('d-video');
    v.src = url; v.hidden = false;
    var p = v.play(); if (p && p.catch) p.catch(function () {});
    v.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }).catch(function () { toast("Couldn't open the video."); });
});

/* ---- edit / delete */
var delArmed = 0;
$('d-edit').addEventListener('click', function () {
  var w = byId(S.current);
  if (!w || w._pending) return;
  stopPlay();
  $('e-word').value = w.word; $('e-sounded').value = w.sounded || ''; $('e-date').value = w.date;
  $('e-heard').value = w.heardBy || ''; $('e-notes').value = w.notes || '';
  $('e-delete').textContent = 'Delete this word'; delArmed = 0;
  $('edit').showModal();
});
$('e-close').addEventListener('click', function () { $('edit').close(); });
$('e-save').addEventListener('click', function () {
  var btn = $('e-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  jsonReq('PATCH', '/words/' + encodeURIComponent(S.current), {
    word: $('e-word').value, sounded: $('e-sounded').value, date: $('e-date').value,
    heardBy: $('e-heard').value, notes: $('e-notes').value
  }).then(function (w) {
    replaceWord(w);
    $('edit').close();
    toast('Changes saved');
  }).catch(function (e) { toast(e.message); })
    .then(function () { btn.disabled = false; btn.textContent = 'Save changes'; });
});
$('e-delete').addEventListener('click', function () {
  var btn = $('e-delete');
  if (Date.now() - delArmed > 4000) {
    delArmed = Date.now();
    btn.textContent = 'Tap again to delete it and its recording';
    return;
  }
  btn.disabled = true;
  var id = S.current;
  req('DELETE', '/words/' + encodeURIComponent(id)).then(function () {
    S.words = S.words.filter(function (w) { return w.id !== id; });
    clipCache.delete(id);
    $('edit').close();
    go('list');
    toast("Deleted. The files are kept in the share's .trash folder.", 4500);
  }).catch(function (e) { toast(e.message); })
    .then(function () { btn.disabled = false; });
});

/* ================================================================ saved / backup */
function renderSaved() {
  var n = S.words.filter(function (w) { return !w._pending; }).length, st = S.storage;
  $('s-folder-name').textContent = st && st.path ? st.path : '';
  $('s-nas').textContent = cap(nas());
  $('s-fine').textContent = 'Clips are ordinary audio files and the log is a plain JSON file on ' + nas() +
    (C.offsite ? ' (' + C.offsite + ')' : '') + ', so they still open if this app goes away. ' +
    "Deleted words go to the share's .trash folder.";
  var ok = st && st.mounted && !st.error;
  $('s-ok').style.display = ok ? '' : 'none';
  $('s-status').textContent = !ok
    ? "Not connected right now. New words wait on this phone."
    : n ? 'All ' + n + (n === 1 ? ' word' : ' words') + ' saved · newest ' + fmtDate(S.words[0].date, { month: 'short', day: 'numeric' })
      : 'Ready. Nothing saved yet.';
  $('s-who').textContent = S.user || 'you';
  $('s-ver').textContent = 'v' + VERSION;
  $('s-result').innerHTML = '';
}
function makeFile(kind, btn, label) {
  var old = btn.firstChild.textContent;
  btn.disabled = true; btn.firstChild.textContent = 'Working… ';
  req('POST', '/make/' + kind).then(function (r) {
    return signedUrl(r.url).then(function (url) {
      $('s-result').innerHTML = '<a class="linkcard" style="margin:0;width:100%" target="_blank" rel="noopener" href="' + esc(url) + '">' +
        '<span class="ic">' + I_CHECK + '</span>' +
        '<span class="tx"><b>' + esc(label) + '</b><small>' + esc(r.name) + ' · in the share\'s exports folder</small></span></a>';
    });
  }).catch(function (e) { toast(e.message); })
    .then(function () { btn.disabled = false; btn.firstChild.textContent = old; });
}
$('s-zip').addEventListener('click', function () { makeFile('export', this, 'Backup .zip is ready'); });
$('s-book').addEventListener('click', function () { makeFile('keepsake', this, 'Keepsake is ready to print'); });

boot();

return {
  setNarrow: function (narrow) {
    var slot = $('menu-slot');
    if (!narrow) { slot.innerHTML = ''; return; }
    if (!slot.firstChild && customElements.get('ha-menu-button')) {
      var b = document.createElement('ha-menu-button');
      b.hass = host.hass; b.narrow = true;
      slot.appendChild(b);
    } else if (slot.firstChild) { slot.firstChild.hass = host.hass; }
  },
  destroy: function () {
    window.removeEventListener('beforeunload', onBeforeUnload);
    window.removeEventListener('resize', onResize);
    window.removeEventListener('online', onOnline);
    document.removeEventListener('visibilitychange', onVisible);
    clearInterval(flushTimer);
  },
  _debug: { S: S, A: A, Q: Q, flush: flushQueue }
};
}

class FirstWordsPanel extends HTMLElement {
  set hass(h) {
    this._hass = h;
    if (!this._app && this.isConnected) this._start();
    else if (this._app) this._app.setNarrow(this._narrow);
  }
  get hass() { return this._hass; }
  set narrow(n) { this._narrow = n; if (this._app) this._app.setNarrow(n); }
  get narrow() { return this._narrow; }
  set panel(p) { this._panel = p; }
  set route(r) { this._route = r; }
  connectedCallback() { if (!this._app && this._hass) this._start(); }
  disconnectedCallback() {
    if (this._onFit) window.removeEventListener('resize', this._onFit);
    if (this._app) { this._app.destroy(); this._app = null; this.shadowRoot.innerHTML = ''; }
  }
  _fit() {
    var top = Math.max(0, Math.round(this.getBoundingClientRect().top));
    if (top !== this._top) { this._top = top; this.style.setProperty('--fw-top', top + 'px'); }
  }
  _start() {
    var self = this;
    this._onFit = this._onFit || function () { self._fit(); };
    window.addEventListener('resize', this._onFit);
    requestAnimationFrame(this._onFit);
    setTimeout(this._onFit, 300);
    ensureFonts();
    var root = this.shadowRoot || this.attachShadow({ mode: 'open' });
    root.innerHTML = '<style>' + CSS + '</style>' + HTML;
    this._app = createApp(this, root);
    this._app.setNarrow(this._narrow);
  }
}
customElements.define('first-words-panel', FirstWordsPanel);
})();

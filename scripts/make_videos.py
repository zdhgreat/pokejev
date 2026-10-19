"""Render the demo videos (MP4 + a README GIF) from battle runs: the animated Showdown replay is recorded in real time
with headless Chrome (DevTools screencast), Jev's panel following it turn by turn; frames are encoded with FFmpeg.

Developer tool, not needed to use the package. Requires Google Chrome or Microsoft Edge and ffmpeg on PATH, and an
internet connection (the battle screen loads Showdown's replay scripts).

    python scripts/make_videos.py --player runs/demo-player --steer runs/demo-ha02 --steer-battle 2 \
        --setup scripts/setup_walkthrough.json --out docs/media

Writes demo-battle.mp4, demo-steering.mp4, setup-walkthrough.mp4 and demo.gif.
"""
import argparse
import asyncio
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pokejev import viewer   # noqa: E402

W, H = 1440, 900
CHROME_CANDIDATES = [os.environ.get("CHROME", ""),
                     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                     r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]

FONT = ('<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">')
GB = ("background-color:#0f380f;background-image:linear-gradient(rgba(155,188,15,.06) 1px,transparent 1px),"
      "linear-gradient(90deg,rgba(155,188,15,.06) 1px,transparent 1px);background-size:16px 16px")

CARD = """<!doctype html><meta charset="utf-8">""" + FONT + """<style>
html,body{margin:0;height:100%;""" + GB + """;color:#e0f8d0;font:22px/1.6 ui-monospace,Consolas,monospace}
.wrap{height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 140px}
.k{color:#9bbc0f;font:16px "Press Start 2P",monospace;letter-spacing:1px}.k:before{content:"";display:inline-block;width:12px;height:12px;background:#9bbc0f;margin-right:14px}
h1{font:46px/1.4 "Press Start 2P",monospace;margin:30px 0 28px;text-shadow:5px 5px 0 #306230}
p{color:#8bac0f;font-size:27px;max-width:1150px;margin:0 0 12px}.logo{font:18px "Press Start 2P",monospace;color:#e0f8d0}.logo b{color:#9bbc0f}</style>
<div class="wrap"><div class="k">__KICKER__</div><h1>__TITLE__</h1>__BODY__<p class="logo" style="margin-top:44px">poke<b>·</b>jev</p></div>"""

TERMINAL = """<!doctype html><meta charset="utf-8">""" + FONT + """<style>
html,body{margin:0;height:100%;""" + GB + """;color:#e0f8d0;font:21px/1.6 Consolas,"Cascadia Mono",monospace}
.win{position:absolute;inset:78px 90px 60px;background:#0a260a;border:4px solid #306230;box-shadow:10px 10px 0 #071c07;overflow:hidden}
.bar{height:46px;background:#306230;display:flex;align-items:center;gap:12px;padding:0 18px}
.sq{width:14px;height:14px;background:#9bbc0f}.title{margin-left:8px;color:#e0f8d0;font:11px "Press Start 2P",monospace}
.body{padding:24px 30px;white-space:pre-wrap}.c{color:#9bbc0f}.cmt{color:#8bac0f}.ok{color:#e0f8d0;font-weight:700}
.step{position:absolute;left:90px;top:28px;color:#9bbc0f;font:15px "Press Start 2P",monospace;letter-spacing:1px;text-transform:uppercase}
</style><div class="step">__STEP__</div><div class="win"><div class="bar"><span class="sq"></span><span class="sq"></span><span class="sq"></span>
<span class="title">TERMINAL</span></div><div class="body">__LINES__</div></div>"""


def chrome():
    for c in CHROME_CANDIDATES:
        if c and (Path(c).exists() or shutil.which(c)):
            return c
    raise SystemExit("Chrome or Edge not found; set CHROME=path")


def shot(url, out, budget=3000):
    """budget: virtual milliseconds to let the page load (the battle screen needs Showdown's scripts and sprites)."""
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--window-size=%d,%d" % (W, H), "--virtual-time-budget=%d" % budget, "--screenshot=%s" % out, url],
                   check=True, capture_output=True)


def card(tmp, name, kicker, title, body):
    f = tmp / (name + ".html")
    f.write_text(CARD.replace("__KICKER__", html.escape(kicker)).replace("__TITLE__", html.escape(title))
                 .replace("__BODY__", "".join("<p>%s</p>" % html.escape(b) for b in body)), encoding="utf-8")
    png = tmp / (name + ".png")
    shot(f.resolve().as_uri(), png)
    return png


async def _record(url, folder, start_turn, max_turn, conflict_turns, hold):
    """Play the viewer's animated replay in headless Chrome and keep every screencast frame with its timestamp."""
    import websockets   # installed with poke-env
    prof = folder / "profile"
    proc = subprocess.Popen([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
                             "--remote-debugging-port=0", "--user-data-dir=%s" % prof, "--window-size=%d,%d" % (W, H),
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (prof / "DevToolsActivePort").exists() and (prof / "DevToolsActivePort").read_text().strip():
                break
            await asyncio.sleep(0.1)
        port = (prof / "DevToolsActivePort").read_text().split()[0]
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:%s/json" % port).read())
        ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=None) as ws:
            ids, waiting, frames = iter(range(1, 10 ** 9)), {}, []

            async def reader():
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("method") == "Page.screencastFrame":
                        p = m["params"]
                        f = folder / ("f%05d.jpg" % len(frames))
                        f.write_bytes(base64.b64decode(p["data"]))
                        frames.append((f, p["metadata"]["timestamp"]))
                        asyncio.ensure_future(send("Page.screencastFrameAck", sessionId=p["sessionId"]))
                    elif m.get("id") in waiting:
                        waiting.pop(m["id"]).set_result(m.get("result", {}))

            async def send(method, **params):
                i = next(ids)
                waiting[i] = asyncio.get_running_loop().create_future()
                await ws.send(json.dumps({"id": i, "method": method, "params": params}))
                return await waiting[i]

            async def js(expr):
                r = await send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return r.get("result", {}).get("value")

            task = asyncio.ensure_future(reader())
            await send("Page.enable")
            await send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
            await send("Page.navigate", url=url)
            for _ in range(240):                         # up to 60 s for Showdown's scripts
                if await js("typeof ready!=='undefined'&&ready"):
                    break
                await asyncio.sleep(0.25)
            else:
                raise SystemExit("the Showdown battle screen did not load (offline?)")
            if start_turn:
                await js("Replays.battle.seekTurn(%d);S=Math.max(0,BT.steps.findIndex(s=>s.turn>=%d));render()" % (start_turn, start_turn))
            # every sprite and effect image must be downloaded first, or it is missing the first time it is used
            loaded = await js("preloadAll()")
            print("sprites and effect images loaded: %d/%d" % tuple(loaded))
            await asyncio.sleep(1.5)                     # sprites and backdrop
            await js("play()")
            await asyncio.sleep(0.3)                     # Showdown's own "Play" button is gone once playback starts
            await send("Page.startScreencast", format="jpeg", quality=88, maxWidth=W, maxHeight=H)
            held = set()
            while True:
                await asyncio.sleep(0.1)
                turn, ended = await js("[Replays.battle.turn,Replays.battle.ended]")
                if turn in conflict_turns and turn not in held:  # stop on the turn the intent changed Jev's move
                    held.add(turn)
                    await js("Replays.battle.pause()")
                    await asyncio.sleep(hold)
                    await js("Replays.battle.play()")
                if ended or (max_turn and turn > max_turn):
                    break
            await asyncio.sleep(2.5)
            await send("Page.stopScreencast")
            task.cancel()
        return frames
    finally:
        proc.kill()
        proc.wait()


def battle_video(tmp, run_dir, battle, prefix, start_turn=None, max_turn=None, hold=4.0):
    """Real-time recording of the animated battle; Jev's panel follows the replay turn by turn."""
    page = viewer.write(run_dir, open_browser=False)
    steps = viewer.build_data(run_dir)["battles"][battle]["steps"]
    conflict = {s["turn"] for s in steps if (s.get("intent") or {}).get("conflict")}
    folder = tmp / prefix
    folder.mkdir()
    frames = asyncio.run(_record(page.resolve().as_uri() + "?battle=%d" % battle, folder, start_turn, max_turn, conflict,
                                 hold))
    return [(f, nxt[1] - t) for (f, t), nxt in zip(frames, frames[1:])] + [(frames[-1][0], 1.0)]


def terminal_frames(tmp, spec):
    """spec: [{"step": "1 · install", "lines": [["cmd", "..."], ["out", "..."], ...]}, ...]; reveal line by line."""
    frames = []
    for i, scene in enumerate(spec):
        shown = []
        for j, (kind, text) in enumerate(scene["lines"]):
            cls = {"cmd": "c", "cmt": "cmt", "ok": "ok"}.get(kind, "")
            prefix = "$ " if kind == "cmd" else ""
            shown.append('<span class="%s">%s%s</span>' % (cls, prefix, html.escape(text)))
            f = tmp / ("term-%02d-%02d.html" % (i, j))
            f.write_text(TERMINAL.replace("__STEP__", html.escape(scene["step"])).replace("__LINES__", "\n".join(shown)),
                         encoding="utf-8")
            png = tmp / ("term-%02d-%02d.png" % (i, j))
            shot(f.resolve().as_uri(), png)
            frames.append((png, 1.6 if kind == "cmd" else 0.9))
        frames[-1] = (frames[-1][0], 3.0)
    return frames


def _jpg(f):
    if f.suffix == ".jpg":
        return f
    j = f.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f), "-pix_fmt", "yuvj420p", "-q:v", "2", str(j)], check=True)
    return j


def encode(segments, out_mp4):
    """segments: [(png, seconds), ...] -> H.264 MP4 at 30 fps."""
    lst = out_mp4.with_suffix(".txt")
    segments = [(_jpg(f), sec) for f, sec in segments]
    with lst.open("w", encoding="utf-8") as f:
        for png, sec in segments:
            f.write("file '%s'\nduration %.2f\n" % (png.resolve().as_posix(), sec))
        f.write("file '%s'\n" % segments[-1][0].resolve().as_posix())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
                    "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-movflags", "+faststart",
                    str(out_mp4)], check=True)
    lst.unlink()


def gif(src_mp4, out_gif, start=0, seconds=14, width=960):
    vf = "fps=12,scale=%d:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" % width
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(seconds), "-i", str(src_mp4),
                    "-vf", vf, str(out_gif)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", required=True)
    ap.add_argument("--steer", required=True)
    ap.add_argument("--setup", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--battle", type=int, default=0)
    ap.add_argument("--steer-battle", type=int, default=0)
    ap.add_argument("--max-turn", type=int, default=None, help="stop the battle recording after this turn")
    ap.add_argument("--lead-in", type=int, default=3, help="turns shown before the steering demo's first conflict")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="jevvid-"))
    try:
        pdata = viewer.build_data(a.player)
        segs = [(card(tmp, "t1", "demo 1", "Jev plays a Pokémon battle",
                      ["Left: the real battle (Pokémon Showdown replay). Right: what Jev saw and chose.",
                       "Code computes the facts for every legal option; Jev picks with one Choice per turn.",
                       "Bars show Jev's probability for each option."]), 5.0)]
        segs += battle_video(tmp, a.player, a.battle, "p", max_turn=a.max_turn)
        won = pdata["battles"][a.battle]["won"]
        segs.append((card(tmp, "t1e", "result", "Jev %s this battle" % ("won" if won else "lost"),
                          ["%d of %d battles won in this run (version %s, model %s)." % (
                              pdata["run"]["wins"], pdata["run"]["battles"], pdata["run"]["version"], pdata["run"]["model"])]), 3.5))
        encode(segs, out / "demo-battle.mp4")
        sdata = viewer.build_data(a.steer)
        segs = [(card(tmp, "t2", "demo 2", "Steering with a designer intent",
                      ["The designer writes one plain-text instruction:", "“%s”" % sdata["intent_text"],
                       "Watch for “intent followed — the rule would have broken it”."]), 5.5)]
        conflicts = [s["turn"] for s in sdata["battles"][a.steer_battle]["steps"] if (s.get("intent") or {}).get("conflict")]
        start = max(1, conflicts[0] - a.lead_in) if conflicts else None
        segs += battle_video(tmp, a.steer, a.steer_battle, "s", start_turn=start, max_turn=a.max_turn)
        encode(segs, out / "demo-steering.mp4")
        spec = json.loads(Path(a.setup).read_text(encoding="utf-8"))
        segs = [(card(tmp, "t3", "setup", "From zero to your first battle",
                      ["Install, start a local Showdown server, run a battle, open the viewer."]), 4.0)]
        segs += terminal_frames(tmp, spec)
        encode(segs, out / "setup-walkthrough.mp4")
        gif(out / "demo-battle.mp4", out / "demo.gif", start=5.0, seconds=16)
        for f in ("demo-battle.mp4", "demo-steering.mp4", "setup-walkthrough.mp4", "demo.gif"):
            print("%-24s %6.1f MB" % (f, (out / f).stat().st_size / 1e6))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""把 md/*.md 轉成 ai-tutorial/*.html。用法：python3 tools/build.py

Markdown 之外多支援幾種區塊（::: 開頭、::: 結束，可以巢狀）：
  :::learn            這一課你會學到
  :::step 標題        編號步驟（自動編號）
  :::say              「你可以這樣說」訊息框（有複製鈕）
  :::chat             對話示意，每行「你：…」或「Claude：…」
  :::flow             流程圖，每行「圖示|標題|說明」
  :::cards            卡片格，每行「圖示|標題|說明」
  :::shot 代號 標題   待補截圖（請使用者提供）
  :::tip / :::warn    提醒框
  :::stuck            常見卡關
  :::video            影片大綱
圖片單獨一行 ![說明](img/x.jpg)；後面加 {.phone} 是手機直式窄圖。連續幾行圖片會排成一列。
"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "md"


def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    s = esc(s)
    codes = []
    s = re.sub(r"`([^`]+)`", lambda m: codes.append(m.group(1)) or f"\0{len(codes)-1}\0", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: f'<a href="{m.group(2)}"' + (' target="_blank" rel="noopener"' if m.group(2).startswith("http") else "") + f'>{m.group(1)}</a>', s)
    s = re.sub(r"\0(\d+)\0", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)
    return s


IMG = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)(\{\.(\w+)\})?\s*$")


def render_lines(lines, ctx):
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if not st:
            i += 1
            continue
        if st.startswith(":::") and st != ":::":
            name, _, arg = st[3:].partition(" ")
            depth, j = 1, i + 1
            while j < len(lines):
                t = lines[j].strip()
                if t.startswith(":::"):
                    depth += -1 if t == ":::" else 1
                    if depth == 0:
                        break
                j += 1
            out.append(block(name, arg.strip(), lines[i + 1:j], ctx))
            i = j + 1
            continue
        if st.startswith("```"):
            lang = st[3:].strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            code = "\n".join(lines[i + 1:j])
            btn = '<button class="copy" type="button">複製</button>' if lang in ("bash", "text") else ""
            out.append(f'<div class="code"><pre><code>{esc(code)}</code></pre>{btn}</div>')
            i = j + 1
            continue
        if st.startswith("#"):
            lvl = len(st) - len(st.lstrip("#"))
            text = st[lvl:].strip()
            hid = f"h{ctx['h']}"
            ctx["h"] += 1
            out.append(f'<h{lvl} id="{hid}">{inline(text)}</h{lvl}>')
            i += 1
            continue
        if IMG.match(st):
            figs = []
            while i < len(lines) and IMG.match(lines[i].strip()):
                m = IMG.match(lines[i].strip())
                cls = f' class="{m.group(4)}"' if m.group(4) else ""
                figs.append(f'<figure{cls}><a href="{m.group(2)}" target="_blank"><img src="{m.group(2)}" alt="{esc(m.group(1))}" loading="lazy"></a><figcaption>{inline(m.group(1))}</figcaption></figure>')
                i += 1
            out.append(f'<div class="figs n{len(figs)}">' + "".join(figs) + "</div>")
            continue
        if st.startswith("<"):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            out.append("\n".join(lines[i:j]))
            i = j
            continue
        if st.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not set("".join(r)) <= set("-: ")]
            t = "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f'<td data-label="{esc(h)}">{inline(c)}</td>' for h, c in zip(head, r)) + "</tr>" for r in body)
            out.append(f'<div class="table"><table>{t}</tbody></table></div>')
            continue
        if re.match(r"^(- |\d+\. )", st):
            ordered = bool(re.match(r"^\d+\. ", st))
            items = []
            while i < len(lines) and re.match(r"^\s*(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^\s*(- |\d+\. )", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if st.startswith(">"):
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f'<blockquote>{inline(" ".join(q))}</blockquote>')
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(:::|```|#|!\[|\||- |\d+\. |>|<)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if not para:  # 防呆：無法辨識的行當成段落
            para.append(st)
            i += 1
        out.append(f"<p>{inline(''.join(para))}</p>")
    return "\n".join(out)


def rows(lines):
    return [[p.strip() for p in l.strip().split("|")] for l in lines if l.strip()]


def block(name, arg, lines, ctx):
    inner = lambda: render_lines(lines, ctx)
    if name == "step":
        ctx["step"] += 1
        n = ctx["step"]
        ctx["steps"].append((n, arg))
        return f'<section class="step" id="step{n}"><div class="stephead"><span class="num">{n}</span><h3>{inline(arg)}</h3></div><div class="stepbody">{inner()}</div></section>'
    if name == "learn":
        return f'<div class="box learn"><div class="boxtitle">這一課你會學到</div>{inner()}</div>'
    if name == "say":
        text = "\n".join(l.strip() for l in lines).strip()
        return f'<div class="say"><div class="saylabel">💬 你可以這樣說</div><p class="saytext">{inline(text).replace(chr(10), "<br>")}</p><button class="copy" type="button">複製</button></div>'
    if name == "chat":
        items = []
        for l in lines:
            l = l.strip()
            if not l:
                continue
            who, _, msg = l.partition("：")
            cls = "me" if who == "你" else "ai"
            items.append(f'<div class="bubble {cls}"><span class="who">{esc(who)}</span>{inline(msg)}</div>')
        cap = f'<div class="chatcap">{inline(arg)}</div>' if arg else '<div class="chatcap">對話示意（不是 app 截圖）</div>'
        return f'<div class="chat">{"".join(items)}{cap}</div>'
    if name == "flow":
        cells = []
        for r in rows(lines):
            icon, title, desc = (r + ["", "", ""])[:3]
            cells.append(f'<div class="node"><div class="icon">{icon}</div><div class="nt">{inline(title)}</div><div class="nd">{inline(desc)}</div></div>')
        cap = f'<div class="flowcap">{inline(arg)}</div>' if arg else ""
        return '<div class="flow">' + '<div class="arrow" aria-hidden="true"></div>'.join(cells) + "</div>" + cap
    if name == "cards":
        cells = []
        for r in rows(lines):
            icon, title, desc = (r + ["", "", ""])[:3]
            cells.append(f'<div class="card"><div class="icon">{icon}</div><div><div class="nt">{inline(title)}</div><div class="nd">{inline(desc)}</div></div></div>')
        return '<div class="cards">' + "".join(cells) + "</div>"
    if name == "shot":
        code, _, title = arg.partition(" ")
        ctx["shots"].append((code, title))
        return f'<div class="shot"><div class="shotcode">待補截圖 {esc(code)}</div><div class="shottitle">{inline(title)}</div><div class="shotbody">{inner()}</div></div>'
    if name in ("tip", "warn"):
        label = arg or ("小提醒" if name == "tip" else "注意")
        return f'<div class="box {name}"><div class="boxtitle">{inline(label)}</div>{inner()}</div>'
    if name == "stuck":
        return f'<section class="box stuck" id="stuck"><div class="boxtitle">🧱 常見卡關</div>{inner()}</section>'
    if name == "video":
        return f'<section class="box video" id="video"><div class="boxtitle">🎬 影片大綱{("：" + inline(arg)) if arg else ""}</div>{inner()}</section>'
    return inner()


def front(text):
    meta = {}
    if text.startswith("---"):
        head, _, text = text[3:].partition("\n---")
        for l in head.strip().splitlines():
            k, _, v = l.partition(":")
            meta[k.strip()] = v.strip()
    return meta, text


SCRIPT = """<script>
document.querySelectorAll('.copy').forEach(b=>b.addEventListener('click',()=>{
  const box=b.parentElement, t=(box.querySelector('code')||box.querySelector('.saytext')).innerText;
  navigator.clipboard&&navigator.clipboard.writeText(t).then(()=>{b.textContent='已複製';setTimeout(()=>b.textContent='複製',1500)});
}));
</script>"""


def page(title, body, desc=""):
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="stylesheet" href="style.css">
</head>
<body>
{body}
{SCRIPT}
</body>
</html>
"""


def main():
    files = sorted(MD.glob("[0-9][0-9]-*.md"))
    lessons = []
    for f in files:
        meta, text = front(f.read_text())
        lessons.append((f, meta, text))
    all_shots = []
    for idx, (f, meta, text) in enumerate(lessons):
        ctx = {"step": 0, "steps": [], "h": 0, "shots": []}
        body = render_lines(text.splitlines(), ctx)
        num = meta.get("num", str(idx + 1))
        out = f.stem + ".html"
        all_shots += [(num, meta.get("short", ""), out, c, t) for c, t in ctx["shots"]]
        toc = "".join(f'<li><a href="#step{n}">{inline(t)}</a></li>' for n, t in ctx["steps"])
        prev = lessons[idx - 1] if idx > 0 else None
        nxt = lessons[idx + 1] if idx + 1 < len(lessons) else None
        nav = '<nav class="pager">'
        nav += f'<a class="prev" href="{prev[0].stem}.html">← 第 {prev[1]["num"]} 課 {esc(prev[1]["short"])}</a>' if prev else '<a class="prev" href="index.html">← 目錄</a>'
        nav += f'<a class="next" href="{nxt[0].stem}.html">第 {nxt[1]["num"]} 課 {esc(nxt[1]["short"])} →</a>' if nxt else '<a class="next" href="index.html">回目錄 →</a>'
        nav += "</nav>"
        html_body = f"""<header class="top"><a href="index.html">AI 零基礎創作教學</a><span>第 {num} 課／共 {len(lessons)} 課</span></header>
<main>
<div class="hero"><div class="kicker">第 {num} 課</div><h1>{inline(meta.get('title', ''))}</h1><p class="lead">{inline(meta.get('lead', ''))}</p>
<div class="meta">{inline(meta.get('time', ''))}</div></div>
<details class="toc"><summary>本課步驟（{len(ctx['steps'])} 步）</summary><ol>{toc}</ol><a href="#stuck">常見卡關</a> · <a href="#video">影片大綱</a></details>
{body}
{nav}
</main>"""
        (ROOT / out).write_text(page(f"第 {num} 課 {meta.get('short', '')}", html_body, meta.get("lead", "")))
        print("寫入", out)
    # 目錄頁
    idx_meta, idx_text = front((MD / "index.md").read_text())
    ctx = {"step": 0, "steps": [], "h": 0, "shots": []}
    intro = render_lines(idx_text.splitlines(), ctx)
    cards = ""
    for f, meta, _ in lessons:
        cards += f'<a class="lesson" href="{f.stem}.html"><img src="{meta.get("thumb", "")}" alt="" loading="lazy"><div><div class="kicker">第 {meta["num"]} 課</div><div class="lt">{inline(meta.get("title", ""))}</div><div class="ld">{inline(meta.get("lead", ""))}</div></div></a>'
    shots = "".join(f'<li><strong>{esc(c)}</strong> {inline(t)}（<a href="{o}">第 {n} 課 {esc(s)}</a>）</li>' for n, s, o, c, t in all_shots)
    review = f'<section class="box warn review"><div class="boxtitle">審稿用：還缺這些畫面</div><p>下面這些是 Claude 桌面版、各服務授權畫面，我看不到你的螢幕，所以先留空框。請你截圖給我（帳號、Email 我會遮掉）。</p><ol>{shots}</ol></section>' if all_shots else ""
    body = f"""<header class="top"><a href="index.html">AI 零基礎創作教學</a><span>共 {len(lessons)} 課</span></header>
<main>
<div class="hero"><h1>{inline(idx_meta.get('title', ''))}</h1><p class="lead">{inline(idx_meta.get('lead', ''))}</p></div>
{intro}
<div class="lessons">{cards}</div>
{review}
</main>"""
    (ROOT / "index.html").write_text(page(idx_meta.get("title", "目錄"), body, idx_meta.get("lead", "")))
    print("寫入 index.html；待補截圖", len(all_shots), "張")


if __name__ == "__main__":
    main()

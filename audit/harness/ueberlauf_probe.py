import sys, br
from playwright.sync_api import sync_playwright
JS = r"""() => { const m = document.querySelector('[data-testid=stMain]'); const vw = m.clientWidth, out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect(); if (!r.width || r.right <= vw + 1) continue;
    let p = e.parentElement, im = false;
    for (; p && p !== m; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o==='auto'||o==='scroll'||o==='hidden') { im = true; break; } }
    if (im) continue;
    const t=[]; for (let q=e; q && t.length<4; q=q.parentElement){const d=q.getAttribute&&(q.getAttribute('data-testid')||q.className&&String(q.className).match(/st-key-[\w-]+/)?.[0]); if(d) t.push(d);}
    out.push([Math.round(r.right), Math.round(r.width), e.tagName, String(e.className||'').slice(0,40), t.join('<'), (e.innerText||'').trim().slice(0,30)]); }
  out.sort((a,b)=>b[0]-a[0]); return [m.scrollWidth, vw, out.slice(0,10)]; }"""
nutzer, pw, breite, ansicht = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
pill = sys.argv[5] if len(sys.argv) > 5 else None
with sync_playwright() as p:
    b, ctx, page = br.start(p, breite, 800, True)
    br.login(page, nutzer, pw); page.wait_for_timeout(800)
    if ansicht != "START":
        if not page.locator(".st-key-nav_menue button", has_text=ansicht).first.is_visible():
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
        page.locator(".st-key-nav_menue button", has_text=ansicht).first.click(); br.warte_ruhe(page, 180)
    if pill:
        page.locator("[data-testid=stMain] [data-testid=stButtonGroup] button", has_text=pill).filter(visible=True).first.click(); br.warte_ruhe(page)
    sw, vw, out = page.evaluate(JS)
    print(breite, ansicht, pill, "scrollWidth", sw, "vw", vw)
    for o in out: print("  ", o)
    page.screenshot(path=f"{sys.argv[0][:-3]}_{breite}.png", full_page=False)
    b.close()

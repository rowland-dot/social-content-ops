"""Stage 7: the approval page (and the headline comparison page). Built from the checked files, nothing reworded."""
from __future__ import annotations
import html, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_checks, tmall_common as common

class NotCheckedError(RuntimeError):
    pass

CSS = ("body{font-family:'Noto Sans CJK SC',sans-serif;margin:16px;background:#f4f4f2;overflow-wrap:anywhere}"       # on body so every page's text wraps: a long web address in a source, a headline, a check note or an id

       ".phone{width:375px;max-width:100%;margin:0 auto 24px;background:#fff}.phone img{width:100%;display:block}"
       ".copy{padding:8px 12px;white-space:pre-wrap}.source{padding:0 12px 8px;color:#555;font-size:13px}"
       ".versions{display:flex;gap:16px}.version{flex:1;margin:0}.version img{width:100%}"       # margin:0: figure's default 40 px sides narrowed each version on a phone
       "@media(max-width:420px){body{margin:0}.versions{flex-direction:column}}")

def _shell(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='zh'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style><body>{body}</body></html>")

def _why_not(image_id: str, report) -> str:
    if not report:
        return f"{image_id}: no check report"
    parts = [f"failed {', '.join(report.get('failed', []))}" if report.get("failed") else "",
             f"missing {', '.join(report.get('missing', []))}" if report.get("missing") else ""]
    return f"{image_id}: " + ("; ".join(p for p in parts if p) or "not passed")

def _not_confirmed(rules) -> str:
    if not rules:
        return ""
    return ("<div class='source'>以下天猫规则尚未按天猫当前规则核实（not yet confirmed against current Tmall guidance）："
            + html.escape("、".join(rules)) + "</div>")

def _passed_for_this_image(folder, image: str, report) -> bool:
    """A report counts only if it passed and was made for these exact image bytes: a round-1 report never passes a round-2 image,
    and a hand-written "passed" without the fingerprint gather records is refused (autoplan review)."""
    results = (report or {}).get("results") or {}
    every_check_passed = all((results.get(c) or {}).get("verdict") == "pass" for c in tmall_checks.CHECKS)    # the flags alone are not trusted (QA 2026-10-28)
    return bool(report and report.get("complete") and report.get("passed") and every_check_passed          # .get: a hand-written report without these keys is refused, not a crash
                and report.get("image_sha256") == common.sha256(Path(folder) / image))

def build_approval(folder, items: list[dict], reports: dict, not_confirmed=()) -> str:
    bad = [_why_not(i["id"], reports.get(i["id"])) + ("" if not reports.get(i["id"], {}).get("passed") else ": made for another version of the image")
           for i in items if not _passed_for_this_image(folder, i["image"], reports.get(i["id"]))]
    if bad:
        raise NotCheckedError("not shown until checked and passed; run the stage 6 checks again for these and fix what is named: " + " | ".join(bad))
    parts, n = [], {"main": 0, "detail": 0}
    for i in items:
        n[i["kind"]] += 1      # the names the owner uses in a ruling: 主图1 to 主图5, 详情第N屏
        cls, attr, label = (("main-image", "data-image", f"主图{n['main']}") if i["kind"] == "main"
                            else ("detail-screen", "data-screen", f"详情第{n['detail']}屏"))
        sources = "".join(f"<div class='source'>{html.escape(s)}</div>" for s in i["sources"])
        parts.append(f"<section class='phone {cls}' {attr}='{html.escape(i['id'])}'><h2 class='label'>{label}</h2>"
                     f"<img src='{html.escape(i['image'])}' alt='{html.escape(i['copy'][:120])}'>"
                     f"<div class='copy'>{html.escape(i['copy'])}</div>{sources}</section>")
    summary = f"<p class='summary'>主图 {n['main']} 张，详情 {n['detail']} 屏，全部通过检查。</p>{_not_confirmed(not_confirmed)}"
    return _shell("Tmall approval", summary + "".join(parts))

def build_headline(folder, versions: dict) -> str:
    """Spec stage 5: all three pass stage 6 before the owner sees them, so this page refuses otherwise (autoplan review)."""
    bad = [k for k, v in sorted(versions.items()) if not _passed_for_this_image(folder, v["image"], v.get("report"))]
    if bad:
        raise NotCheckedError(f"headline versions not checked and passed, so not shown: {', '.join(bad)}")
    cells = "".join(
        f"<figure class='version' data-version='{k}'><img src='{html.escape(v['image'])}' alt='Version {k}: {html.escape(v['headline'])}'>"
        f"<img class='thumb' src='{html.escape(v['image'])}' alt='Version {k} at search-result size' style='width:128px'>"
        f"<figcaption>{k}：{html.escape(v['headline'])}<br>方向：{html.escape(v['direction'])}<br>参照竞品：{html.escape(str(v['listing_id']))}</figcaption></figure>"
        for k, v in sorted(versions.items()))
    return _shell("Headline versions", f"<div class='versions'>{cells}</div>")

def build_check_report(reports: dict, not_confirmed=()) -> str:
    """What the owner gets when an image stops at the checks (spec: stop and report) and, while the quality check is held, the only page
    there is: one row per image, in words, never the raw report file (autoplan review)."""
    rows = []
    for image_id, r in sorted(reports.items()):
        state = "通过" if r.get("complete") and r.get("passed") else ("未通过" if r.get("failed") else "未完成")      # .get: a hand-written report missing keys is shown, not a crash (reviewed-plan audit pass 2)
        notes = "".join(f"<li>{html.escape(c)}：{html.escape((r.get('results', {}).get(c) or {}).get('note') or '')}</li>" for c in r.get("failed", []))
        notes += "".join(f"<li>{html.escape(c)}：没有结果（not run yet）</li>" for c in r.get("missing", []))
        rows.append(f"<section class='phone report' data-image='{html.escape(image_id)}'><h2 class='label'>{html.escape(image_id)}：{state}</h2><ul>{notes}</ul></section>")
    return _shell("Tmall check report", _not_confirmed(not_confirmed) + ("".join(rows) or "<p>还没有检查结果（no check results yet）。</p>"))

def main(argv=None) -> int:
    import argparse, json
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("approval", "headline", "report"):
        sub.add_parser(name).add_argument("product_dir")
    a = ap.parse_args(argv)
    folder = Path(a.product_dir)
    source, out = {"approval": ("approval-items.json", "approval.html"), "headline": ("headline-versions.json", "headline-versions.html"),
                   "report": ("check-reports.json", "check-report.html")}[a.cmd]
    if not (folder / source).is_file():
        print(f"{folder / source} is missing; write it first (shape: see the skill page)", file=sys.stderr); return 2
    data = json.loads((folder / source).read_text(encoding="utf-8"))
    try:
        page = (build_approval(folder, data["items"], data["reports"], data.get("not_confirmed", ())) if a.cmd == "approval"
                else build_headline(folder, data) if a.cmd == "headline"
                else build_check_report(data["reports"], data.get("not_confirmed", ())))
    except NotCheckedError as e:
        print(e, file=sys.stderr); return 2
    except KeyError as e:                 # a hand-written input missing a key is named, not a traceback (reviewed-plan audit pass 3)
        print(f"{folder / source} has no {e} entry; write it in the shape the skill page gives", file=sys.stderr); return 2
    (folder / out).write_text(page, encoding="utf-8"); print(folder / out); return 0

if __name__ == "__main__":
    sys.exit(main())

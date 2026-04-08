from __future__ import annotations

from pathlib import Path
import re


def _extract_raw_triple_quoted(text: str, var_name: str) -> str:
    start_m = re.search(rf"\n{re.escape(var_name)}\s*=\s*r\"\"\"", text)
    if not start_m:
        raise RuntimeError(f"Could not find {var_name} = r\"\"\" start")
    start = start_m.end()
    end = text.find('"""', start)
    if end == -1:
        raise RuntimeError(f"Could not find closing triple-quotes for {var_name}")
    return text[start:end]


def _extract_root_return_html(text: str) -> str:
    root_start = re.search(
        r'@app\.get\("/",\s*response_class=HTMLResponse\)\s*\n'
        r"async def root\(\):\s*\n\s*return \"\"\"",
        text,
    )
    if not root_start:
        raise RuntimeError("Could not find root() return triple-quote start")
    start = root_start.end()
    end = text.find('"""', start)
    if end == -1:
        raise RuntimeError("Could not find root() closing triple-quotes")
    return text[start:end]


def main() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    text = app_path.read_text(encoding="utf-8")

    ui_dir = app_path.parent / "ui"
    ui_dir.mkdir(exist_ok=True)

    student_html = _extract_raw_triple_quoted(text, "STUDENT_HTML")
    admin_html = _extract_raw_triple_quoted(text, "ADMIN_HTML")
    index_html = _extract_root_return_html(text)

    (ui_dir / "student.html").write_text(student_html, encoding="utf-8", newline="\n")
    (ui_dir / "admin.html").write_text(admin_html, encoding="utf-8", newline="\n")
    (ui_dir / "index.html").write_text(index_html, encoding="utf-8", newline="\n")

    print("Wrote:", (ui_dir / "student.html"))
    print("Wrote:", (ui_dir / "admin.html"))
    print("Wrote:", (ui_dir / "index.html"))


if __name__ == "__main__":
    main()


from __future__ import annotations

from pathlib import Path
import re


def _replace_raw_triple_quoted(text: str, var_name: str, replacement: str) -> str:
    # Replace: VAR = r""" ... """
    pattern = rf"(\n{re.escape(var_name)}\s*=\s*r\"\"\"[\s\S]*?\"\"\")"
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"Could not find raw triple-quoted block for {var_name}")
    return text[: m.start(1)] + "\n" + replacement + text[m.end(1) :]


def _replace_root_return(text: str, replacement_return_line: str) -> str:
    # Replace the triple-quoted return inside root()
    pattern = (
        r'(@app\.get\("/",\s*response_class=HTMLResponse\)\s*\n'
        r"async def root\(\):\s*\n\s*)return \"\"\"[\s\S]*?\"\"\""
    )
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError("Could not find root() triple-quoted return block")
    prefix = m.group(1)
    return text[: m.start()] + prefix + replacement_return_line + text[m.end() :]


def main() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    text = app_path.read_text(encoding="utf-8")

    text = _replace_raw_triple_quoted(
        text,
        "STUDENT_HTML",
        'STUDENT_HTML = None  # loaded from ui/student.html at runtime',
    )
    text = _replace_raw_triple_quoted(
        text,
        "ADMIN_HTML",
        'ADMIN_HTML = None  # loaded from ui/admin.html at runtime',
    )
    text = _replace_root_return(text, "return load_ui_page('index.html')\n")

    app_path.write_text(text, encoding="utf-8", newline="\n")
    print("Stripped embedded UI blocks from:", app_path)


if __name__ == "__main__":
    main()


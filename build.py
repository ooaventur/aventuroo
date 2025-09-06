"""Assemble final HTML files from templates using Jinja2 partials."""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def build():
    src = Path(".")
    dest = Path("dist")
    dest.mkdir(exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(src)), autoescape=False)

    for html_file in src.glob("*.html"):
        template = env.get_template(html_file.name)
        output = template.render()
        (dest / html_file.name).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    build()

import random

from rich.console import Console, JustifyMethod
from rich.highlighter import Highlighter
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

console = Console()


class RainbowHighlighter(Highlighter):
    def highlight(self, text):
        for index in range(len(text)):
            text.stylize(f"color({random.randint(16, 255)})", index, index + 1)


def print_blank():
    console.print()


def print_text(content: str, style: str = "", rainbow: bool = False, with_markup: bool = False):
    print_blank()

    text = Text(content)

    if with_markup:
        text = Text.from_markup(content)

    if style:
        text.stylize(style)

    if rainbow:
        text = RainbowHighlighter()(text)

    console.print(text)


def print_prompt(content: str, empty_allowed=False) -> str:
    response = None
    while not response:
        response = Prompt.ask(content)
        if empty_allowed:
            break
    return response

def print_table(table: Table, justify: JustifyMethod = "center"):
    print_blank()

    console.print(table, justify=justify)

def clear_screen():
    console.clear()

#print_text("Hello, World!", style="bold red on white", rainbow=True)

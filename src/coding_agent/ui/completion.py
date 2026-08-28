from __future__ import annotations

import os
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from coding_agent.skills import SkillRegistry
from coding_agent.ui.commands import COMMAND_BY_NAME, SLASH_COMMANDS


class AgentCompleter(Completer):
    def __init__(self, workspace: Path, skills: SkillRegistry) -> None:
        self.workspace = workspace
        self.skills = skills

    def get_completions(self, document: Document, complete_event: object):  # type: ignore[no-untyped-def]
        token = document.get_word_before_cursor(WORD=True)
        if token.startswith("/") and not document.text_before_cursor.strip().count(" "):
            for command in SLASH_COMMANDS:
                if command.startswith(token):
                    yield Completion(
                        command,
                        start_position=-len(token),
                        display_meta=COMMAND_BY_NAME[command].description,
                    )
            return
        if token.startswith("$"):
            prefix = token[1:]
            for name in sorted(self.skills.skills):
                if name.startswith(prefix):
                    yield Completion("$" + name, start_position=-len(token))
            return
        if token.startswith("@"):
            prefix = token[1:].casefold()
            count = 0
            for directory, names, files in os.walk(self.workspace, followlinks=False):
                names[:] = [
                    name
                    for name in names
                    if name != ".git" and not (Path(directory) / name).is_symlink()
                ]
                for name in files:
                    path = Path(directory) / name
                    relative = path.relative_to(self.workspace).as_posix()
                    if prefix in relative.casefold():
                        yield Completion("@" + relative, start_position=-len(token))
                        count += 1
                    if count >= 100:
                        return

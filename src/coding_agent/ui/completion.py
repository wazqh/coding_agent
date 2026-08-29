from __future__ import annotations

import os
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from coding_agent.model_catalog import ModelCatalog
from coding_agent.skills import SkillRegistry
from coding_agent.ui.commands import COMMAND_BY_NAME, SLASH_COMMANDS


class AgentCompleter(Completer):
    def __init__(
        self,
        workspace: Path,
        skills: SkillRegistry,
        *,
        model_catalog: ModelCatalog | None = None,
    ) -> None:
        self.workspace = workspace
        self.skills = skills
        self.model_catalog = model_catalog

    def get_completions(self, document: Document, complete_event: object):  # type: ignore[no-untyped-def]
        before = document.text_before_cursor
        if before.startswith("/model use ") and self.model_catalog is not None:
            value = before.removeprefix("/model use ")
            provider, separator, prefix = value.partition(" ")
            if not separator:
                for name in self.model_catalog.providers():
                    if name.startswith(provider):
                        yield Completion(name, start_position=-len(provider))
                return
            profile = self.model_catalog.config.providers.get(provider)
            if profile is not None:
                for model in profile.models or [profile.default_model]:
                    if model.startswith(prefix):
                        yield Completion(model, start_position=-len(prefix))
            return
        if before.startswith("/steps "):
            prefix = before.removeprefix("/steps ")
            for value in ("12", "24", "40", "64", "100", "reset"):
                if value.startswith(prefix):
                    yield Completion(value, start_position=-len(prefix))
            return
        if before.startswith("/model "):
            prefix = before.removeprefix("/model ")
            for value in ("use", "reload"):
                if value.startswith(prefix):
                    yield Completion(value, start_position=-len(prefix))
            return
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

from typing import cast

import lsprotocol.types as lsp
from beet import Context, GenericPlugin, Pipeline, Task

from .context import LanguageServerContext

__all__ = ["PipelineShadow"]


class PipelineShadow(Pipeline):
    def require(self, *args: GenericPlugin[Context] | str):
        for spec in args:
            try:
                plugin = self.resolve(spec)
            except Exception as exc:
                ls = cast(LanguageServerContext, self.ctx).ls
                message = f"An issue occured while loading plugin: {spec}\n{exc}"
                ls.show_message(message.split("\n")[0], lsp.MessageType.Warning)
                ls.show_message_log(message, lsp.MessageType.Warning)
                continue

            if plugin in self.plugins:
                continue

            self.plugins.add(plugin)

            try:
                # Advance the plugin only once, ignore remaining work
                # Most setup happens in the first half of the plugin
                # where side effects happen in the latter
                Task(plugin).advance(self.ctx)
            except Exception as exc:
                ls = cast(LanguageServerContext, self.ctx).ls
                message = f"An issue occured while running first step of plugin: {plugin}\n{exc}"
                ls.show_message(message.split("\n")[0], lsp.MessageType.Warning)
                ls.show_message_log(message, lsp.MessageType.Warning)

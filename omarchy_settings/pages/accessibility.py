"""Accessibility page: text size, cursor size and animations."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from .. import accessibility as a11y
from .. import core, displays
from ..i18n import _
from ..ui import Debouncer, bg, combo_row, spin_row
from .hyprland import HyprOptionsPage


class AccessibilityPage(HyprOptionsPage):
    GROUPS = ("seeing", "motion")
    RESET_SUBTITLE = _("Turns the animations back on")

    def _seeing_group(self) -> None:
        self.seeing = Adw.PreferencesGroup(title=_("Seeing"))
        self.add(self.seeing)
        self._text_size = Debouncer(600, lambda size: bg(lambda: displays.set_text_size(size)))
        if core.have("omarchy-display-text-size"):
            bg(displays.text_size, self._add_text_size)
        if core.have("gsettings"):
            bg(a11y.cursor_size, self._add_cursor_size)

    def _add_text_size(self, size) -> None:
        if isinstance(size, int):
            self.seeing.add(
                spin_row(
                    _("Text size"), _("Shell, GTK apps and terminals (default 12)"), 9, 20, 1, size, self._text_size
                )
            )

    def _add_cursor_size(self, size) -> None:
        if isinstance(size, Exception):
            return
        sizes = list(a11y.CURSOR_SIZES)
        labels = [_("Default ({size})").format(size=n) if n == a11y.DEFAULT_CURSOR else str(n) for n in sizes]
        self.seeing.add(
            combo_row(
                _("Pointer size"),
                _("In pixels; apps opened from now on use it too"),
                labels,
                sizes.index(size) if size in sizes else 0,
                lambda i: self._set_cursor(sizes[i]),
            )
        )

    def _set_cursor(self, size: int) -> None:
        def work() -> None:
            a11y.set_cursor_size(size)
            self.store.set_extra("cursor_size", None if size == a11y.DEFAULT_CURSOR else size, reload=False)

        bg(work)

    def _motion_group(self) -> None:
        group = Adw.PreferencesGroup(title=_("Motion"))
        group.add(
            self._switch(
                "animations:enabled",
                _("Animations"),
                _("Transitions when opening, closing and switching workspaces; turn off to reduce motion"),
                True,
            )
        )
        self.add(group)

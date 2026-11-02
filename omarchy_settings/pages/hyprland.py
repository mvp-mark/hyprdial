"""Hyprland settings page: style, windows, effects, keyboard, mouse, touchpad and behavior.

Each row shows the value in use (saved state > running Hyprland > default) and, when this app overrides the
option, a ↶ button that returns just that option to Omarchy's default.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import core
from ..i18n import _
from ..ui import bg, button_row, to_bool, to_float

# Quick styles: keys missing from a style go back to Omarchy's default.
PRESET_KEYS = (
    "general:gaps_in",
    "general:gaps_out",
    "general:border_size",
    "decoration:rounding",
    "decoration:blur:enabled",
    "decoration:blur:size",
    "decoration:blur:passes",
    "decoration:shadow:enabled",
    "decoration:shadow:range",
    "decoration:inactive_opacity",
)
PRESETS = [
    (
        _("Compact"),
        _("No gaps or decorations: maximum usable area"),
        {
            "general:gaps_in": 0,
            "general:gaps_out": 0,
            "general:border_size": 1,
            "decoration:rounding": 0,
            "decoration:blur:enabled": False,
            "decoration:shadow:enabled": False,
        },
    ),
    ("Omarchy", _("Omarchy's default look"), {}),
    (
        _("Comfortable"),
        _("More room between windows and soft corners"),
        {
            "general:gaps_in": 8,
            "general:gaps_out": 16,
            "general:border_size": 2,
            "decoration:rounding": 10,
            "decoration:shadow:enabled": True,
            "decoration:shadow:range": 12,
        },
    ),
    (
        _("Elegant"),
        _("Rounded corners, shadow, blur and translucent inactive windows"),
        {
            "general:gaps_in": 10,
            "general:gaps_out": 20,
            "general:border_size": 2,
            "decoration:rounding": 14,
            "decoration:blur:enabled": True,
            "decoration:blur:size": 6,
            "decoration:blur:passes": 2,
            "decoration:shadow:enabled": True,
            "decoration:shadow:range": 20,
            "decoration:inactive_opacity": 0.92,
        },
    ),
]

LAYOUTS = [
    ("dwindle", _("Split (default)"), _("Each new window splits the space of the focused window")),
    ("master", _("Main and stack"), _("One large window on the left and the others stacked beside it")),
    ("scrolling", _("Side scrolling"), _("Side-by-side columns that scroll horizontally, niri style")),
]

# (label, layout, variant)
KEYBOARDS = [
    (_("Portuguese (Brazil, ABNT2)"), "br", ""),
    (_("English (US)"), "us", ""),
    (_("English (US, international with dead keys)"), "us", "intl"),
    (_("Portuguese (Portugal)"), "pt", ""),
    (_("Spanish"), "es", ""),
]

ACCEL = [("", _("Device default")), ("adaptive", _("Adaptive")), ("flat", _("Off (good for games)"))]


def keyboard_index(layout: str, variant: str) -> int:
    """Position in the list of common layouts; the last item is 'Custom'."""
    return next(
        (i for i, (_label, lay, var) in enumerate(KEYBOARDS) if (lay, var) == (layout, variant)), len(KEYBOARDS)
    )


FOLLOW = [(1, _("On mouse hover")), (0, _("Only on click")), (2, _("On click, but the keyboard follows the mouse"))]


class HyprlandPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store
        self.controls: dict[str, tuple[Callable, object, Gtk.Button]] = {}
        self.entries: dict[str, Adw.EntryRow] = {}
        self._updating = False

        self._style_group()
        self._windows_group()
        self._effects_group()
        self._keyboard_group()
        self._mouse_group()
        self._touchpad_group()
        self._behavior_group()

        reset = Adw.PreferencesGroup()
        reset.add(
            button_row(
                _("Restore defaults"),
                _("Returns every option on this page to Omarchy's default"),
                _("Restore"),
                self._reset_all,
                "destructive-action",
            )
        )
        self.add(reset)

    # ------------------------------------------------------------------ groups
    def _style_group(self) -> None:
        group = Adw.PreferencesGroup(
            title=_("Quick style"),
            description=_("Applies several settings at once; you can fine-tune each one below."),
        )
        for name, desc, values in PRESETS:
            group.add(button_row(name, desc, _("Apply"), lambda v=values, n=name: self._apply_preset(n, v)))
        self.add(group)

    def _windows_group(self) -> None:
        group = Adw.PreferencesGroup(title=_("Windows"))
        group.add(
            self._choice(
                "general:layout",
                _("Window layout"),
                LAYOUTS[0][0],
                [(k, label) for k, label, _desc in LAYOUTS],
                subtitle_for=self._layout_subtitle,
            )
        )
        group.add(self._spin("general:gaps_in", _("Gap between windows"), _("In pixels"), 0, 40, 1, 5))
        group.add(self._spin("general:gaps_out", _("Margin to the screen edge"), _("In pixels"), 0, 80, 1, 10))
        group.add(
            self._spin(
                "general:border_size",
                _("Border width"),
                _("The color comes from the theme; 0 hides the border"),
                0,
                10,
                1,
                2,
            )
        )
        group.add(
            self._spin(
                "decoration:rounding", _("Rounded corners"), _("Radius in pixels; 0 keeps corners square"), 0, 30, 1, 0
            )
        )
        group.add(
            self._switch(
                "general:resize_on_border",
                _("Resize from the border"),
                _("Drag a window's border with the mouse to resize it"),
                False,
            )
        )
        self.add(group)

    def _effects_group(self) -> None:
        group = Adw.PreferencesGroup(
            title=_("Transparency and effects"),
            description=_("Effects use more GPU; on laptops they can drain the battery."),
        )
        group.add(
            self._percent(
                "decoration:active_opacity", _("Active window opacity"), _("100% is fully opaque"), 30, 100, 1.0
            )
        )
        group.add(
            self._percent(
                "decoration:inactive_opacity",
                _("Other windows' opacity"),
                _("Below 100% lets you see what is behind"),
                30,
                100,
                1.0,
            )
        )
        group.add(
            self._switch(
                "decoration:dim_inactive", _("Dim unfocused windows"), _("Helps you see which window is active"), False
            )
        )
        group.add(self._percent("decoration:dim_strength", _("Dimming strength"), "", 0, 100, 0.5))

        blur = Adw.ExpanderRow(title=_("Blur"), subtitle=_("Blurs what shows behind translucent windows"))
        blur.add_row(self._switch("decoration:blur:enabled", _("Enable blur"), "", False))
        blur.add_row(self._spin("decoration:blur:size", _("Strength"), _("Blur radius"), 1, 20, 1, 8))
        blur.add_row(
            self._spin("decoration:blur:passes", _("Quality"), _("More passes = smoother and heavier"), 1, 4, 1, 1)
        )
        group.add(blur)

        shadow = Adw.ExpanderRow(title=_("Shadow"), subtitle=_("Soft shadow around windows"))
        shadow.add_row(self._switch("decoration:shadow:enabled", _("Enable shadow"), "", False))
        shadow.add_row(self._spin("decoration:shadow:range", _("Size"), _("In pixels"), 1, 50, 1, 4))
        group.add(shadow)

        group.add(
            self._switch(
                "animations:enabled",
                _("Animations"),
                _("Transitions when opening, closing and switching workspaces"),
                True,
            )
        )
        self.add(group)

    def _keyboard_group(self) -> None:
        group = Adw.PreferencesGroup(title=_("Keyboard"))
        group.add(self._keyboard_row())
        group.add(self._switch("input:numlock_by_default", _("Num Lock on at startup"), "", False))
        group.add(
            self._spin(
                "input:repeat_delay",
                _("Delay before repeating"),
                _("Milliseconds holding a key before it repeats"),
                100,
                1000,
                50,
                600,
            )
        )
        group.add(self._spin("input:repeat_rate", _("Repeat rate"), _("Characters per second"), 1, 100, 1, 25))

        advanced = Adw.ExpanderRow(title=_("Advanced"), subtitle=_("Multiple layouts, variants and XKB options"))
        advanced.add_row(self._entry("input:kb_layout", _("Layouts (e.g. br,us)"), "us"))
        advanced.add_row(self._entry("input:kb_variant", _("Variants (e.g. ,intl)"), ""))
        advanced.add_row(self._entry("input:kb_options", _("Options (e.g. compose:caps,grp:alts_toggle)"), ""))
        group.add(advanced)
        self.add(group)

    def _mouse_group(self) -> None:
        group = Adw.PreferencesGroup(title=_("Mouse"))
        group.add(
            self._spin(
                "input:sensitivity", _("Pointer speed"), _("From -1 (slower) to 1 (faster)"), -1, 1, 0.05, 0, digits=2
            )
        )
        group.add(self._choice("input:accel_profile", _("Acceleration"), "", ACCEL))
        group.add(
            self._switch(
                "input:natural_scroll", _("Natural scrolling"), _("Content follows the wheel's movement"), False
            )
        )
        group.add(self._spin("input:scroll_factor", _("Scroll speed"), _("1 is normal"), 0.1, 5, 0.1, 1.0, digits=1))
        group.add(
            self._switch("input:left_handed", _("Left-handed mode"), _("Swaps the left and right buttons"), False)
        )
        group.add(self._choice("input:follow_mouse", _("Window focus"), 1, FOLLOW))
        self.add(group)

    def _touchpad_group(self) -> None:
        group = Adw.PreferencesGroup(title=_("Touchpad"))
        group.add(self._switch("input:touchpad:tap-to-click", _("Tap to click"), "", True))
        group.add(self._switch("input:touchpad:natural_scroll", _("Natural scrolling"), _("Like on a phone"), False))
        group.add(
            self._switch(
                "input:touchpad:clickfinger_behavior",
                _("Two-finger click = right button"),
                _("Instead of clicking the bottom-right corner"),
                False,
            )
        )
        group.add(
            self._switch(
                "input:touchpad:disable_while_typing",
                _("Disable while typing"),
                _("Avoids moving the pointer by accident"),
                True,
            )
        )
        group.add(
            self._spin("input:touchpad:scroll_factor", _("Scroll speed"), _("1 is normal"), 0.1, 3, 0.1, 1.0, digits=1)
        )
        self.add(group)

    def _behavior_group(self) -> None:
        group = Adw.PreferencesGroup(title=_("Behavior"))
        group.add(
            self._switch(
                "misc:focus_on_activate",
                _("Focus windows that ask for attention"),
                _("E.g. opening a link brings the browser to the front"),
                False,
            )
        )
        group.add(
            self._switch(
                "binds:workspace_back_and_forth",
                _("Go back to the previous workspace"),
                _("Going to the workspace you are on returns to the previous one"),
                False,
            )
        )
        group.add(self._switch("misc:middle_click_paste", _("Paste with the middle button"), "", True))
        group.add(self._switch("cursor:hide_on_key_press", _("Hide the pointer while typing"), "", False))
        group.add(
            self._spin(
                "cursor:inactive_timeout",
                _("Hide an idle pointer"),
                _("Seconds without moving the mouse; 0 never hides"),
                0,
                60,
                1,
                0,
            )
        )
        self.add(group)

    # ------------------------------------------------------------------ rows
    def _initial(self, key: str, default):
        saved = self.store.get(key)
        if saved is not None:
            return saved
        live = core.live_option(key)
        return default if live is None else live

    def _register(self, key: str, row, set_widget: Callable, default) -> None:
        """A ↶ button per option, visible only when this app overrides the value."""
        undo = Gtk.Button(
            icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Back to Omarchy's default")
        )
        undo.add_css_class("flat")
        undo.set_visible(self.store.get(key) is not None)
        undo.connect("clicked", lambda _b: self._reset_keys([key]))
        row.add_suffix(undo)
        self.controls[key] = (set_widget, default, undo)

    def _changed(self, key: str, value) -> None:
        if self._updating:
            return
        self.store.set(key, value)
        self.controls[key][2].set_visible(True)
        if key in ("input:kb_layout", "input:kb_variant"):
            self._sync_keyboard_row()

    def _sync_keyboard_row(self) -> None:
        """Keeps the common layouts list in sync with the Advanced fields (after editing or restoring)."""
        layout = self.entries["input:kb_layout"].get_text().strip()
        variant = self.entries["input:kb_variant"].get_text().strip()
        updating, self._updating = self._updating, True
        try:
            self._kb_row.set_selected(keyboard_index(layout, variant))
        finally:
            self._updating = updating

    def _spin(self, key, title, subtitle, lo, hi, step, default, digits=0) -> Adw.SpinRow:
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_digits(digits)
        row.set_value(to_float(self._initial(key, default), default))
        row.connect(
            "notify::value",
            lambda r, _p: self._changed(key, round(r.get_value(), digits) if digits else int(r.get_value())),
        )
        self._register(key, row, lambda v: row.set_value(to_float(v, default)), default)
        return row

    def _percent(self, key, title, subtitle, lo, hi, default) -> Adw.SpinRow:
        """A 0 to 1 option shown as a percentage."""
        row = Adw.SpinRow.new_with_range(lo, hi, 1)
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_value(round(to_float(self._initial(key, default), default) * 100))
        row.connect("notify::value", lambda r, _p: self._changed(key, round(r.get_value() / 100, 2)))
        self._register(key, row, lambda v: row.set_value(round(to_float(v, default) * 100)), default)
        return row

    def _switch(self, key, title, subtitle, default) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=title, subtitle=subtitle)
        row.set_active(to_bool(self._initial(key, default), default))
        row.connect("notify::active", lambda r, _p: self._changed(key, r.get_active()))
        self._register(key, row, lambda v: row.set_active(to_bool(v, default)), default)
        return row

    def _choice(self, key, title, default, options, subtitle_for: Callable | None = None) -> Adw.ComboRow:
        """List of (value, label); a current value outside the list is added as an extra option."""
        options = list(options)
        values = [str(v) for v, _ in options]
        current = str(self._initial(key, default))
        if current not in values:
            options.append((current, _("Custom ({value})").format(value=current)))
            values.append(current)
        row = Adw.ComboRow(title=title, subtitle=subtitle_for(current) if subtitle_for else "")
        row.set_model(Gtk.StringList.new([label for _, label in options]))
        row.set_selected(values.index(current))

        def on_selected(r, _p) -> None:
            value = options[r.get_selected()][0]
            if subtitle_for:
                r.set_subtitle(subtitle_for(str(value)))
            self._changed(key, value)

        def set_widget(v) -> None:
            v = str(v)
            if v in values:
                row.set_selected(values.index(v))
                if subtitle_for:
                    row.set_subtitle(subtitle_for(v))

        row.connect("notify::selected", on_selected)
        self._register(key, row, set_widget, default)
        return row

    @staticmethod
    def _layout_subtitle(value: str) -> str:
        return next((desc for k, _label, desc in LAYOUTS if k == value), "")

    def _entry(self, key, title, default) -> Adw.EntryRow:
        row = self.entries[key] = Adw.EntryRow(title=title)
        row.set_text(str(self._initial(key, default) or ""))
        row.set_show_apply_button(True)
        row.connect("apply", lambda r: self._changed(key, r.get_text().strip()))
        self._register(key, row, lambda v: row.set_text(str(v or "")), default)
        return row

    def _keyboard_row(self) -> Adw.ComboRow:
        """Shortcut to the most common layouts; everything else is under Advanced."""
        layout = str(self._initial("input:kb_layout", "us"))
        variant = str(self._initial("input:kb_variant", "") or "")
        labels = [label for label, _lay, _var in KEYBOARDS] + [_("Custom (see Advanced)")]
        current = keyboard_index(layout, variant)
        row = self._kb_row = Adw.ComboRow(
            title=_("Keyboard layout"), subtitle=_("Test by typing accented characters after switching")
        )
        row.set_model(Gtk.StringList.new(labels))
        row.set_selected(current)

        def on_selected(r, _p) -> None:
            i = r.get_selected()
            if i >= len(KEYBOARDS) or self._updating:
                return
            _label, lay, var = KEYBOARDS[i]
            # write directly: _changed would re-sync this same list mid-signal and loop forever
            for key, value in (("input:kb_layout", lay), ("input:kb_variant", var)):
                self.store.set(key, value)
                self.controls[key][2].set_visible(True)
            self._updating = True
            try:
                self.controls["input:kb_layout"][0](lay)
                self.controls["input:kb_variant"][0](var)
            finally:
                self._updating = False

        row.connect("notify::selected", on_selected)
        return row

    # ------------------------------------------------------------------ styles and restoring
    def _apply_preset(self, name: str, values: dict) -> None:
        self._updating = True
        try:
            for key in PRESET_KEYS:
                if key in values:
                    self.store.set(key, values[key])
                    set_widget, _default, undo = self.controls[key]
                    set_widget(values[key])
                    undo.set_visible(True)
                elif self.store.get(key) is not None:
                    self.store.unset(key)
        finally:
            self._updating = False
        restored = [k for k in PRESET_KEYS if k not in values]
        if restored:
            # what went back to the default is only known after Hyprland reloads
            GLib.timeout_add(1200, self._sync_from_live, restored)
        self.win.toast(_("{name} style applied").format(name=name))

    def _reset_keys(self, keys: list[str]) -> None:
        for key in keys:
            self.store.unset(key)
        GLib.timeout_add(1200, self._sync_from_live, keys)

    def _sync_from_live(self, keys: list[str]) -> bool:
        def read() -> dict:
            return {k: core.live_option(k) for k in keys}

        def apply(result) -> None:
            if isinstance(result, Exception):
                return
            self._updating = True
            try:
                for key, value in result.items():
                    if key not in self.controls or self.store.get(key) is not None:
                        continue
                    set_widget, default, undo = self.controls[key]
                    set_widget(default if value is None else value)
                    undo.set_visible(False)
                if "input:kb_layout" in result or "input:kb_variant" in result:
                    self._sync_keyboard_row()
            finally:
                self._updating = False

        bg(read, apply)
        return False

    def _reset_all(self) -> None:
        self.store.reset_options()
        GLib.timeout_add(1200, self._sync_from_live, list(self.controls))
        self.win.toast(_("Hyprland options restored"))

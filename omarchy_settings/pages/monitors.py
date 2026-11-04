"""Displays page: drag-and-drop arrangement, resolution, refresh rate, scale, rotation, VRR, mirroring, brightness."""

from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from .. import core, displays, layout
from ..i18n import _, ngettext
from ..ui import Debouncer, bg, button_row, combo_row, set_changed, spin_row, switch_row, to_float

SCALES = [1, 1.25, 1.333333, 1.5, 1.6, 1.666667, 2, 2.5, 3]
TRANSFORMS = [
    _("Normal"),
    "90°",
    "180°",
    "270°",
    _("Flipped"),
    _("Flipped + 90°"),
    _("Flipped + 180°"),
    _("Flipped + 270°"),
]
VRR = [_("Off"), _("On"), _("Fullscreen only")]
CONFIRM_SECONDS = 15
# Changes that can make the screen unreadable ask for confirmation, with an automatic revert.
RISKY = ("mode", "scale", "transform", "disabled", "mirror", "bitdepth")


def scale_label(value: float) -> str:
    return f"{value:g}×" if value == round(value, 2) else f"{value:.2f}×"


class MonitorLayout(Gtk.DrawingArea):
    """Displays drawn to scale; drag to position them, they snap to each other's edges."""

    PAD = 18
    SNAP_PX = 16  # on-screen distance to snap to an edge

    def __init__(self, rects: list[layout.Rect], on_change):
        super().__init__(hexpand=True, content_height=320)
        self.rects = list(rects)
        self.on_change = on_change
        self._drag: tuple[int, layout.Rect] | None = None
        self._view: tuple[float, float, float] | None = None  # frozen while dragging
        self.set_draw_func(self._draw)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_begin)
        drag.connect("drag-update", self._on_update)
        drag.connect("drag-end", self._on_end)
        self.add_controller(drag)
        motion = Gtk.EventControllerMotion()
        motion.connect(
            "motion",
            lambda _c, x, y: self.set_cursor_from_name(
                "grabbing" if self._drag else "grab" if self._hit(x, y) is not None else None
            ),
        )
        self.add_controller(motion)

    def set_rects(self, rects: list[layout.Rect]) -> None:
        if self._drag is None:
            self.rects = list(rects)
            self.queue_draw()

    # -- converting between logical pixels and the drawing area
    def _compute_view(self) -> tuple[float, float, float]:
        x0, y0 = min(r.x for r in self.rects), min(r.y for r in self.rects)
        x1, y1 = max(r.right for r in self.rects), max(r.bottom for r in self.rects)
        # a whole display's worth of margin around, so any display fits on any side
        mx, my = max(r.w for r in self.rects), max(r.h for r in self.rects)
        x0, y0, x1, y1 = x0 - mx, y0 - my, x1 + mx, y1 + my
        w, h = max(self.get_width() - 2 * self.PAD, 1), max(self.get_height() - 2 * self.PAD, 1)
        k = min(w / (x1 - x0), h / (y1 - y0))
        ox = self.PAD + (w - (x1 - x0) * k) / 2 - x0 * k
        oy = self.PAD + (h - (y1 - y0) * k) / 2 - y0 * k
        return k, ox, oy

    def _view_now(self) -> tuple[float, float, float]:
        return self._view or self._compute_view()

    def _hit(self, x: float, y: float) -> int | None:
        if not self.rects:
            return None
        k, ox, oy = self._view_now()
        for i in reversed(range(len(self.rects))):
            r = self.rects[i]
            if ox + r.x * k <= x <= ox + r.right * k and oy + r.y * k <= y <= oy + r.bottom * k:
                return i
        return None

    # -- dragging
    def _on_begin(self, gesture, x, y) -> None:
        i = self._hit(x, y)
        if i is None:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        self._view = self._compute_view()
        self.rects.append(self.rects.pop(i))  # the dragged one is drawn on top
        self._drag = (len(self.rects) - 1, self.rects[-1])
        self.set_cursor_from_name("grabbing")
        self.queue_draw()

    def _on_update(self, _gesture, dx, dy) -> None:
        if self._drag is None:
            return
        i, start = self._drag
        k, ox, oy = self._view
        # keep the dragged display inside the visible area
        x = min(max(start.x + dx / k, -ox / k), (self.get_width() - ox) / k - start.w)
        y = min(max(start.y + dy / k, -oy / k), (self.get_height() - oy) / k - start.h)
        moved = start.moved(round(x), round(y))
        self.rects[i] = layout.snap(moved, self.rects[:i] + self.rects[i + 1 :], self.SNAP_PX / k)
        self.queue_draw()

    def _on_end(self, _gesture, _dx, _dy) -> None:
        if self._drag is None:
            return
        i, start = self._drag
        self._drag, self._view = None, None
        self.rects[i] = layout.settle(self.rects[i], self.rects[:i] + self.rects[i + 1 :])
        self.rects = layout.normalize(self.rects)
        self.set_cursor_from_name("grab")
        self.queue_draw()
        self.on_change(list(self.rects))

    # -- drawing
    def _draw(self, _area, cr, _w, _h) -> None:
        if not self.rects:
            return
        k, ox, oy = self._view_now()
        fg = self.get_color()
        accent = (
            Adw.StyleManager.get_default().get_accent_color_rgba()
            if hasattr(Adw.StyleManager, "get_accent_color_rgba")
            else None
        )
        dragged = self._drag[0] if self._drag else None
        for i, r in enumerate(self.rects):
            x, y, w, h = ox + r.x * k, oy + r.y * k, r.w * k, r.h * k
            rounded(cr, x + 1, y + 1, w - 2, h - 2, 6)
            if i == dragged and accent:
                cr.set_source_rgba(accent.red, accent.green, accent.blue, 0.85)
            else:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
            cr.fill_preserve()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.45)
            cr.set_line_width(1.5)
            cr.stroke()

            text = Pango.Layout.new(self.get_pango_context())
            text.set_alignment(Pango.Alignment.CENTER)
            name = GLib.markup_escape_text(r.name)
            # full label, name only, or nothing, depending on the space at the current scale
            for markup in (f"<b>{name}</b>\n<small>{r.w}×{r.h}</small>", f"<small><b>{name}</b></small>", None):
                if markup is None:
                    break
                text.set_markup(markup, -1)
                tw, th = text.get_pixel_size()
                if tw <= w - 6 and th <= h - 4:
                    break
            if markup is None:
                continue
            if i == dragged and accent:
                cr.set_source_rgba(1, 1, 1, 1)
            else:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.9)
            cr.move_to(x + (w - tw) / 2, y + (h - th) / 2)
            PangoCairo.show_layout(cr, text)


def rounded(cr, x: float, y: float, w: float, h: float, r: float) -> None:
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.14159)
    cr.arc(x + r, y + r, r, 3.14159, 4.71239)
    cr.close_path()


class MonitorsPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store
        self.groups: list[Adw.PreferencesGroup] = []
        self.monitors: list[dict] = []
        self._dialog = None
        self._brightness: dict[str, Debouncer] = {}
        self.layout: MonitorLayout | None = None
        self.pos_rows: dict[str, tuple[Adw.SpinRow, Adw.SpinRow]] = {}
        self._syncing = False

        display = Adw.PreferencesGroup(title=_("Display"))
        display.add(button_row(_("Reload"), _("Reads the connected displays again"), _("Reload"), self.refresh))
        self.add(display)

        footer = Adw.PreferencesGroup(
            description=_(
                "Settings are stored in {file} and take priority over the rest of your config. "
                "'Restore' returns to what your config says."
            ).format(file=core.home_path(core.HYPR_MANAGED)),
        )
        self.add(footer)
        self.footer = footer
        self.refresh()

    # -- building
    def refresh(self) -> None:
        bg(core.list_monitors, self._populate)

    def _populate(self, monitors) -> None:
        if isinstance(monitors, Exception):
            monitors = []
        for group in self.groups:
            self.remove(group)
        self.groups = []
        self.layout = None
        self.pos_rows = {}
        self.monitors = sorted(monitors, key=lambda m: (m.get("x", 0), m.get("y", 0)))
        self.remove(self.footer)
        arrangement = self._layout_group()
        if arrangement:
            self.groups.append(arrangement)
            self.add(arrangement)
        if not self.monitors:
            empty = Adw.PreferencesGroup(title=_("Displays"), description=_("hyprctl found no displays."))
            self.groups.append(empty)
            self.add(empty)
        for mon in self.monitors:
            group = self._monitor_group(mon)
            self.groups.append(group)
            self.add(group)
        self.add(self.footer)

    def _layout_group(self) -> Adw.PreferencesGroup | None:
        rects = self._rects()
        if len(rects) < 2:
            return None
        group = Adw.PreferencesGroup(
            title=_("Arrangement"),
            description=_(
                "Drag the displays with the mouse; they snap to each other's edges. "
                "The position is applied when you let go."
            ),
        )
        frame = Gtk.Frame()
        self.layout = MonitorLayout(rects, self._on_arranged)
        frame.set_child(self.layout)
        group.add(frame)
        return group

    def _rects(self) -> list[layout.Rect]:
        """Active, non-mirrored displays, in logical pixels."""
        rects = []
        for mon in self.monitors:
            rule = self._rule(mon)
            if rule.get("disabled") or rule.get("mirror"):
                continue
            w, h = layout.logical_size(
                str(rule.get("mode", "")),
                to_float(rule.get("scale"), 1.0),
                int(rule.get("transform", 0)),
                (mon["width"], mon["height"]),
            )
            x, y = self._position(rule, mon)
            rects.append(layout.Rect(mon["name"], x, y, w, h))
        return rects

    def _on_arranged(self, rects: list[layout.Rect]) -> None:
        by_name = {m["name"]: m for m in self.monitors}
        moved = 0
        self._syncing = True  # the spin rows below follow along without causing extra changes
        try:
            for r in rects:
                mon = by_name.get(r.name)
                if mon is None or self._position(self._rule(mon), mon) == (r.x, r.y):
                    continue
                self._change(mon, position=f"{r.x}x{r.y}")
                moved += 1
                if r.name in self.pos_rows:
                    xrow, yrow = self.pos_rows[r.name]
                    xrow.set_value(r.x)
                    yrow.set_value(r.y)
        finally:
            self._syncing = False
        if moved:
            self.win.toast(_("Display positions applied"))

    def _rule(self, mon: dict) -> dict:
        return self.store.get_monitor(mon["name"]) or core.live_rule(mon)

    def _monitor_group(self, mon: dict) -> Adw.PreferencesGroup:
        name = mon["name"]
        rule = self._rule(mon)
        disabled = bool(rule.get("disabled"))
        model = " ".join(p for p in (mon.get("make"), mon.get("model")) if p) or mon.get("description", "")
        size = f"{mon['width']}×{mon['height']} @ {mon['refreshRate']:.2f} Hz"
        desc = f"{model} · {_('disabled') if disabled else size}"
        if self.store.get_monitor(name):
            desc += " · " + _("adjusted by this app")
        group = Adw.PreferencesGroup(title=name, description=desc)

        group.add(
            switch_row(
                _("Enabled"),
                _("Turning it off removes the display from the desktop"),
                not disabled,
                lambda on: self._set_enabled(mon, on),
            )
        )
        if disabled:
            group.add(self._restore_row(name))
            return group

        modes = list(dict.fromkeys(mon.get("availableModes") or []))
        current_mode = str(rule.get("mode", ""))
        if current_mode and current_mode not in modes:
            modes.insert(0, current_mode)
        if modes:
            group.add(
                combo_row(
                    _("Resolution and refresh rate"),
                    _("Modes the display advertises"),
                    modes,
                    modes.index(current_mode) if current_mode in modes else 0,
                    lambda i: self._change(mon, mode=modes[i]),
                )
            )

        scales = list(SCALES)
        current_scale = to_float(rule.get("scale"), 1.0)
        if not any(abs(s - current_scale) < 0.001 for s in scales):
            scales.append(current_scale)
            scales.sort()
        group.add(
            combo_row(
                _("Scale"),
                _("Interface size on this display"),
                [scale_label(s) for s in scales],
                min(range(len(scales)), key=lambda i: abs(scales[i] - current_scale)),
                lambda i: self._change(mon, scale=scales[i]),
            )
        )

        group.add(
            combo_row(
                _("Rotation"),
                _("For portrait displays use 90° or 270°"),
                TRANSFORMS,
                int(rule.get("transform", 0)),
                lambda i: self._change(mon, transform=i),
            )
        )

        x, y = self._position(rule, mon)
        xrow = spin_row(
            _("Horizontal position (X)"),
            _("In logical pixels; you can also drag it in Arrangement"),
            -16384,
            16384,
            10,
            x,
            lambda v: self._move(mon, x=v),
        )
        yrow = spin_row(
            _("Vertical position (Y)"), _("In logical pixels"), -16384, 16384, 10, y, lambda v: self._move(mon, y=v)
        )
        self.pos_rows[name] = (xrow, yrow)
        group.add(xrow)
        group.add(yrow)

        group.add(
            combo_row(
                _("Variable refresh rate (VRR / FreeSync)"),
                _("Reduces tearing in games and videos"),
                VRR,
                int(rule.get("vrr", 0)),
                lambda i: self._change(mon, vrr=i),
            )
        )

        others = [m["name"] for m in self.monitors if m["name"] != name]
        if others:
            options = [_("Don't mirror")] + others
            current = rule.get("mirror")
            group.add(
                combo_row(
                    _("Mirror"),
                    _("Shows the same content as another display"),
                    options,
                    options.index(current) if current in options else 0,
                    lambda i: self._change(mon, mirror=options[i] if i else None),
                )
            )

        group.add(
            switch_row(
                _("10-bit color"),
                _("Only enable it if the display and cable support it"),
                rule.get("bitdepth") == 10,
                lambda on: self._change(mon, bitdepth=10 if on else None),
            )
        )

        if core.have("omarchy-brightness-display"):
            # brightness arrives later (DDC is slow); 'Restore' stays the last row
            bg(lambda: displays.brightness(name), lambda value: self._add_brightness(group, name, value))
        else:
            group.add(self._restore_row(name))
        return group

    def _restore_row(self, name: str) -> Adw.ActionRow:
        row = button_row(
            _("Restore this display"),
            _("Returns to what is in monitors.lua"),
            _("Restore"),
            lambda: self._restore(name),
        )
        set_changed(row, self.store.get_monitor(name) is not None)
        return row

    @staticmethod
    def _position(rule: dict, mon: dict) -> tuple[int, int]:
        m = re.fullmatch(r"(-?\d+)x(-?\d+)", str(rule.get("position", "")))
        return (int(m.group(1)), int(m.group(2))) if m else (mon.get("x", 0), mon.get("y", 0))

    # -- changes
    def _change(self, mon: dict, **fields) -> None:
        before = self.store.get_monitor(mon["name"])
        rule = self._rule(mon)
        rule.pop("disabled", None)
        for key, value in fields.items():
            if value is None:
                rule.pop(key, None)
            else:
                rule[key] = value
        self.store.set_monitor(rule)
        if any(k in RISKY for k in fields):
            self._confirm(mon["name"], before)

    def _move(self, mon: dict, x: int | None = None, y: int | None = None) -> None:
        if self._syncing:
            return
        cur_x, cur_y = self._position(self._rule(mon), mon)
        self._change(mon, position=f"{cur_x if x is None else x}x{cur_y if y is None else y}")
        if self.layout:
            self.layout.set_rects(self._rects())

    def _set_enabled(self, mon: dict, on: bool) -> None:
        if not on:
            active = [m for m in self.monitors if not self._rule(m).get("disabled")]
            if len(active) <= 1:
                self.win.toast(_("The only active display can't be turned off"))
                GLib.timeout_add(300, self._reload_later)
                return
            before = self.store.get_monitor(mon["name"])
            self.store.set_monitor({"output": mon["name"], "disabled": True})
            self._confirm(mon["name"], before)
        else:
            rule = self._rule(mon)
            rule.pop("disabled", None)
            rule.setdefault("mode", "preferred")
            rule.setdefault("position", "auto")
            rule.setdefault("scale", 1)
            self.store.set_monitor(rule)
        GLib.timeout_add(900, self._reload_later)

    def _restore(self, name: str) -> None:
        if self.store.get_monitor(name) is None:
            self.win.toast(_("{name} already uses monitors.lua").format(name=name))
            return
        self.store.unset_monitor(name)
        self.win.toast(_("{name} restored").format(name=name))
        GLib.timeout_add(900, self._reload_later)

    def _reload_later(self) -> bool:
        self.refresh()
        return False

    # -- confirmation with automatic revert
    def _confirm(self, name: str, before: dict | None) -> None:
        if self._dialog is not None or not hasattr(Adw, "AlertDialog"):
            return  # a confirmation is already open; it covers this change too
        remaining = [CONFIRM_SECONDS]
        dialog = Adw.AlertDialog(heading=_("Keep these display settings?"))
        dialog.add_response("revert", _("Revert"))
        dialog.add_response("keep", _("Keep"))
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("keep")
        dialog.set_close_response("revert")

        def body() -> None:
            dialog.set_body(
                ngettext(
                    "Changes to {name} will be reverted in {seconds} second.",
                    "Changes to {name} will be reverted in {seconds} seconds.",
                    remaining[0],
                ).format(name=name, seconds=remaining[0])
            )

        def tick() -> bool:
            remaining[0] -= 1
            if remaining[0] <= 0:
                dialog.close()  # triggers the close response: revert
                return False
            body()
            return True

        def on_response(_d, response: str) -> None:
            GLib.source_remove(timer)
            self._dialog = None
            if response != "keep":
                if before is None:
                    self.store.unset_monitor(name)
                else:
                    self.store.set_monitor(before)
                self.win.toast(_("Display settings reverted"))
            GLib.timeout_add(900, self._reload_later)

        body()
        timer = GLib.timeout_add_seconds(1, tick)
        dialog.connect("response", on_response)
        self._dialog = dialog
        GLib.timeout_add(600, lambda: dialog.present(self.win) and False)

    # -- extras
    def _add_brightness(self, group: Adw.PreferencesGroup, name: str, value) -> None:
        if group not in self.groups:
            return
        if not isinstance(value, int):
            group.add(self._restore_row(name))
            return
        row = Adw.ActionRow(title=_("Brightness"), subtitle=_("Via DDC/CI"))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        scale.set_value(value)
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_size_request(260, -1)
        scale.set_valign(Gtk.Align.CENTER)
        scale.connect("value-changed", lambda s: self._on_brightness(name, s.get_value()))
        row.add_suffix(scale)
        group.add(row)
        group.add(self._restore_row(name))

    def _on_brightness(self, name: str, value: float) -> None:
        if name not in self._brightness:
            self._brightness[name] = Debouncer(
                300,
                lambda v: bg(lambda: displays.set_brightness(name, int(v))),
            )
        self._brightness[name](value)

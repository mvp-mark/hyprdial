"""Página de atalhos: os do Omarchy (mudar de tecla, desativar, restaurar) e atalhos próprios."""
from __future__ import annotations

import copy

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import keybinds as kb
from ..ui import bg, button_row

CSS = b"""
.oms-keycap {
  border: 1px solid alpha(currentColor, 0.25);
  border-bottom-width: 2px;
  border-radius: 6px;
  padding: 0 6px;
  min-width: 14px;
  font-size: 0.9em;
  font-weight: 600;
}
.oms-keycaps.dim { opacity: 0.45; }
"""
MODIFIER_KEYS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
                 "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "ISO_Level3_Shift", "Caps_Lock", "Num_Lock"}
GDK_MODS = [(Gdk.ModifierType.SUPER_MASK, "SUPER"), (Gdk.ModifierType.SHIFT_MASK, "SHIFT"),
            (Gdk.ModifierType.CONTROL_MASK, "CTRL"), (Gdk.ModifierType.ALT_MASK, "ALT")]

_css_installed = False


def install_css() -> None:
    global _css_installed
    if _css_installed:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_installed = True


def keycaps_box(keys: str | None, dim: bool = False) -> Gtk.Box:
    box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
    box.add_css_class("oms-keycaps")
    if dim:
        box.add_css_class("dim")
    if not keys:
        box.append(Gtk.Label(label="—"))
        return box
    for i, cap in enumerate(kb.keycaps(keys)):
        if i:
            box.append(Gtk.Label(label="+", css_classes=["dim-label"]))
        box.append(Gtk.Label(label=cap, css_classes=["oms-keycap"]))
    return box


class KeyDialog(Adw.AlertDialog):
    """Escolha de teclas: grava a combinação pressionada, com modificadores ajustáveis à mão.

    O Hyprland intercepta combinações que já estão em uso, então elas podem não chegar aqui;
    nesse caso basta marcar os modificadores e gravar só a tecla final.
    """

    def __init__(self, heading: str, keys: str | None, conflicts, on_save, custom: dict | None = None):
        super().__init__(heading=heading)
        self.conflicts = conflicts  # função: teclas -> (mensagem, bloqueia)
        self.on_save = on_save
        mods, self.key = kb.split_keys(keys) if keys else (["SUPER"], "")
        self.recording = False

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.is_custom = custom is not None
        if self.is_custom:
            group = Adw.PreferencesGroup()
            self.desc_row = Adw.EntryRow(title="Nome (aparece na lista de atalhos)", text=custom.get("desc", ""))
            self.kind_row = Adw.ComboRow(title="O que fazer")
            self.kind_row.set_model(Gtk.StringList.new([label for _, label in kb.KINDS]))
            kinds = [k for k, _ in kb.KINDS]
            self.kind_row.set_selected(kinds.index(custom.get("kind", "launch")))
            self.cmd_row = Adw.EntryRow(title="Comando (ex.: firefox, gimp, btop)", text=custom.get("command", ""))
            for row in (self.desc_row, self.kind_row, self.cmd_row):
                group.add(row)
            self.desc_row.connect("changed", lambda *_: self._update())
            self.cmd_row.connect("changed", lambda *_: self._update())
            body.append(group)

        self.mod_buttons = {}
        mods_box = Gtk.Box(halign=Gtk.Align.CENTER, css_classes=["linked"])
        for _, name in kb.MOD_BITS:
            btn = Gtk.ToggleButton(label=name.capitalize() if name != "CTRL" else "Ctrl", active=name in mods)
            btn.connect("toggled", lambda *_: self._update())
            self.mod_buttons[name] = btn
            mods_box.append(btn)
        body.append(mods_box)

        self.record_btn = Gtk.Button(halign=Gtk.Align.CENTER, css_classes=["pill"])
        self.record_btn.connect("clicked", lambda _b: self._set_recording(not self.recording))
        body.append(self.record_btn)
        self.preview = Gtk.Box(halign=Gtk.Align.CENTER)
        body.append(self.preview)
        self.message = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, css_classes=["dim-label"])
        body.append(self.message)
        self.set_extra_child(body)

        self.add_response("cancel", "Cancelar")
        self.add_response("save", "Salvar")
        self.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        self.set_close_response("cancel")
        self.connect("response", self._on_response)

        keys_ctl = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys_ctl.connect("key-pressed", self._on_key)
        self.add_controller(keys_ctl)
        self._set_recording(not self.key)

    def keys(self) -> str | None:
        if not self.key:
            return None
        return kb.join_keys([m for m, b in self.mod_buttons.items() if b.get_active()], self.key)

    def custom(self) -> dict:
        return {"desc": self.desc_row.get_text().strip(), "kind": kb.KINDS[self.kind_row.get_selected()][0],
                "command": self.cmd_row.get_text().strip()}

    def _set_recording(self, on: bool) -> None:
        self.recording = on
        self.record_btn.set_label("Pressione a tecla…" if on else "Gravar outra tecla")
        if on:
            self.record_btn.add_css_class("suggested-action")
        else:
            self.record_btn.remove_css_class("suggested-action")
        self._update()

    def _on_key(self, _ctl, keyval, keycode, state) -> bool:
        if not self.recording:
            return False
        name = Gdk.keyval_name(keyval) or ""
        if name in MODIFIER_KEYS:
            return True
        # tecla base, sem o efeito do Shift (Shift+1 grava "1", não "!")
        ok, _keys, keyvals = Gdk.Display.get_default().map_keycode(keycode)
        base = keyvals[0] if ok and keyvals else keyval
        self.key = (Gdk.keyval_name(Gdk.keyval_to_lower(base)) or name).upper()
        for mask, mod in GDK_MODS:
            self.mod_buttons[mod].set_active(bool(state & mask))
        self._set_recording(False)
        return True

    def _update(self) -> None:
        child = self.preview.get_first_child()
        if child:
            self.preview.remove(child)
        keys = self.keys()
        self.preview.append(keycaps_box(keys))
        msg, blocked = ("", False)
        if self.recording:
            msg = ("Pressione a combinação. Se o sistema já usa essa combinação ela pode não chegar aqui: "
                   "marque os modificadores acima e grave só a tecla.")
        elif keys:
            msg, blocked = self.conflicts(keys)
            if not msg and not any(b.get_active() for b in self.mod_buttons.values()) and len(self.key) == 1:
                msg = "Sem modificador, essa tecla deixa de funcionar para digitar."
        if self.is_custom and not (self.desc_row.get_text().strip() and self.cmd_row.get_text().strip()):
            blocked = True
        self.message.set_label(msg)
        self.set_response_enabled("save", bool(keys) and not blocked and not self.recording)

    def _on_response(self, _d, response: str) -> None:
        if response == "save" and self.keys():
            self.on_save(self)


class ShortcutsPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        install_css()
        self.win = win
        self.store = win.store
        self.entries: list[kb.Entry] = []
        self.groups: list[Adw.PreferencesGroup] = []
        self.rows: list[tuple[Gtk.Widget, str, Adw.ExpanderRow | None]] = []
        self.expanders: dict[str, Adw.ExpanderRow] = {}
        self._busy = False

        top = Adw.PreferencesGroup(description="Os atalhos padrão vêm do Omarchy. Mudanças feitas aqui ficam em "
                                               "~/.config/hypr/omarchy-settings.lua e podem ser desfeitas com ↶.")
        header = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(hexpand=True, placeholder_text="Buscar por nome ou tecla (ex.: browser, super+b)")
        self.search.connect("search-changed", lambda _e: self._filter())
        new = Gtk.Button(label="Novo atalho", css_classes=["suggested-action"])
        new.connect("clicked", lambda _b: self._edit_custom(None))
        header.append(self.search)
        header.append(new)
        top.add(header)
        self.add(top)

        self.footer = Adw.PreferencesGroup()
        self.footer.add(button_row("Restaurar todos os atalhos", "Desfaz todas as mudanças e apaga os atalhos próprios",
                                   "Restaurar", self._confirm_reset, "destructive-action"))
        self.add(self.footer)
        self.reload()

    # ------------------------------------------------------------------ montagem
    def reload(self) -> None:
        state = copy.deepcopy(self.store.bindings)
        bg(lambda: kb.build_entries(kb.live_binds(), kb.source_binds(), state), self._populate)

    def _populate(self, entries) -> None:
        if isinstance(entries, Exception):
            self.win.toast("Não foi possível ler os atalhos")
            return
        self.entries = entries
        expanded = {cat: exp.get_expanded() for cat, exp in self.expanders.items()}
        for group in self.groups:
            self.remove(group)
        self.groups, self.rows, self.expanders = [], [], {}
        self.remove(self.footer)

        custom = Adw.PreferencesGroup(title="Seus atalhos")
        items = self.store.bindings.get("custom", [])
        if not items:
            custom.add(Adw.ActionRow(title="Nenhum atalho próprio",
                                     subtitle="Use “Novo atalho” para abrir um app ou rodar um comando"))
        for index, item in enumerate(items):
            row = self._custom_row(index, item)
            custom.add(row)
            self.rows.append((row, f"{item['desc']} {item['command']} {self._hay(item['keys'])}".lower(), None))
        self._add_group(custom)

        omarchy = Adw.PreferencesGroup(title="Atalhos do Omarchy")
        for cat in kb.CATEGORY_ORDER:
            cat_entries = [e for e in entries if e.category == cat]
            if not cat_entries:
                continue
            changed = sum(e.override is not None for e in cat_entries)
            exp = Adw.ExpanderRow(title=kb.CATEGORIES[cat],
                                  subtitle=f"{len(cat_entries)} atalhos" + (f" · {changed} alterados" if changed else ""),
                                  expanded=expanded.get(cat, False))
            for e in cat_entries:
                row = self._entry_row(e)
                exp.add_row(row)
                self.rows.append((row, f"{e.desc} {self._hay(e.keys)} {self._hay(e.current_keys)}".lower(), exp))
            self.expanders[cat] = exp
            omarchy.add(exp)
        self._add_group(omarchy)
        self.add(self.footer)
        self._filter()

    def _add_group(self, group: Adw.PreferencesGroup) -> None:
        self.groups.append(group)
        self.add(group)

    @staticmethod
    def _hay(keys: str | None) -> str:
        """Texto de busca para teclas: 'super+shift+b' e os nomes amigáveis."""
        if not keys:
            return ""
        return f"{kb.canon(keys).replace(' ', '')} {' '.join(kb.keycaps(keys))} {'+'.join(kb.keycaps(keys))}"

    def _entry_row(self, e: kb.Entry) -> Adw.ActionRow:
        row = Adw.ActionRow(title=e.desc, use_markup=False)
        disabled = e.override is not None and not e.override.get("keys")
        if disabled:
            row.set_subtitle("Desativado")
        elif e.override is not None:
            row.set_subtitle(f"Antes: {' + '.join(kb.keycaps(e.keys))}")
        row.add_suffix(keycaps_box(e.current_keys or e.keys, dim=disabled))

        edit = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                          sensitive=e.action is not None and not disabled,
                          tooltip_text="Mudar a tecla" if e.action else e.locked)
        edit.connect("clicked", lambda _b: self._edit_entry(e))
        row.add_suffix(edit)
        if e.override is not None:
            undo = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                              tooltip_text="Voltar ao padrão do Omarchy")
            undo.connect("clicked", lambda _b: self._restore(e))
            row.add_suffix(undo)
        switch = Gtk.Switch(active=not disabled, valign=Gtk.Align.CENTER, tooltip_text="Ativo")
        switch.connect("notify::active", lambda s, _p: self._toggle(e, s.get_active()))
        row.add_suffix(switch)
        return row

    def _custom_row(self, index: int, item: dict) -> Adw.ActionRow:
        kind = dict(kb.KINDS).get(item["kind"], "")
        row = Adw.ActionRow(title=item["desc"], subtitle=f"{kind}: {item['command']}", use_markup=False)
        row.add_suffix(keycaps_box(item["keys"]))
        edit = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                          tooltip_text="Editar")
        edit.connect("clicked", lambda _b: self._edit_custom(index))
        delete = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                            tooltip_text="Apagar")
        delete.connect("clicked", lambda _b: self._delete_custom(index))
        row.add_suffix(edit)
        row.add_suffix(delete)
        return row

    def _filter(self) -> None:
        q = self.search.get_text().strip().lower().replace(" ", "")
        visible: dict[Adw.ExpanderRow, int] = {}
        for row, hay, exp in self.rows:
            show = not q or q in hay.replace(" ", "") or q in hay
            row.set_visible(show)
            if exp is not None:
                visible[exp] = visible.get(exp, 0) + show
        for exp, count in visible.items():
            exp.set_visible(count > 0)
            if q:
                exp.set_expanded(count > 0)

    # ------------------------------------------------------------------ conflitos
    def _who_uses(self, keys: str, ignore: str | None = None, ignore_custom: int | None = None):
        c = kb.canon(keys)
        for i, item in enumerate(self.store.bindings.get("custom", [])):
            if i != ignore_custom and kb.canon(item["keys"]) == c:
                return "custom", item
        for e in self.entries:
            if e.keys != ignore and e.current_keys and kb.canon(e.current_keys) == c:
                return "entry", e
        return None, None

    def _conflict_check(self, ignore: str | None = None, ignore_custom: int | None = None):
        def check(keys: str) -> tuple[str, bool]:
            kind, who = self._who_uses(keys, ignore, ignore_custom)
            if kind == "custom":
                return f"Já usado pelo seu atalho “{who['desc']}”.", True
            if kind == "entry":
                return f"Já usado por “{who.desc}”, que será desativado.", False
            return "", False

        return check

    def _take_keys(self, state: dict, keys: str, ignore: str | None = None) -> None:
        """Desativa o atalho do Omarchy que hoje usa estas teclas."""
        kind, who = self._who_uses(keys, ignore)
        if kind == "entry":
            state["overrides"][who.keys] = {"desc": who.desc}

    # ------------------------------------------------------------------ ações
    def _edit_entry(self, e: kb.Entry) -> None:
        def save(dialog: KeyDialog) -> None:
            state = copy.deepcopy(self.store.bindings)
            keys = dialog.keys()
            self._take_keys(state, keys, ignore=e.keys)
            if kb.canon(keys) == kb.canon(e.keys):
                state["overrides"].pop(e.keys, None)
            else:
                state["overrides"][e.keys] = {"desc": e.desc, "keys": keys, "action": e.action}
            self._apply(state, f"“{e.desc}” agora é {' + '.join(kb.keycaps(keys))}", expect=keys)

        KeyDialog(f"Tecla para “{e.desc}”", e.current_keys or e.keys, self._conflict_check(ignore=e.keys),
                  save).present(self.win)

    def _toggle(self, e: kb.Entry, on: bool) -> None:
        if self._busy:
            return
        state = copy.deepcopy(self.store.bindings)
        if on:
            if self._who_uses(e.keys, ignore=e.keys)[0]:
                self.win.toast("Essas teclas estão em uso por outro atalho; mude a tecla dele antes")
                GLib.idle_add(self.reload)
                return
            state["overrides"].pop(e.keys, None)
        else:
            state["overrides"][e.keys] = {"desc": e.desc}
        self._apply(state, f"“{e.desc}” {'ativado' if on else 'desativado'}")

    def _restore(self, e: kb.Entry) -> None:
        state = copy.deepcopy(self.store.bindings)
        state["overrides"].pop(e.keys, None)
        kind, who = self._who_uses(e.keys, ignore=e.keys)
        if kind == "custom":
            self.win.toast(f"A tecla original está em uso por “{who['desc']}”")
            return
        if kind == "entry":
            state["overrides"][who.keys] = {"desc": who.desc}
        self._apply(state, f"“{e.desc}” voltou ao padrão")

    def _edit_custom(self, index: int | None) -> None:
        items = self.store.bindings.get("custom", [])
        item = items[index] if index is not None else {}

        def save(dialog: KeyDialog) -> None:
            state = copy.deepcopy(self.store.bindings)
            keys = dialog.keys()
            self._take_keys(state, keys)
            new = {"keys": keys, **dialog.custom()}
            if index is None:
                state["custom"].append(new)
            else:
                state["custom"][index] = new
            self._apply(state, f"Atalho “{new['desc']}” salvo", expect=keys)

        KeyDialog("Novo atalho" if index is None else "Editar atalho", item.get("keys"),
                  self._conflict_check(ignore_custom=index), save, custom=item).present(self.win)

    def _delete_custom(self, index: int) -> None:
        state = copy.deepcopy(self.store.bindings)
        item = state["custom"].pop(index)
        self._apply(state, f"Atalho “{item['desc']}” apagado")

    def _confirm_reset(self) -> None:
        dialog = Adw.AlertDialog(heading="Restaurar todos os atalhos?",
                                 body="Os atalhos do Omarchy voltam ao padrão e os seus atalhos próprios são apagados.")
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("reset", "Restaurar")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "reset" and self._apply(kb.empty_state(),
                                                                              "Atalhos restaurados"))
        dialog.present(self.win)

    def _apply(self, state: dict, ok_msg: str, expect: str | None = None) -> None:
        """Grava, recarrega e confere; se o atalho novo não aparecer no Hyprland, desfaz."""
        previous = copy.deepcopy(self.store.bindings)
        self._busy = True

        def work() -> str | None:
            self.store.apply_bindings(state)
            if expect is None:
                return None
            by_desc = {(tuple(kb.split_keys(s.keys)[0]), s.desc): s for s in kb.source_binds()}
            live = {kb.canon(k) for k in (kb.live_keys(b, by_desc) for b in kb.live_binds()) if k}
            if kb.canon(expect) in live:
                return None
            self.store.apply_bindings(previous)
            return "O Hyprland não aceitou esse atalho; nada foi alterado"

        def done(error) -> None:
            self._busy = False
            if isinstance(error, Exception):
                error = str(error)
            self.win.toast(error or ok_msg)
            self.reload()

        bg(work, done)

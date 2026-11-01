local function universal_clipboard_shortcut(default_mods, default_key)
  return function() end
end

o.bind("SUPER + C", "Universal copy", universal_clipboard_shortcut("CTRL", "C"))
o.bind("SUPER + CTRL + V", "Clipboard manager", "omarchy-shell shell toggle omarchy.clipboard")

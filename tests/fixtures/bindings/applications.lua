-- Essential application bindings.
o.bind("SUPER + RETURN", "Terminal", { omarchy = "terminal" })
o.bind("SUPER + SHIFT + B", "Browser", { omarchy = "browser" })
-- o.bind("SUPER + SHIFT + Q", "Commented out", "never")

if o.preinstalled_bindings_enabled() then
  o.bind( "SUPER + SHIFT + CTRL + G", "Google Messages", { webapp = "https://messages.google.com/web/", focus = true })
end

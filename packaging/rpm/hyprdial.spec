# RPM for Fedora and openSUSE (COPR, OBS). Dependencies follow hyprdial/deps.py; CI builds and installs it on both
# (.github/workflows/tests.yml, job "distros").
Name:           hyprdial
Version:        1.0.0
Release:        1%{?dist}
Summary:        Settings app for Hyprland, with Omarchy integration
License:        MIT
URL:            https://github.com/mvp-mark/hyprdial
Source0:        %{url}/archive/refs/tags/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  gettext
BuildRequires:  python3
BuildRequires:  desktop-file-utils
Requires:       python3
Requires:       python3-gobject
Recommends:     waybar
Recommends:     hypridle
Recommends:     hyprlock
Recommends:     hyprpaper
Recommends:     brightnessctl
%if 0%{?suse_version}
Requires:       typelib(Gtk) = 4.0
Requires:       typelib(Adw) = 1
Recommends:     typelib(NM) = 1.0
%else
Requires:       gtk4
Requires:       libadwaita
Recommends:     NetworkManager-libnm
%endif

%description
A graphical settings app for Hyprland 0.56 or newer (Lua configuration), built with GTK4 and libadwaita:
displays, sound, input, power, connectivity, shortcuts, startup apps, accessibility, language and time. Its
settings go to one generated file, ~/.config/hypr/hyprdial.lua, loaded by a single require line in
hyprland.lua. On Omarchy it also covers themes, the bar, web apps and security setups.

%prep
%autosetup -n %{name}-%{version}

%build
for po in po/*.po; do
  lang=$(basename "$po" .po)
  mkdir -p "hyprdial/locale/$lang/LC_MESSAGES"
  msgfmt -o "hyprdial/locale/$lang/LC_MESSAGES/%{name}.mo" "$po"
done
# pt_PT and other variants without their own catalog use Brazilian Portuguese
mkdir -p hyprdial/locale/pt/LC_MESSAGES
cp hyprdial/locale/pt_BR/LC_MESSAGES/%{name}.mo hyprdial/locale/pt/LC_MESSAGES/

%install
install -d %{buildroot}%{_datadir}/%{name}
cp -r hyprdial %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name __pycache__ -type d -prune -exec rm -rf {} +
python3 -m compileall -q -s %{buildroot} -p / %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_bindir}
printf '#!/bin/sh\nexec env PYTHONPATH=%s python3 -m hyprdial "$@"\n' %{_datadir}/%{name} > %{buildroot}%{_bindir}/%{name}
chmod 755 %{buildroot}%{_bindir}/%{name}
install -Dm644 data/io.github.mvp_mark.Hyprdial.desktop -t %{buildroot}%{_datadir}/applications/

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.mvp_mark.Hyprdial.desktop

%files
%license LICENSE
%doc README.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/io.github.mvp_mark.Hyprdial.desktop

%changelog
* Tue Nov 03 2026 Marcus Vinícius Peixoto Paulo <mvp.paulo@gmail.com> - 1.0.0-1
- First RPM: omarchy-settings renamed to Hyprdial, runs on plain Hyprland

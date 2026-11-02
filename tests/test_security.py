from omarchy_settings import security


def test_states_follow_omarchys_menu(commands):
    commands.codes["omarchy-hw-fingerprint"] = 1  # no reader: no fingerprint row
    commands.codes["omarchy-pkg-present pam-u2f"] = 1
    commands.codes["systemctl is-enabled --quiet sshd"] = 0
    commands.answers["systemctl is-active sshd"] = "active\n"
    assert [(s.key, s.configured, s.detail) for s in security.states()] == [
        ("fido2", False, ""),
        ("sshd", True, "active"),
    ]


def test_fingerprint_with_a_reader(commands):
    states = security.states()  # every command "succeeds" by default
    assert states[0].key == "fingerprint" and states[0].configured


def test_commands_run_in_a_terminal():
    assert security.command("sshd") == [
        "omarchy-launch-floating-terminal-with-presentation",
        "omarchy-setup-security-sshd",
    ]
    assert security.command("fido2", remove=True)[-1] == "omarchy-remove-security-fido2"

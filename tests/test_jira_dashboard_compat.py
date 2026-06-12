"""hermes_cli.jira_dashboard shim points at jira_dashboard.service."""


def test_shim_installs_hermes_cli_jira_dashboard():
    import hermes_cli
    from jira_dashboard import service
    from jira_dashboard.compat import install_hermes_cli_jira_dashboard_shim

    install_hermes_cli_jira_dashboard_shim()

    import hermes_cli.jira_dashboard as jira_mod

    assert jira_mod is service
    assert hermes_cli.jira_dashboard is service
    assert jira_mod.JIRA_MCP_NAME == "jira"

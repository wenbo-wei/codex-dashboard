PYTHON ?= python3
NODE ?= node

.PHONY: check test syntax

check: test syntax

test:
	$(PYTHON) codex-quota/tests/test_codex_dashboard_data.py
	$(PYTHON) codex-quota/tests/test_codex_quota.py
	$(PYTHON) tests/test_installer.py
	$(NODE) codex-quota/tests/test_dashboard_model.mjs

syntax:
	$(PYTHON) -m py_compile \
		codex-panel/codex_app_server.py \
		codex-panel/quota_snapshot.py \
		codex-panel/quota_sni.py \
		codex-quota/codex-dashboard-data \
		codex-quota/codex-quota
	$(PYTHON) -m json.tool \
		extensions/codex-quota-centre@local/metadata.json >/dev/null
	$(NODE) --check \
		extensions/codex-quota-centre@local/extension.js
	$(NODE) --check \
		extensions/codex-quota-centre@local/dashboardModel.mjs
	sh -n scripts/install.sh scripts/uninstall.sh
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck scripts/install.sh scripts/uninstall.sh; \
	fi

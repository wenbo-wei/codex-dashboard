PYTHON ?= /usr/bin/python3
NODE ?= node

.PHONY: check

check:
	$(PYTHON) -m py_compile \
		backend/codex_app_server.py \
		backend/quota_snapshot.py \
		backend/quota_sni.py \
		codex-quota/codex-dashboard-data \
		codex-quota/codex-quota \
		tests/test_dashboard_data.py
	$(PYTHON) -m json.tool \
		extensions/codex-dashboard@wenbo-wei/metadata.json >/dev/null
	$(NODE) --check \
		extensions/codex-dashboard@wenbo-wei/extension.js
	$(NODE) --check \
		extensions/codex-dashboard@wenbo-wei/dashboardModel.mjs
	$(NODE) --check scripts/queue-extension.mjs
	sh -n \
		scripts/install.sh \
		scripts/uninstall.sh \
		tests/fakes/codex \
		tests/fakes/gnome-extensions \
		tests/fakes/gnome-shell \
		tests/fakes/gtk-update-icon-cache \
		tests/fakes/systemctl \
		tests/test-install.sh \
		tests/test-queue-extension.sh
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'
	$(NODE) --test tests/dashboardModel.test.mjs
	sh tests/test-queue-extension.sh
	sh tests/test-install.sh

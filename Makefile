PYTHON ?= python3
NODE ?= node

.PHONY: check

check:
	$(PYTHON) -m py_compile \
		backend/codex_app_server.py \
		backend/quota_snapshot.py \
		backend/quota_sni.py \
		codex-quota/codex-dashboard-data \
		codex-quota/codex-quota
	$(PYTHON) -m json.tool \
		extensions/codex-dashboard@wenbo-wei/metadata.json >/dev/null
	$(NODE) --check \
		extensions/codex-dashboard@wenbo-wei/extension.js
	$(NODE) --check \
		extensions/codex-dashboard@wenbo-wei/dashboardModel.mjs
	sh -n scripts/install.sh scripts/uninstall.sh

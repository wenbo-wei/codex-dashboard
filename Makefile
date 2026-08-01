PYTHON ?= /usr/bin/python3
NODE ?= node

.PHONY: check

check:
	$(PYTHON) -m py_compile \
		backend/codex_app_server.py \
		backend/codex_thread_index.py \
		backend/quota_snapshot.py \
		backend/quota_sni.py \
		backend/task_overviews.py \
		codex-quota/codex-dashboard-data \
		codex-quota/codex-dashboard-task-overviews \
		codex-quota/codex-quota
	$(PYTHON) -m json.tool \
		extensions/codex-dashboard@wenbo-wei/metadata.json >/dev/null
	$(NODE) --check \
		extensions/codex-dashboard@wenbo-wei/extension.js
	$(NODE) --check \
		extensions/codex-dashboard@wenbo-wei/dashboardModel.mjs
	$(NODE) --check scripts/queue-extension.mjs
	sh -n \
		scripts/install.sh \
		scripts/uninstall.sh

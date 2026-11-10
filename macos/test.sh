#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
swiftc Shared/Models.swift Tests/ModelTests.swift -o build/model-tests
build/model-tests
swiftc Shared/Models.swift App/ConnectionStore.swift Tests/ConnectionStoreTests.swift -o build/connection-tests
build/connection-tests
swiftc App/ProcessLock.swift Tests/ProcessLockTests.swift -o build/process-lock-tests
build/process-lock-tests
swiftc Shared/Models.swift Shared/Cache.swift Tests/CacheTests.swift -o build/cache-tests
build/cache-tests
swiftc Shared/Models.swift Shared/Cache.swift App/ConnectionStore.swift App/DetailAnalysisModel.swift App/AppModel.swift Tests/AppModelTests.swift -o build/app-model-tests
build/app-model-tests
swiftc Shared/Models.swift App/ConnectionStore.swift App/DetailAnalysisModel.swift Tests/DetailClientTests.swift -o build/detail-client-tests
build/detail-client-tests
swiftc -D REMOTE_DASHBOARD_TESTS Shared/Models.swift Widget/RemoteDashboard.swift Tests/RemoteDashboardTests.swift -o build/remote-tests
build/remote-tests
python3 Tests/test_configure.py
swiftc -D PREVIEW_TOOL Shared/Models.swift Shared/Cache.swift Shared/Appearance.swift Shared/GlucoseChart.swift Widget/RemoteDashboard.swift Widget/GlucoseWidget.swift Tests/Preview.swift -o build/preview
build/preview "$(pwd)/build/widget-synthetic.png"
swiftc Shared/Models.swift App/StatusBadge.swift Tests/StatusPreview.swift -o build/status-preview
build/status-preview "$(pwd)/build/menubar-states-synthetic.png"

swiftc -D PREVIEW_TOOL Shared/*.swift App/*.swift Tests/InteractionPreview.swift -o build/interaction-preview
build/interaction-preview "$(pwd)/build/report-events-synthetic.png"

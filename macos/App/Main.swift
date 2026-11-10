import SwiftUI
import AppKit

enum AppNavigation {
    static let settings = Notification.Name("com.joviliu.ottai.mirror.settings")
    static let detail = Notification.Name("com.joviliu.ottai.mirror.detail")
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var dashboardWindow: NSWindow?
    private var settingsWindow: NSWindow?
    private var settingsObserver: NSObjectProtocol?
    private var dashboardObserver: NSObjectProtocol?
    private var detailObserver: NSObjectProtocol?
    private var detailWindow: DetailedReportWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        settingsObserver = NotificationCenter.default.addObserver(forName: AppNavigation.settings, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.showSettings() }
        }
        dashboardObserver = DistributedNotificationCenter.default().addObserver(forName: SingleInstance.showDashboard, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.showDashboard() }
        }
        detailObserver = NotificationCenter.default.addObserver(forName: AppNavigation.detail, object: nil, queue: .main) { [weak self] notice in
            guard let selection = notice.object as? DetailReportSelection, selection.valid else { return }
            Task { @MainActor in
                guard let self else { return }
                self.detailWindow?.close()
                self.detailWindow = DetailedReportWindowController(model: AppModel.shared, selection: selection)
                NSApplication.shared.activate(ignoringOtherApps: true)
                self.detailWindow?.showWindow(nil)
            }
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        guard urls.contains(where: { $0.scheme == "ottaimirror" && $0.host == "dashboard" }) else { return }
        showDashboard()
    }

    private func showSettings() {
        if settingsWindow == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 390), styleMask: [.titled,.closable], backing: .buffered, defer: false)
            window.title = "血糖镜像 · 设置"
            window.contentView = NSHostingView(rootView: SettingsView(model: AppModel.shared).padding(24).frame(width:480,height:390))
            window.isReleasedWhenClosed = false
            window.center()
            settingsWindow = window
        }
        NSApplication.shared.activate(ignoringOtherApps: true)
        settingsWindow?.makeKeyAndOrderFront(nil)
    }

    private func showDashboard() {
        if dashboardWindow == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 800),
                                  styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
            window.title = "血糖镜像"
            window.contentView = NSHostingView(rootView: DashboardView(model: AppModel.shared))
            window.isReleasedWhenClosed = false
            window.center()
            dashboardWindow = window
        }
        NSApplication.shared.activate(ignoringOtherApps: true)
        dashboardWindow?.makeKeyAndOrderFront(nil)
    }
}

#if !PREVIEW_TOOL
@main
struct OttaiMirrorApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = AppModel.shared

    init() {
        if !SingleInstance.claim() { exit(0) }
    }

    var body: some Scene {
        MenuBarExtra {
            MenuContent(model: model)
        } label: {
            Image(nsImage: StatusBadge.menuImage(reading: model.latest, now: model.now))
                .accessibilityLabel("血糖 \(model.latest?.display ?? "暂无")，\(StatusBadge.rangeState(reading: model.latest, now: model.now).description)")
                .help(model.latest.map { "血糖 \($0.display) mmol/L · \($0.displayTrend) · \(DisplayTime.time($0.date)) · \(StatusBadge.rangeState(reading: $0, now: model.now).description)" } ?? "血糖镜像 · 等待数据")
        }.menuBarExtraStyle(.window)
    }
}
#endif

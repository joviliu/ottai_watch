import AppKit
import SwiftUI
import WidgetKit

final class NoRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum LoginStartup {
    static var file: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/com.joviliu.ottai.mirror.plist") }
    static var enabled: Bool { FileManager.default.fileExists(atPath: file.path) }
    static func setEnabled(_ value: Bool) throws {
        let manager = FileManager.default
        if value {
            let executable = Bundle.main.executableURL!.path
            let plist: [String: Any] = ["Label": "com.joviliu.ottai.mirror", "ProgramArguments": [executable],
                                      "RunAtLoad": true, "ProcessType": "Background"]
            try manager.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0).write(to: file, options: .atomic)
            // Registration is for the next login. The current menu app is already running.
        } else if enabled {
            try manager.removeItem(at: file)
        }
    }
}

@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    @Published var snapshot: CachedDashboard? = SnapshotStore.load()
    @Published var message = ""
    @Published var fetching = false
    @Published var now = Date()
    @Published var baseURL = ""
    @Published var launchAtLogin = LoginStartup.enabled
    private var loop: Task<Void, Never>?
    private var clock: Timer?
    private let connectionStore = ConnectionStore()
    private let session = URLSession(configuration: .ephemeral, delegate: NoRedirects(), delegateQueue: nil)

    var latest: Reading? { snapshot?.dashboard.latest }
    var stale: Bool { latest?.isStale(at: now) ?? true }
    var statusText: String { latest.map { "\($0.display) \($0.displayTrend)" } ?? "— →" }

    init() {
        baseURL = connectionStore.current?.baseURL ?? ""
        clock = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.now = Date() }
        }
        loop = Task { [weak self] in
            if let index = CommandLine.arguments.firstIndex(of: "--import-config"), CommandLine.arguments.count > index + 1 {
                await self?.importFile(URL(fileURLWithPath: CommandLine.arguments[index + 1]))
            }
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(300))
            }
        }
    }

    func configure(url: String, token: String?) async {
        do {
            let configuration = ConnectionConfiguration(baseURL: url, readToken: token?.trimmingCharacters(in: .whitespacesAndNewlines) ?? connectionStore.current?.readToken ?? "")
            try connectionStore.save(configuration)
            baseURL = connectionStore.current!.baseURL
            await refresh()
        } catch { message = "配置未保存：\(error.localizedDescription)" }
    }

    func refresh() async {
        guard !fetching else { return }
        guard let configuration = connectionStore.current, let root = URL(string: configuration.baseURL) else {
            message = "请先在设置中连接血糖服务。"; return
        }
        fetching = true
        defer { fetching = false; now = Date() }
        do {
            var request = URLRequest(url: root.appendingPathComponent("api/v1/dashboard"))
            request.setValue("Bearer \(configuration.readToken)", forHTTPHeaderField: "Authorization")
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 20
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else { throw MirrorError.invalidResponse }
            if response.statusCode == 401 || response.statusCode == 403 { throw MirrorError.authentication }
            guard response.statusCode == 200, data.count <= 2_000_000 else { throw MirrorError.unavailable }
            let dashboard = try Dashboard.decode(data)
            let result = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
            try SnapshotStore.save(result)
            snapshot = result
            message = ""
            WidgetCenter.shared.reloadTimelines(ofKind: SnapshotStore.kind)
        } catch let error as MirrorError { message = error.localizedDescription }
        catch { message = MirrorError.unavailable.localizedDescription }
    }

    func setStartup(_ enabled: Bool) {
        do { try LoginStartup.setEnabled(enabled); launchAtLogin = enabled }
        catch { message = "开机启动设置失败，请检查安装位置。" }
    }

    func importConfiguration() async {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        panel.message = "选择权限为 600 的私密配置 JSON。"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        await importFile(url)
    }

    func importFile(_ url: URL) async {
        do {
            let configuration = try ConnectionStore.readConfiguration(from: url)
            await configure(url: configuration.baseURL, token: configuration.readToken)
        } catch { message = "无法读取配置，请检查 JSON 文件。" }
    }
}

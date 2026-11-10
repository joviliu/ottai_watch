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
    @Published var snapshot: CachedDashboard?
    @Published var message = ""
    @Published var fetching = false
    @Published var analyzing = false
    @Published var analysisMessage = ""
    @Published var eventSaving = false
    @Published var now = Date()
    @Published var baseURL = ""
    @Published var launchAtLogin = LoginStartup.enabled
    private var loop: Task<Void, Never>?
    private var clock: Timer?
    private let connectionStore: ConnectionStore
    private let session: URLSession
    private let snapshotURL: URL
    private let reloadWidgets: () -> Void

    var canAnalyze: Bool { connectionStore.current?.analysisToken != nil && snapshot?.dashboard.manualAnalysis?.eligible == true && !analyzing }
    var canEditEvents: Bool { connectionStore.current?.analysisToken != nil }
    var analysisReason: String {
        if connectionStore.current?.analysisToken == nil { return "请在设置中导入手动分析权限。" }
        return snapshot?.dashboard.manualAnalysis?.reason ?? "请先刷新数据。"
    }
    var latest: Reading? { snapshot?.dashboard.latest }
    var stale: Bool { latest?.isStale(at: now) ?? true }
    var statusText: String { latest.map { "\($0.display) \($0.displayTrend)" } ?? "— →" }

    init(connectionStore: ConnectionStore = ConnectionStore(), snapshotURL: URL = SnapshotStore.localURL,
         session: URLSession? = nil, automaticallyRefresh: Bool = true,
         reloadWidgets: @escaping () -> Void = { WidgetCenter.shared.reloadTimelines(ofKind: SnapshotStore.kind) }) {
        self.connectionStore = connectionStore
        self.snapshotURL = snapshotURL
        self.session = session ?? URLSession(configuration: .ephemeral, delegate: NoRedirects(), delegateQueue: nil)
        self.reloadWidgets = reloadWidgets
        snapshot = SnapshotStore.load(at: snapshotURL)
        baseURL = connectionStore.current?.baseURL ?? ""
        guard automaticallyRefresh else { return }
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

    func configure(url: String, token: String?, analysisToken: String? = nil) async {
        do {
            let configuration = ConnectionConfiguration(baseURL: url, readToken: token?.trimmingCharacters(in: .whitespacesAndNewlines) ?? connectionStore.current?.readToken ?? "", analysisToken: analysisToken ?? (url.trimmingCharacters(in: CharacterSet(charactersIn: "/")) == connectionStore.current?.baseURL ? connectionStore.current?.analysisToken : nil))
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
            guard configuration == connectionStore.current else { message = "连接已更改，请刷新新连接。"; return }
            guard let response = response as? HTTPURLResponse else { throw MirrorError.invalidResponse }
            if response.statusCode == 401 || response.statusCode == 403 { throw MirrorError.authentication }
            guard response.statusCode == 200, data.count <= 2_000_000 else { throw MirrorError.unavailable }
            let dashboard = try Dashboard.decode(data)
            let result = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
            try SnapshotStore.save(result, at: snapshotURL)
            snapshot = result
            message = ""
            if !analyzing { analysisMessage = "" }
            reloadWidgets()
        } catch let error as MirrorError { message = error.localizedDescription }
        catch { message = MirrorError.unavailable.localizedDescription }
    }

    func analyzeRecent() async {
        guard canAnalyze, let configuration = connectionStore.current,
              let token = configuration.analysisToken, let root = URL(string: configuration.baseURL) else { return }
        analyzing = true
        analysisMessage = "正在分析最近24小时…"
        defer { analyzing = false }
        do {
            var request = URLRequest(url: root.appendingPathComponent("api/v1/analysis"))
            request.httpMethod = "POST"
            request.httpBody = Data()
            request.timeoutInterval = 20
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse, data.count < 65536 else { throw MirrorError.invalidResponse }
            if response.statusCode == 401 || response.statusCode == 403 { throw MirrorError.authentication }
            guard [200,202,409].contains(response.statusCode) else { throw MirrorError.unavailable }
            let result = try JSONSerialization.jsonObject(with: data) as? [String:Any]
            analysisMessage = result?["reason"] as? String ?? "已提交分析。"
            for _ in 0..<13 {
                await refresh()
                if snapshot?.dashboard.manualAnalysis?.status != "running" {
                    analysisMessage = snapshot?.dashboard.manualAnalysis?.reason ?? "分析状态已更新。"
                    return
                }
                try await Task.sleep(for: .seconds(10))
            }
            analysisMessage = "分析仍在生成，完成后会自动更新。"
        } catch {
            analysisMessage = "分析请求暂未确认，已保留原结果；请刷新状态，避免重复提交。"
            await refresh()
        }
    }

    func saveEvent(_ event: LifestyleEvent) async throws {
        guard event.valid else { throw EventWriteError.invalid }
        guard var body = try JSONSerialization.jsonObject(with: JSONEncoder().encode(event)) as? [String: Any] else { throw EventWriteError.invalid }
        body.removeValue(forKey: "updatedAt")
        if let revision = event.updatedAt { body["expectedUpdatedAt"] = revision }
        let response = try await writeEvent(path: "api/v1/events", body: body)
        guard let object = response["event"], JSONSerialization.isValidJSONObject(object),
              let saved = try? JSONDecoder().decode(LifestyleEvent.self, from: JSONSerialization.data(withJSONObject: object)), saved.valid
        else { throw EventWriteError.invalid }
        applyEvent(saved, deleting: nil)
        await refresh()
    }

    func deleteEvent(_ event: LifestyleEvent) async throws {
        var body: [String: Any] = ["id": event.id]
        if let revision = event.updatedAt { body["expectedUpdatedAt"] = revision }
        _ = try await writeEvent(path: "api/v1/events/delete", body: body)
        applyEvent(nil, deleting: event.id)
        await refresh()
    }

    private func writeEvent(path: String, body: [String: Any]) async throws -> [String: Any] {
        guard !eventSaving else { throw EventWriteError.busy }
        guard let configuration = connectionStore.current, let token = configuration.analysisToken,
              let root = URL(string: configuration.baseURL) else { throw EventWriteError.permission }
        let encoded = try JSONSerialization.data(withJSONObject: body)
        guard encoded.count <= 16384 else { throw EventWriteError.invalid }
        eventSaving = true
        defer { eventSaving = false }
        var request = URLRequest(url: root.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.httpBody = encoded
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        do {
            let (data, response) = try await session.data(for: request)
            guard configuration == connectionStore.current else { throw EventWriteError.connectionChanged }
            guard let http = response as? HTTPURLResponse, data.count <= 65536 else { throw EventWriteError.invalid }
            if http.statusCode == 401 || http.statusCode == 403 { throw EventWriteError.permission }
            if http.statusCode == 409 { throw EventWriteError.conflict }
            if http.statusCode == 400 || http.statusCode == 422 { throw EventWriteError.invalid }
            guard http.statusCode == 200, let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  result["ok"] as? Bool == true else { throw EventWriteError.unavailable }
            return result
        } catch let error as EventWriteError { throw error }
        catch { throw EventWriteError.unavailable }
    }

    private func applyEvent(_ event: LifestyleEvent?, deleting id: String?) {
        guard let previous = snapshot else { return }
        var dashboard = previous.dashboard
        let replaced = id ?? event?.id
        let changedDates = (dashboard.events ?? []).filter { $0.id == replaced }.map(\.at) + (event.map { [$0.at] } ?? [])
        var events = (dashboard.events ?? []).filter { $0.id != replaced }
        if let event { events.append(event) }
        dashboard.events = Array(events.sorted { $0.at < $1.at }.suffix(500))
        dashboard.rollingAnalysis = markingChanged(dashboard.rollingAnalysis, at: changedDates)
        dashboard.dailyAnalysis = markingChanged(dashboard.dailyAnalysis, at: changedDates)
        dashboard.analysis = markingChanged(dashboard.analysis, at: changedDates)
        let updated = CachedDashboard(fetchedAt: previous.fetchedAt, dashboard: dashboard)
        snapshot = updated
        try? SnapshotStore.save(updated, at: snapshotURL)
    }

    private func markingChanged(_ analysis: Analysis?, at dates: [Double]) -> Analysis? {
        guard var analysis, let start = analysis.periodStart, let end = analysis.periodEnd else { return analysis }
        if dates.contains(where: { $0 >= start && $0 < end }) { analysis.dataStale = true }
        return analysis
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
            await configure(url: configuration.baseURL, token: configuration.readToken, analysisToken: configuration.analysisToken)
        } catch { message = "无法读取配置，请检查 JSON 文件。" }
    }
}

enum EventWriteError: LocalizedError {
    case permission, conflict, invalid, unavailable, busy, connectionChanged
    var errorDescription: String? {
        switch self {
        case .permission: return "当前连接没有记录权限，请在设置中导入分析权限。"
        case .conflict: return "这条记录已在其他设备更新。请刷新后重新打开，当前填写内容已保留。"
        case .invalid: return "记录格式有误，请检查时间和文字。"
        case .unavailable: return "暂未确认保存结果，填写内容已保留；重试会使用同一条记录。"
        case .busy: return "上一条记录仍在保存，请稍候。"
        case .connectionChanged: return "连接已更改，请到原连接核对记录。"
        }
    }
}

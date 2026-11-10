import Foundation
import SwiftUI

@MainActor
final class DetailAnalysisModel: ObservableObject {
    let selection: DetailReportSelection
    @Published private(set) var state: DetailAnalysisState?
    @Published private(set) var message = ""
    @Published private(set) var loading = false
    @Published private(set) var submitting = false
    @Published private(set) var unconfirmed = false
    private let connectionStore: ConnectionStore
    private let configuration: ConnectionConfiguration?
    private let session: URLSession
    private let pollInterval: Duration
    private let pollCount: Int
    private var polling: Task<Void, Never>?
    private var active = false

    init(selection: DetailReportSelection, connectionStore: ConnectionStore, session: URLSession,
         pollInterval: Duration = .seconds(5), pollCount: Int = 36) {
        self.selection = selection
        self.connectionStore = connectionStore
        configuration = connectionStore.current
        self.session = session
        self.pollInterval = pollInterval
        self.pollCount = pollCount
    }

    var canGenerate: Bool {
        active && configuration == connectionStore.current && configuration?.analysisToken != nil
            && state?.eligible == true && state?.status != "running" && !submitting && !loading && !unconfirmed
    }
    var generationTitle: String { state?.report == nil ? "生成详细解读" : "生成新版解读" }
    var generationReason: String {
        if configuration?.analysisToken == nil { return "当前连接只有查看权限；请在设置中导入分析权限。" }
        return state?.reason ?? "正在核对所选报告。"
    }

    func open() async {
        active = true
        await query()
        resumePollingIfNeeded()
    }

    func query() async {
        guard active, !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let result = try await request(generate: false)
            guard active else { return }
            state = result
            if result.status != "available" { unconfirmed = false }
            message = ""
        } catch {
            guard active else { return }
            if configuration != connectionStore.current { invalidateConnection() }
            else { message = error.localizedDescription }
        }
    }

    func generate() async {
        guard canGenerate else { return }
        submitting = true
        defer { submitting = false }
        do {
            let result = try await request(generate: true)
            guard active else { return }
            state = result
            message = ""
            unconfirmed = false
        } catch {
            guard active else { return }
            if configuration != connectionStore.current { invalidateConnection(); return }
            if let known = error as? DetailClientError {
                switch known {
                case .permission, .rejected:
                    message = known.localizedDescription
                    return
                default: break
                }
            }
            unconfirmed = true
            message = "请求暂未确认，请查询状态；不会自动重复生成。"
            await query()
        }
        resumePollingIfNeeded()
    }

    func refreshStatus() async {
        await query()
        resumePollingIfNeeded()
    }

    func stop() {
        active = false
        polling?.cancel()
        polling = nil
    }

    func invalidateConnection() {
        stop()
        state = nil
        message = "连接已更改，请重新打开详细解读。"
    }

    private func resumePollingIfNeeded() {
        guard active, state?.status == "running", polling == nil else { return }
        polling = Task { [weak self] in
            guard let self else { return }
            defer { polling = nil }
            let clock = ContinuousClock()
            let deadline = clock.now.advanced(by: .seconds(180))
            for _ in 0..<pollCount {
                if clock.now >= deadline { break }
                do { try await Task.sleep(for: pollInterval) } catch { return }
                guard active, !Task.isCancelled else { return }
                await query()
                if state?.status != "running" { return }
            }
            if active && state?.status == "running" { message = "解读仍在生成，可稍后查询；不会重复提交。" }
        }
    }

    private func request(generate: Bool) async throws -> DetailAnalysisState {
        guard selection.valid, let configuration, configuration == connectionStore.current,
              let root = URL(string: configuration.baseURL) else { throw DetailClientError.connectionChanged }
        let endpoint = root.appendingPathComponent("api/v1/analysis/detail")
        var request: URLRequest
        if generate {
            guard let token = configuration.analysisToken else { throw DetailClientError.permission }
            request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.httpBody = try JSONSerialization.data(withJSONObject: ["kind": selection.kind, "reportId": selection.reportId])
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        } else {
            var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false)!
            components.queryItems = [URLQueryItem(name: "kind", value: selection.kind), URLQueryItem(name: "reportId", value: selection.reportId)]
            request = URLRequest(url: components.url!)
            request.setValue("Bearer \(configuration.readToken)", forHTTPHeaderField: "Authorization")
        }
        request.timeoutInterval = 45
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard configuration == connectionStore.current else { throw DetailClientError.connectionChanged }
        guard let http = response as? HTTPURLResponse, data.count <= 262144 else { throw MirrorError.invalidResponse }
        if http.statusCode == 401 || http.statusCode == 403 { throw DetailClientError.permission }
        guard [200, 202, 409].contains(http.statusCode) else { throw DetailClientError.unavailable }
        if let state = try? DetailAnalysisState.decode(data, for: selection) { return state }
        if http.statusCode == 409,
           let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let reason = value["reason"] as? String {
            throw DetailClientError.rejected(String(reason.prefix(1000)))
        }
        throw MirrorError.invalidResponse
    }
}

enum DetailClientError: LocalizedError {
    case permission, connectionChanged, unavailable, rejected(String)
    var errorDescription: String? {
        switch self {
        case .permission: return "当前连接没有详细分析权限，请检查设置。"
        case .connectionChanged: return "连接已更改，请重新打开详细解读。"
        case .unavailable: return "暂时未能取得解读状态，已保留当前报告。"
        case .rejected(let reason): return reason
        }
    }
}

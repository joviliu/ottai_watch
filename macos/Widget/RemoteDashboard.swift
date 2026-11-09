import Foundation

enum WidgetRemoteCategory: String, Error {
    case ok, authentication, unavailable
    case notConfigured = "not_configured"
    case invalidConfiguration = "invalid_configuration"
    case redirectRejected = "redirect_rejected"
    case timedOut = "timed_out"
    case invalidResponse = "invalid_response"
    case responseTooLarge = "response_too_large"
    case cacheUnavailable = "cache_unavailable"
}

struct WidgetRemoteResult {
    let snapshot: CachedDashboard?
    let category: WidgetRemoteCategory
}

/// Uses only the current process's sandbox. Completion runs off the main thread.
final class RemoteDashboard {
    private let directory: URL
    private var protocolClasses: [AnyClass]?
    private static let responseLimit = 2_000_000
    // JSONEncoder can escape strings that were unescaped in the response.
    private static let cacheLimit = 4_100_000

    init() {
        directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("OttaiMirror", isDirectory: true)
    }

    #if REMOTE_DASHBOARD_TESTS
    init(testDirectory: URL, protocolClasses: [AnyClass]) {
        directory = testDirectory
        self.protocolClasses = protocolClasses
    }
    #endif

    func load(completion: @escaping (WidgetRemoteResult) -> Void) {
        DispatchQueue.global(qos: .utility).async { [self] in
            var cached: CachedDashboard?
            let request: URLRequest
            do {
                let parent = try openDirectory()
                defer { close(parent) }
                cached = try? readCache(in: parent)
                request = try readRequest(in: parent)
            } catch {
                completion(WidgetRemoteResult(snapshot: cached, category: error as? WidgetRemoteCategory ?? .invalidConfiguration))
                return
            }
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 15
            configuration.timeoutIntervalForResource = 15
            configuration.waitsForConnectivity = false
            configuration.urlCache = nil
            configuration.urlCredentialStorage = nil
            configuration.httpCookieStorage = nil
            configuration.httpShouldSetCookies = false
            configuration.protocolClasses = protocolClasses
            let fallback = cached
            BoundedDashboardRequest.start(request, configuration: configuration, limit: Self.responseLimit) { result in
                switch result {
                case .success(let dashboard):
                    let snapshot = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
                    do {
                        try self.writeCache(snapshot)
                        completion(WidgetRemoteResult(snapshot: snapshot, category: .ok))
                    } catch {
                        completion(WidgetRemoteResult(snapshot: snapshot, category: .cacheUnavailable))
                    }
                case .failure(let category):
                    completion(WidgetRemoteResult(snapshot: fallback, category: category))
                }
            }
        }
    }

    private func openDirectory() throws -> Int32 {
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                    attributes: [.posixPermissions: 0o700])
        } catch { throw WidgetRemoteCategory.invalidConfiguration }
        let parent = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard parent >= 0 else { throw WidgetRemoteCategory.invalidConfiguration }
        var info = stat()
        guard fstat(parent, &info) == 0, info.st_uid == geteuid(), info.st_mode & 0o777 == 0o700 else {
            close(parent)
            throw WidgetRemoteCategory.invalidConfiguration
        }
        return parent
    }

    private func readFile(in parent: Int32, name: String, limit: Int, missing: WidgetRemoteCategory) throws -> Data {
        let descriptor = openat(parent, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard descriptor >= 0 else { throw errno == ENOENT ? missing : .invalidConfiguration }
        defer { close(descriptor) }
        var info = stat()
        guard fstat(descriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_uid == geteuid(), info.st_mode & 0o777 == 0o600,
              info.st_size > 0, info.st_size <= limit else { throw WidgetRemoteCategory.invalidConfiguration }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
        guard let data = try handle.read(upToCount: limit + 1), data.count <= limit else {
            throw WidgetRemoteCategory.invalidConfiguration
        }
        return data
    }

    private func readRequest(in parent: Int32) throws -> URLRequest {
        struct Configuration: Decodable { let baseURL: String; let readToken: String }
        let data = try readFile(in: parent, name: "connection.json", limit: 16_384, missing: .notConfigured)
        let config = try JSONDecoder().decode(Configuration.self, from: data)
        guard let base = URL(string: config.baseURL), base.scheme == "https", base.host?.isEmpty == false,
              base.user == nil, base.password == nil, base.query == nil, base.fragment == nil,
              !config.readToken.isEmpty, config.readToken.utf8.count <= 8192,
              config.readToken.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else {
            throw WidgetRemoteCategory.invalidConfiguration
        }
        var request = URLRequest(url: base.appendingPathComponent("api/v1/dashboard"),
                                 cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(config.readToken)", forHTTPHeaderField: "Authorization")
        return request
    }

    private func readCache(in parent: Int32) throws -> CachedDashboard {
        let data = try readFile(in: parent, name: "widget-dashboard.json", limit: Self.cacheLimit, missing: .cacheUnavailable)
        let snapshot = try JSONDecoder().decode(CachedDashboard.self, from: data)
        _ = try Dashboard.decode(JSONEncoder().encode(snapshot.dashboard))
        guard snapshot.fetchedAt.timeIntervalSince1970.isFinite else { throw WidgetRemoteCategory.invalidResponse }
        return snapshot
    }

    private func writeCache(_ snapshot: CachedDashboard) throws {
        let data = try JSONEncoder().encode(snapshot)
        guard data.count <= Self.cacheLimit else { throw WidgetRemoteCategory.cacheUnavailable }
        let parent = try openDirectory()
        defer { close(parent) }
        let name = "widget-dashboard.json"
        var existing = stat()
        if fstatat(parent, name, &existing, AT_SYMLINK_NOFOLLOW) == 0 {
            guard existing.st_mode & S_IFMT == S_IFREG, existing.st_uid == geteuid(),
                  existing.st_mode & 0o777 == 0o600 else { throw WidgetRemoteCategory.cacheUnavailable }
        } else if errno != ENOENT { throw WidgetRemoteCategory.cacheUnavailable }
        let temporary = ".widget-dashboard-\(UUID().uuidString).tmp"
        let descriptor = openat(parent, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard descriptor >= 0 else { throw WidgetRemoteCategory.cacheUnavailable }
        defer { close(descriptor); unlinkat(parent, temporary, 0) }
        guard fchmod(descriptor, 0o600) == 0 else { throw WidgetRemoteCategory.cacheUnavailable }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
        try handle.write(contentsOf: data)
        try handle.synchronize()
        guard renameat(parent, temporary, parent, name) == 0 else { throw WidgetRemoteCategory.cacheUnavailable }
    }
}

/// URLSession retains this delegate until invalidation; all state uses its serial delegate queue.
private final class BoundedDashboardRequest: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let limit: Int
    private let completion: (Result<Dashboard, WidgetRemoteCategory>) -> Void
    private var session: URLSession?
    private var data = Data()
    private var failure: WidgetRemoteCategory?

    private init(limit: Int, completion: @escaping (Result<Dashboard, WidgetRemoteCategory>) -> Void) {
        self.limit = limit
        self.completion = completion
    }

    static func start(_ request: URLRequest, configuration: URLSessionConfiguration, limit: Int,
                      completion: @escaping (Result<Dashboard, WidgetRemoteCategory>) -> Void) {
        let delegate = BoundedDashboardRequest(limit: limit, completion: completion)
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        delegate.session = session
        session.dataTask(with: request).resume()
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        failure = .redirectRejected
        completionHandler(nil)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        guard let http = response as? HTTPURLResponse, http.url?.scheme == "https" else {
            failure = .invalidResponse
            completionHandler(.cancel)
            return
        }
        if http.statusCode == 401 || http.statusCode == 403 { failure = .authentication }
        else if (300...399).contains(http.statusCode) { failure = .redirectRejected }
        else if !(200...299).contains(http.statusCode) { failure = .unavailable }
        else if response.expectedContentLength > Int64(limit) { failure = .responseTooLarge }
        completionHandler(failure == nil ? .allow : .cancel)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive chunk: Data) {
        guard failure == nil else { return }
        guard chunk.count <= limit - data.count else {
            failure = .responseTooLarge
            dataTask.cancel()
            return
        }
        data.append(chunk)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        defer { session.finishTasksAndInvalidate(); self.session = nil }
        if let failure { completion(.failure(failure)); return }
        if let error {
            let timeout = (error as NSError).domain == NSURLErrorDomain && (error as NSError).code == NSURLErrorTimedOut
            completion(.failure(timeout ? .timedOut : .unavailable))
            return
        }
        do { completion(.success(try Dashboard.decode(data))) }
        catch { completion(.failure(.invalidResponse)) }
    }
}

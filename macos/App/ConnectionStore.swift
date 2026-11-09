import Foundation
import Darwin

struct ConnectionConfiguration: Codable, Equatable {
    let baseURL: String
    let readToken: String

    func validated() throws -> ConnectionConfiguration {
        guard let url = URL(string: baseURL), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              !readToken.isEmpty, readToken.utf8.count <= 8192,
              readToken.utf8.allSatisfy({ $0 > 32 && $0 < 127 })
        else { throw MirrorError.invalidConfiguration }
        return ConnectionConfiguration(baseURL: baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")), readToken: readToken)
    }
}

final class ConnectionStore {
    static var location: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("OttaiMirror/connection.json")
    }
    let url: URL
    private(set) var current: ConnectionConfiguration?

    init(url: URL = ConnectionStore.location) {
        self.url = url
        current = try? Self.readConfiguration(from: url, requirePrivateDirectory: true)
    }

    static func readConfiguration(from url: URL, requirePrivateDirectory: Bool = false) throws -> ConnectionConfiguration {
        let parent = open(url.deletingLastPathComponent().path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard parent >= 0 else { throw MirrorError.invalidConfiguration }
        defer { close(parent) }
        if requirePrivateDirectory {
            var info = stat()
            guard fstat(parent, &info) == 0, info.st_uid == geteuid(), info.st_mode & 0o777 == 0o700 else { throw MirrorError.invalidConfiguration }
        }
        let descriptor = openat(parent, url.lastPathComponent, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard descriptor >= 0 else { throw MirrorError.invalidConfiguration }
        defer { close(descriptor) }
        var info = stat()
        guard fstat(descriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_uid == geteuid(), info.st_mode & 0o777 == 0o600,
              info.st_size > 0, info.st_size <= 16384 else { throw MirrorError.invalidConfiguration }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
        guard let data = try handle.read(upToCount: 16385), data.count <= 16384 else { throw MirrorError.invalidConfiguration }
        return try JSONDecoder().decode(ConnectionConfiguration.self, from: data).validated()
    }

    func save(_ configuration: ConnectionConfiguration) throws {
        let validated = try configuration.validated()
        let directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let parent = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard parent >= 0 else { throw MirrorError.invalidConfiguration }
        defer { close(parent) }
        var parentInfo = stat()
        guard fstat(parent, &parentInfo) == 0, parentInfo.st_uid == geteuid(), fchmod(parent, 0o700) == 0 else { throw MirrorError.invalidConfiguration }
        var existing = stat()
        if fstatat(parent, url.lastPathComponent, &existing, AT_SYMLINK_NOFOLLOW) == 0 {
            guard existing.st_mode & S_IFMT == S_IFREG, existing.st_uid == geteuid() else { throw MirrorError.invalidConfiguration }
        } else if errno != ENOENT { throw MirrorError.invalidConfiguration }
        let temporary = ".connection-\(UUID().uuidString).tmp"
        let output = openat(parent, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard output >= 0 else { throw MirrorError.unavailable }
        defer { close(output); unlinkat(parent, temporary, 0) }
        guard fchmod(output, 0o600) == 0 else { throw MirrorError.unavailable }
        let handle = FileHandle(fileDescriptor: output, closeOnDealloc: false)
        try handle.write(contentsOf: JSONEncoder().encode(validated))
        try handle.synchronize()
        guard renameat(parent, temporary, parent, url.lastPathComponent) == 0 else { throw MirrorError.unavailable }
        current = validated
    }
}

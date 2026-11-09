import Foundation
import Darwin

final class ProcessLock {
    enum Failure: Error { case busy, unsafePath }
    private let descriptor: Int32

    init(at url: URL) throws {
        let folder = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let directory = open(folder.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard directory >= 0 else { throw Failure.unsafePath }
        defer { close(directory) }
        var directoryInfo = stat()
        guard fstat(directory, &directoryInfo) == 0, directoryInfo.st_uid == geteuid(), fchmod(directory, 0o700) == 0 else { throw Failure.unsafePath }
        let file = openat(directory, url.lastPathComponent, O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard file >= 0 else { throw Failure.unsafePath }
        var info = stat()
        guard fstat(file, &info) == 0, info.st_uid == geteuid(), info.st_mode & S_IFMT == S_IFREG,
              info.st_mode & 0o777 == 0o600 else { close(file); throw Failure.unsafePath }
        guard flock(file, LOCK_EX | LOCK_NB) == 0 else { close(file); throw Failure.busy }
        descriptor = file
    }

    deinit { close(descriptor) }
}

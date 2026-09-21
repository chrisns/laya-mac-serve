import Foundation
import LayaServeCore

/// Start, watch and stop the bundled Python server.
///
/// The application bundles its own CPython, so it never uses the Python of the user.
final class ServerProcess {
    private var process: Process?
    private var stopping = false
    private var restartCount = 0
    private let queue = DispatchQueue(label: "me.cns.laya-serve.process")

    var onStateChange: ((String) -> Void)?

    /// The bundled interpreter. Fall back to a development checkout when it is missing.
    static func pythonURL() -> URL? {
        let bundled = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Resources/python/bin/python3")
        if FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        if let override = ProcessInfo.processInfo.environment["LAYA_SERVE_PYTHON"] {
            return URL(fileURLWithPath: override)
        }
        return nil
    }

    static func serverRootURL() -> URL {
        Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/server")
    }

    /// The weights that ship inside the application. The server then needs no network.
    static func modelRootURL() -> URL? {
        let bundled = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/model")
        var isDirectory: ObjCBool = false
        if FileManager.default.fileExists(atPath: bundled.path, isDirectory: &isDirectory),
            isDirectory.boolValue
        {
            return bundled
        }
        if let override = ProcessInfo.processInfo.environment["LAYA_SERVE_MODEL_DIR"] {
            return URL(fileURLWithPath: override)
        }
        return nil
    }

    static var logURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/LayaServe/server.log")
    }

    func start() {
        queue.async { [weak self] in self?.launch() }
    }

    private func launch() {
        guard process == nil, !stopping else { return }
        guard let python = Self.pythonURL() else {
            onStateChange?("The bundled Python runtime is missing from the application.")
            return
        }

        try? FileManager.default.createDirectory(
            at: Self.logURL.deletingLastPathComponent(), withIntermediateDirectories: true)

        let task = Process()
        task.executableURL = python
        // --watch-parent makes the server stop when this application dies. A SIGKILL
        // skips the shutdown handler, and the old server would then keep the port.
        task.arguments = ["-m", "laya_serve", "--log-file", "--watch-parent"]
        task.currentDirectoryURL = Self.serverRootURL()

        var environment = ProcessInfo.processInfo.environment
        let runtime = python.deletingLastPathComponent().deletingLastPathComponent()
        environment["PYTHONHOME"] = runtime.path
        environment["PYTHONPATH"] = Self.serverRootURL().path
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if let model = Self.modelRootURL() {
            environment["LAYA_SERVE_MODEL_DIR"] = model.path
        }
        task.environment = environment

        if !FileManager.default.fileExists(atPath: Self.logURL.path) {
            FileManager.default.createFile(atPath: Self.logURL.path, contents: nil)
        }
        if let handle = try? FileHandle(forWritingTo: Self.logURL) {
            handle.seekToEndOfFile()
            task.standardOutput = handle
            task.standardError = handle
        }

        task.terminationHandler = { [weak self] finished in
            guard let self else { return }
            self.queue.async {
                self.process = nil
                guard !self.stopping else { return }
                self.restartCount += 1
                let delay = min(30.0, pow(2.0, Double(min(self.restartCount, 5))))
                self.onStateChange?(
                    "The server stopped with code \(finished.terminationStatus). "
                        + "It restarts in \(Int(delay)) seconds.")
                self.queue.asyncAfter(deadline: .now() + delay) { self.launch() }
            }
        }

        do {
            try task.run()
            process = task
        } catch {
            onStateChange?("The server did not start: \(error.localizedDescription)")
        }
    }

    /// Stop the server. Send SIGTERM first, then SIGKILL after a grace period.
    func stop() {
        queue.sync {
            stopping = true
            guard let task = process, task.isRunning else { return }
            task.terminate()
            let deadline = Date().addingTimeInterval(5)
            while task.isRunning && Date() < deadline {
                usleep(50_000)
            }
            if task.isRunning {
                kill(task.processIdentifier, SIGKILL)
            }
            process = nil
        }
    }

    /// Stop and start again. A change of host, port or key needs this.
    func restart() {
        queue.async { [weak self] in
            guard let self else { return }
            if let task = self.process, task.isRunning {
                self.stopping = true
                task.terminate()
                let deadline = Date().addingTimeInterval(5)
                while task.isRunning && Date() < deadline { usleep(50_000) }
                self.process = nil
            }
            self.stopping = false
            self.restartCount = 0
            self.launch()
        }
    }
}

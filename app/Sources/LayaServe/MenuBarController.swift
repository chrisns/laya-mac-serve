import AppKit
import LayaServeCore

/// The menu bar item. The application has no window and no Dock icon.
@MainActor
final class MenuBarController {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let store = SettingsStore()
    private let server = ServerProcess()
    private var client: StatusClient
    private var settings: Settings
    private var state: MenuState = .starting
    private var bundledModels: [String] = []
    private var pollTask: Task<Void, Never>?

    private let statusMenuItem = NSMenuItem(title: "Starting...", action: nil, keyEquivalent: "")
    private let urlMenuItem = NSMenuItem(
        title: "Copy base URL", action: #selector(copyBaseURL), keyEquivalent: "c")
    private let idleMenu = NSMenu()
    private let modelMenu = NSMenu()
    private let networkItem = NSMenuItem(
        title: "Allow connections from the network", action: #selector(toggleNetwork),
        keyEquivalent: "")

    init() {
        settings = store.load()
        client = StatusClient(baseURL: settings.localBaseURL)
        buildMenu()
        server.onStateChange = { [weak self] message in
            Task { @MainActor in self?.state = .failed(message); self?.refreshMenu() }
        }
        server.start()
        startPolling()
    }

    // MARK: - Menu

    private func buildMenu() {
        let menu = NSMenu()
        menu.autoenablesItems = false

        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)
        menu.addItem(.separator())

        urlMenuItem.target = self
        menu.addItem(urlMenuItem)

        let loadItem = NSMenuItem(
            title: "Load model now", action: #selector(loadNow), keyEquivalent: "")
        loadItem.target = self
        menu.addItem(loadItem)

        let unloadItem = NSMenuItem(
            title: "Unload model now", action: #selector(unloadNow), keyEquivalent: "")
        unloadItem.target = self
        menu.addItem(unloadItem)
        menu.addItem(.separator())

        for interval in IdleInterval.allCases {
            let item = NSMenuItem(
                title: interval.title, action: #selector(selectIdleInterval(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = interval.seconds
            idleMenu.addItem(item)
        }
        let idleParent = NSMenuItem(title: "Unload when idle for", action: nil, keyEquivalent: "")
        idleParent.submenu = idleMenu
        menu.addItem(idleParent)

        for model in Models.all {
            let item = NSMenuItem(
                title: Models.title(for: model), action: #selector(selectModel(_:)),
                keyEquivalent: "")
            item.target = self
            item.representedObject = model
            modelMenu.addItem(item)
        }
        let modelParent = NSMenuItem(title: "Default model", action: nil, keyEquivalent: "")
        modelParent.submenu = modelMenu
        menu.addItem(modelParent)

        networkItem.target = self
        menu.addItem(networkItem)
        menu.addItem(.separator())

        let logItem = NSMenuItem(
            title: "Open log file", action: #selector(openLog), keyEquivalent: "")
        logItem.target = self
        menu.addItem(logItem)

        let folderItem = NSMenuItem(
            title: "Open settings folder", action: #selector(openSettingsFolder), keyEquivalent: "")
        folderItem.target = self
        menu.addItem(folderItem)
        menu.addItem(.separator())

        let quitItem = NSMenuItem(title: "Quit Laya Serve", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
        refreshMenu()
    }

    private func refreshMenu() {
        statusMenuItem.title = state.title
        urlMenuItem.title = "Copy base URL  (\(settings.baseURL))"

        let symbol = settings.listensOnNetwork && (settings.apiKey ?? "").isEmpty
            ? "exclamationmark.triangle" : state.symbolName
        if let button = statusItem.button {
            button.image = NSImage(
                systemSymbolName: symbol, accessibilityDescription: "Laya Serve")
            button.image?.isTemplate = true
            button.toolTip = state.title
        }

        let currentInterval = IdleInterval.closest(to: settings.idleUnloadSeconds)
        for item in idleMenu.items {
            let seconds = item.representedObject as? Int ?? -1
            item.state = seconds == currentInterval.seconds ? .on : .off
        }
        for item in modelMenu.items {
            guard let model = item.representedObject as? String else { continue }
            item.state = model == settings.defaultModel ? .on : .off
            // Say which checkpoints ship inside the application. Any other one downloads.
            let bundled = bundledModels.isEmpty || bundledModels.contains(model)
            item.title = bundled ? Models.title(for: model) : Models.title(for: model) + "  (downloads)"
        }
        networkItem.state = settings.listensOnNetwork ? .on : .off
    }

    // MARK: - Polling

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                let status = await self.client.status()
                await MainActor.run {
                    self.state = MenuState.from(status)
                    self.bundledModels = status?.bundledModels ?? []
                    self.refreshMenu()
                }
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    // MARK: - Actions

    @objc private func copyBaseURL() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(settings.baseURL, forType: .string)
    }

    @objc private func loadNow() {
        Task { await client.loadNow() }
    }

    @objc private func unloadNow() {
        Task { await client.unloadNow() }
    }

    @objc private func selectIdleInterval(_ sender: NSMenuItem) {
        guard let seconds = sender.representedObject as? Int else { return }
        settings.idleUnloadSeconds = seconds
        persist(restart: false)
    }

    @objc private func selectModel(_ sender: NSMenuItem) {
        guard let model = sender.representedObject as? String else { return }
        settings.defaultModel = model
        persist(restart: false)
    }

    @objc private func toggleNetwork() {
        if settings.listensOnNetwork {
            settings.host = "127.0.0.1"
            settings.apiKey = nil
            persist(restart: true)
            return
        }
        let key = generateAPIKey()
        settings.host = "0.0.0.0"
        settings.apiKey = key
        persist(restart: true)
        showAPIKeyAlert(key)
    }

    private func showAPIKeyAlert(_ key: String) {
        let alert = NSAlert()
        alert.messageText = "Laya Serve now listens on the network"
        alert.informativeText = """
            Use this API key in the n8n credential. Anyone who has the key can use the server.

            \(key)
            """
        alert.addButton(withTitle: "Copy key")
        alert.addButton(withTitle: "Close")
        if alert.runModal() == .alertFirstButtonReturn {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(key, forType: .string)
        }
    }

    @objc private func openLog() {
        NSWorkspace.shared.open(ServerProcess.logURL)
    }

    @objc private func openSettingsFolder() {
        NSWorkspace.shared.open(store.directory)
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    // MARK: - Settings

    private func persist(restart: Bool) {
        try? store.save(settings)
        let current = settings
        Task { [client] in await client.pushSettings(current) }
        if restart {
            client = StatusClient(baseURL: settings.localBaseURL)
            state = .starting
            server.restart()
        }
        refreshMenu()
    }

    func shutdown() {
        pollTask?.cancel()
        server.stop()
    }
}

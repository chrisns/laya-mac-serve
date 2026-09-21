import AppKit

// The application lives in the menu bar only. It has no Dock icon and no window.
let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let delegate = AppDelegate()
application.delegate = delegate
application.run()

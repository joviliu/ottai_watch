import AppKit
import SwiftUI

struct StatusStates: View {
    let scheme: ColorScheme
    let now: Date
    private let states: [(String, Double, String)] = [
        ("平稳", 6.2, "→"), ("斜升", 7.1, "↗"), ("上升", 8.0, "↑"), ("快升", 9.4, "↑↑"),
        ("斜降", 6.8, "↘"), ("下降", 4.5, "↓"), ("快降", 3.8, "↓↓")]
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(scheme == .dark ? "深色 · 18pt" : "浅色 · 18pt").font(.system(size: 12, weight: .semibold)).padding(.bottom, 5)
            ForEach(states, id: \.0) { state in
                row(state.0, Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: state.1, trend: state.2))
            }
            row("旧读数", Reading(sourceAt: now.addingTimeInterval(-1200).timeIntervalSince1970 * 1000, value: 6.2, trend: "→"))
            row("无数据", nil)
        }.padding(16).frame(width: 178)
            .foregroundStyle(.primary)
            .background(scheme == .dark ? Color(red: 0.07, green: 0.08, blue: 0.10) : Color(red: 0.96, green: 0.97, blue: 0.98))
            .environment(\.colorScheme, scheme)
    }
    private func row(_ title: String, _ reading: Reading?) -> some View {
        HStack {
            Text(title).font(.system(size: 11)).foregroundStyle(.secondary).frame(width: 42, alignment: .leading)
            Spacer(minLength: 6)
            Image(nsImage: StatusBadge.menuImage(reading: reading, now: now))
        }.frame(height: 22)
    }
}

@main
struct StatusPreview {
    @MainActor static func main() throws {
        let now = Date()
        assert(NSFont(name: "HelveticaNeue-Thin", size: 16) != nil)
        let badge = StatusBadge.menuImage(reading: Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: 6.2, trend: "→"), now: now)
        assert(badge.isTemplate && badge.size.height == 18 && badge.size.width < 30 && badge.tiffRepresentation != nil)
        let view = VStack(spacing: 10) {
            HStack(spacing: 12) { StatusStates(scheme: .light, now: now); StatusStates(scheme: .dark, now: now) }
            Text("合成状态预览 · 合成图像的内嵌细数字").font(.system(size: 11)).foregroundStyle(.secondary)
        }.padding(12).background(Color.white)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff), let data = bitmap.representation(using: .png, properties: [:]) else { throw MirrorError.unavailable }
        let output = CommandLine.arguments.dropFirst().first ?? "macos/build/menubar-states-synthetic.png"
        try data.write(to: URL(fileURLWithPath: output))
        print("Rendered native status badge states in light/dark appearance")
    }
}

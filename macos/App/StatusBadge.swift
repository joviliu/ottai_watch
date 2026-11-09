import AppKit
import SwiftUI

private struct BloodDrop: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addCurve(to: CGPoint(x: rect.minX, y: rect.height * 0.65),
                      control1: CGPoint(x: rect.width * 0.38, y: rect.height * 0.22),
                      control2: CGPoint(x: rect.minX, y: rect.height * 0.40))
        path.addCurve(to: CGPoint(x: rect.maxX, y: rect.height * 0.65),
                      control1: CGPoint(x: rect.minX, y: rect.height * 1.12),
                      control2: CGPoint(x: rect.maxX, y: rect.height * 1.12))
        path.addCurve(to: CGPoint(x: rect.midX, y: rect.minY),
                      control1: CGPoint(x: rect.maxX, y: rect.height * 0.40),
                      control2: CGPoint(x: rect.width * 0.62, y: rect.height * 0.22))
        path.closeSubpath()
        return path
    }
}

struct StatusBadge: View {
    let reading: Reading?
    let now: Date
    private var stale: Bool { reading?.isStale(at: now) ?? true }

    var body: some View {
        ZStack(alignment: .leading) {
            BloodDrop().fill(Color.primary.opacity(0.48))
                .overlay(BloodDrop().stroke(Color.primary.opacity(0.62), lineWidth: 0.6))
                .frame(width: 16, height: 22)
            Text(reading?.display ?? "—")
                .font(.custom("HelveticaNeue-Thin", size: 16)).monospacedDigit()
                .padding(.leading, 3).offset(y: 1)
        }
        .foregroundStyle(.primary)
        .padding(.horizontal, 2).frame(height: 22)
        .opacity(stale ? 0.48 : 1)
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("血糖 \(reading?.display ?? "暂无")，趋势 \(reading?.displayTrend ?? "未知")，\(stale ? "待更新" : "已更新")")
        .help(reading.map { "血糖 \($0.display) mmol/L · \($0.displayTrend) · \(DisplayTime.time($0.date))\(stale ? " · 旧读数" : "")" } ?? "血糖镜像 · 等待数据")
    }

    @MainActor static func menuImage(reading: Reading?, now: Date) -> NSImage {
        // MenuBarExtra separates Image/Text labels; render one template image to preserve overlap.
        let renderer = ImageRenderer(content: StatusBadge(reading: reading, now: now)
            .environment(\.colorScheme, .light))
        renderer.scale = 3
        let image = renderer.nsImage ?? NSImage(size: NSSize(width: 30, height: 22))
        image.size = NSSize(width: image.size.width * 18 / 22, height: 18)
        image.isTemplate = true
        return image
    }
}

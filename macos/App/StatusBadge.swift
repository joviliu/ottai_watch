import SwiftUI

struct StatusBadge: View {
    let reading: Reading?
    let now: Date
    private var stale: Bool { reading?.isStale(at: now) ?? true }

    var body: some View {
        HStack(spacing: -10) {
            Image(systemName: "drop.fill").resizable().scaledToFit()
                .frame(width: 20, height: 22).opacity(0.25)
            Text(reading?.display ?? "—")
                .font(.custom("AvenirNext-Medium", size: 15)).monospacedDigit()
        }
        .foregroundStyle(.primary)
        .padding(.horizontal, 2).frame(height: 22)
        .opacity(stale ? 0.48 : 1)
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("血糖 \(reading?.display ?? "暂无")，趋势 \(reading?.displayTrend ?? "未知")，\(stale ? "待更新" : "已更新")")
        .help(reading.map { "血糖 \($0.display) mmol/L · \($0.displayTrend) · \(DisplayTime.time($0.date))\(stale ? " · 旧读数" : "")" } ?? "血糖镜像 · 等待数据")
    }
}

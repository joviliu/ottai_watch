import AppKit
import SwiftUI

@MainActor
final class DetailedReportWindowController: NSWindowController, NSWindowDelegate {
    private let detailModel: DetailAnalysisModel
    init(model: AppModel, selection: DetailReportSelection) {
        detailModel = model.detailModel(for: selection)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 740, height: 840),
                              styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = selection.title
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 560, height: 480)
        super.init(window: window)
        window.contentView = NSHostingView(rootView: DetailedReportView(model: model, detail: detailModel))
        window.delegate = self
        window.center()
    }
    required init?(coder: NSCoder) { nil }
    func windowWillClose(_ notification: Notification) { detailModel.stop() }
}

struct DetailedReportView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var detail: DetailAnalysisModel
    private var parentChanged: Bool {
        let dashboard = model.snapshot?.dashboard
        let parent = detail.selection.kind == "rolling" ? dashboard?.rollingAnalysis : dashboard?.dailyAnalysis
        return parent?.reportId.map { $0 != detail.selection.reportId } ?? false
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                if let report = detail.state?.report { DetailedReportBody(report: report) }
                else if detail.state?.status == "available" {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("进一步理解这段血糖变化", systemImage: "text.magnifyingglass").font(.headline).foregroundStyle(MirrorPalette.violet)
                        Text("结合所选时段与个人历史中的血糖、活动、心率和饮食，展开原因分析、替代解释与可验证的调整。").font(.body)
                        Text("点击生成后开始，完成的解读会保留供再次查看。").font(.caption).foregroundStyle(MirrorPalette.muted)
                    }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 20)
                }
            }.padding(24)
        }.foregroundStyle(MirrorPalette.ink).background(MirrorPalette.background).preferredColorScheme(.light)
            .task { await detail.open() }
    }
    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Label(detail.selection.title, systemImage: "doc.text.magnifyingglass").font(.title2.weight(.semibold)).foregroundStyle(MirrorPalette.violet)
                Spacer()
                if detail.loading || detail.submitting { ProgressView().controlSize(.small) }
            }
            if let period = detail.selection.periodDescription {
                Text(period).font(.caption).monospacedDigit().foregroundStyle(MirrorPalette.muted)
            }
            if parentChanged { Label("简报已有更新，此处保留的是所选时段的解读。", systemImage: "clock.arrow.circlepath").font(.caption).foregroundStyle(MirrorPalette.muted) }
            if detail.state?.dataStale == true { Label("生成后有资料更新，原解读仍可查看。", systemImage: "arrow.triangle.2.circlepath").font(.caption).foregroundStyle(MirrorPalette.muted) }
            if detail.state?.status == "running" {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text(detail.state?.report == nil ? "正在生成详细解读…" : "新版解读生成中，原解读保留。").font(.callout) }
            }
            if let reason = detail.state?.reason, !reason.isEmpty { Text(reason).font(.caption).foregroundStyle(MirrorPalette.muted) }
            if !detail.message.isEmpty { Text(detail.message).font(.caption).foregroundStyle(MirrorPalette.muted) }
            if detail.unconfirmed { Text("请求暂未确认，请先查询状态；不会自动重复生成。").font(.caption).foregroundStyle(MirrorPalette.muted) }
            HStack(spacing: 12) {
                if detail.state?.eligible == true || detail.state?.status == "available" {
                    Button { Task { await detail.generate() } } label: { Label(detail.generationTitle, systemImage: "sparkles") }
                        .disabled(!detail.canGenerate).buttonStyle(.borderedProminent).tint(MirrorPalette.violet)
                }
                Button { Task { await detail.refreshStatus() } } label: { Label("查询状态", systemImage: "arrow.clockwise") }
                    .disabled(detail.loading || detail.submitting).buttonStyle(.borderless).foregroundStyle(MirrorPalette.blue)
                Spacer()
                if let at = detail.state?.generatedAt { Text("生成于 \(DisplayTime.dateTime(Date(timeIntervalSince1970: at/1000)))").font(.caption).foregroundStyle(MirrorPalette.muted) }
            }
            if detail.state?.eligible == true && !detail.canGenerate && !detail.loading && !detail.submitting && !detail.unconfirmed {
                Text(detail.generationReason).font(.caption).foregroundStyle(MirrorPalette.muted)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 20)
    }
}

struct DetailedReportBody: View {
    let report: DetailedReport
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 10) {
                Text(report.title).font(.title2.weight(.semibold))
                Text(reportInlineText(report.summary)).font(.body.weight(.medium)).lineSpacing(4).textSelection(.enabled)
            }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 22)
            ForEach(report.sections) { section in
                VStack(alignment: .leading, spacing: 10) {
                    Text(section.title).font(.headline).foregroundStyle(MirrorPalette.blue)
                    Text(reportInlineText(section.text)).font(.body).lineSpacing(5).textSelection(.enabled)
                    DetailReferences(ids: section.sourceIds, sources: report.sources)
                }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 22)
            }
            if !report.hypotheses.isEmpty {
                Label("原因假设与验证", systemImage: "point.3.connected.trianglepath.dotted").font(.title3.weight(.semibold)).foregroundStyle(MirrorPalette.violet).padding(.top, 4)
                ForEach(report.hypotheses) { hypothesis in
                    VStack(alignment: .leading, spacing: 13) {
                        HStack(alignment: .top) {
                            Text(hypothesis.title).font(.headline)
                            Spacer()
                            Text(hypothesis.confidenceTitle).font(.caption.weight(.medium)).foregroundStyle(MirrorPalette.violet)
                                .padding(.horizontal, 9).padding(.vertical, 4).background(MirrorPalette.violet.opacity(0.09), in: Capsule())
                        }
                        hypothesisText("支持线索", hypothesis.support, symbol: "plus.circle")
                        hypothesisText("其他解释与反证", hypothesis.against, symbol: "arrow.triangle.branch")
                        hypothesisText("如何验证", hypothesis.verification, symbol: "checklist")
                        DetailReferences(ids: hypothesis.sourceIds, sources: report.sources)
                    }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 22)
                }
            }
            VStack(alignment: .leading, spacing: 16) {
                Label("可以验证的调整", systemImage: "list.bullet.clipboard").font(.headline).foregroundStyle(MirrorPalette.violet)
                ForEach(Array(report.actions.enumerated()), id: \.offset) { index, action in
                    HStack(alignment: .top, spacing: 10) {
                        Text("\(index+1)").font(.caption.weight(.semibold)).frame(width: 24, height: 24)
                            .foregroundStyle(MirrorPalette.violet).background(MirrorPalette.violet.opacity(0.09), in: Circle())
                        VStack(alignment: .leading, spacing: 7) {
                            Text(action.title).font(.subheadline.weight(.semibold))
                            Text(reportInlineText(action.text)).font(.body).lineSpacing(4).textSelection(.enabled)
                        }
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 22)
            if !report.limitations.isEmpty {
                DisclosureGroup("影响本次判断的资料") {
                    VStack(alignment: .leading, spacing: 8) { ForEach(report.limitations, id: \.self) { Text($0).font(.callout).textSelection(.enabled) } }.padding(.top, 8)
                }.mirrorCard(padding: 20)
            }
        }
    }
    private func hypothesisText(_ label: String, _ text: String, symbol: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(label, systemImage: symbol).font(.caption.weight(.semibold)).foregroundStyle(MirrorPalette.muted)
            Text(reportInlineText(text)).font(.body).lineSpacing(4).textSelection(.enabled)
        }
    }
}

private struct DetailReferences: View {
    let ids: [String]
    let sources: [DetailSource]
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            ForEach(sources.filter { ids.contains($0.id) }) { source in
                if let url = URL(string: source.url), source.valid {
                    Link(destination: url) { Label(source.title, systemImage: "book.closed") }.font(.caption).foregroundStyle(MirrorPalette.muted)
                }
            }
        }
    }
}

import AppKit
import SwiftUI
import CoreText

struct StatusStates: View {
    let scheme: ColorScheme
    let now: Date
    var selectedBackdrop = false
    private let states: [(String, Double)] = [
        ("正常", 6.2), ("下界", 3.9), ("上界", 7.8),
        ("偏高", 8.0), ("偏低", 3.8), ("双位数", 10.4)]
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(selectedBackdrop ? "模拟选中背景" : scheme == .dark ? "深色 · 16.2pt" : "浅色 · 16.2pt")
                .font(.system(size: 12, weight: .semibold)).padding(.bottom, 5)
            ForEach(states, id: \.0) { state in
                row(state.0, Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: state.1, trend: "→"))
            }
            row("旧高值", Reading(sourceAt: now.addingTimeInterval(-1200).timeIntervalSince1970 * 1000, value: 8.0, trend: "→"))
            row("无数据", nil)
        }.padding(16).frame(width: 178)
            .foregroundStyle(.primary)
            .background(selectedBackdrop ? Color(red: 0.08, green: 0.32, blue: 0.68) : scheme == .dark ? Color(red: 0.07, green: 0.08, blue: 0.10) : Color(red: 0.96, green: 0.97, blue: 0.98))
            .environment(\.colorScheme, scheme)
    }
    private func row(_ title: String, _ reading: Reading?) -> some View {
        let original = StatusBadge.menuImage(reading: reading, now: now)
        let appearance = NSAppearance(named: scheme == .dark ? .darkAqua : .aqua)!
        let previewImage = original.isTemplate ? original : NSImage(cgImage: StatusPreview.raster(original, appearance: appearance).cgImage!, size: original.size)
        return HStack {
            Text(title).font(.system(size: 11)).foregroundStyle(.secondary).frame(width: 42, alignment: .leading)
            Spacer(minLength: 6)
            Image(nsImage: previewImage)
        }.frame(height: 22)
    }
}

@main
struct StatusPreview {
    @MainActor fileprivate static func raster(_ image: NSImage, appearance: NSAppearance) -> NSBitmapImageRep {
        let scale: CGFloat = 3
        let context = CGContext(data: nil, width: Int(ceil(image.size.width * scale)), height: Int(ceil(image.size.height * scale)),
                                bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.scaleBy(x: scale, y: scale)
        appearance.performAsCurrentDrawingAppearance {
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
            image.draw(in: NSRect(origin: .zero, size: image.size))
            NSGraphicsContext.restoreGraphicsState()
        }
        return NSBitmapImageRep(cgImage: context.makeImage()!)
    }

    @MainActor private static func glyphMask(_ text: String, size: NSSize) -> NSBitmapImageRep {
        let scale: CGFloat = 3
        let context = CGContext(data: nil, width: Int(ceil(size.width * scale)), height: Int(ceil(size.height * scale)),
                                bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.scaleBy(x: scale, y: scale)
        let font = NSFont(name: "HelveticaNeue", size: 16 * 18 / 22)!
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: [.font: font, .foregroundColor: NSColor.black]))
        context.textMatrix = .identity
        context.textPosition = CGPoint(x: 8, y: 4 * 18 / 22)
        CTLineDraw(line, context)
        return NSBitmapImageRep(cgImage: context.makeImage()!)
    }

    @MainActor private static func checkWarningPixels(_ value: Double, now: Date, appearance: NSAppearance, image reusedImage: NSImage? = nil) {
        let reading = Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: value, trend: "→")
        let image = reusedImage ?? StatusBadge.menuImage(reading: reading, now: now)
        let actual = raster(image, appearance: appearance)
        let mask = glyphMask(reading.display, size: image.size)
        var tintedIcon = 0, corePixels = 0, rightDigits = 0
        var coreBrightness: CGFloat = 0
        for y in 0..<actual.pixelsHigh {
            for x in 0..<actual.pixelsWide {
                let color = actual.colorAt(x: x, y: y)!.usingColorSpace(.deviceRGB)!
                let components = [color.redComponent, color.greenComponent, color.blueComponent]
                let chroma = components.max()! - components.min()!
                if x < 21 && color.alphaComponent > 0.4 && chroma > 0.1 { tintedIcon += 1 }
                if x >= 50 && color.alphaComponent > 0.8 {
                    rightDigits += 1
                    assert(chroma < 0.04, "Warning color must not tint numeric foreground")
                }
                if mask.colorAt(x: x, y: y)!.alphaComponent > 0.98 {
                    corePixels += 1
                    coreBrightness += (color.redComponent + color.greenComponent + color.blueComponent) / 3
                    assert(color.alphaComponent > 0.75 && chroma < 0.04, "Icon edges must not cut or recolor any numeral core")
                }
            }
        }
        assert(tintedIcon > 10 && corePixels > 30 && rightDigits > 10)
        let dark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        let brightness = coreBrightness / CGFloat(corePixels)
        assert(dark ? brightness > 0.6 : brightness < 0.3, "Numeric ink must contrast with the actual drawing appearance")
    }

    @MainActor static func main() throws {
        let now = Date(timeIntervalSince1970: 1_794_290_400)
        assert(NSFont(name: "HelveticaNeue", size: 16 * 18 / 22) != nil)
        for value in [3.9, 6.2, 7.8] {
            let reading = Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: value, trend: "→")
            let badge = StatusBadge.menuImage(reading: reading, now: now)
            assert(StatusBadge.rangeState(reading: reading, now: now) == .normal)
            assert(badge.isTemplate && abs(badge.size.height - 16.2) < 0.001 && badge.size.width < 30 && badge.tiffRepresentation != nil)
        }
        for value in [3.8, 7.9, 10.4] {
            let reading = Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: value, trend: "→")
            let badge = StatusBadge.menuImage(reading: reading, now: now)
            assert(StatusBadge.rangeState(reading: reading, now: now) == (value < 3.9 ? .low : .high))
            assert(!badge.isTemplate)
            for name in [NSAppearance.Name.aqua, .darkAqua] {
                checkWarningPixels(value, now: now, appearance: NSAppearance(named: name)!)
            }
        }
        let sameWarningImage = StatusBadge.menuImage(reading: Reading(sourceAt: now.timeIntervalSince1970 * 1000, value: 8.0, trend: "→"), now: now)
        for name in [NSAppearance.Name.aqua, .darkAqua, .aqua] {
            checkWarningPixels(8.0, now: now, appearance: NSAppearance(named: name)!, image: sameWarningImage)
        }
        for offset: TimeInterval in [-601, 121] {
            let reading = Reading(sourceAt: now.addingTimeInterval(offset).timeIntervalSince1970 * 1000, value: 8.0, trend: "→")
            assert(StatusBadge.rangeState(reading: reading, now: now) == .unavailable)
            let image = StatusBadge.menuImage(reading: reading, now: now)
            assert(image.isTemplate, "Outdated or future values must not show an active colored warning")
            let bitmap = raster(image, appearance: NSAppearance(named: .aqua)!)
            var maximumAlpha: CGFloat = 0
            for y in 0..<bitmap.pixelsHigh {
                for x in 0..<bitmap.pixelsWide {
                    maximumAlpha = max(maximumAlpha, bitmap.colorAt(x: x, y: y)!.alphaComponent)
                }
            }
            assert(maximumAlpha > 0.4 && maximumAlpha < 0.55, "Unavailable values must remain visibly faded")
        }
        assert(StatusBadge.rangeState(reading: nil, now: now) == .unavailable)
        assert(StatusBadge.menuImage(reading: nil, now: now).isTemplate)
        print("Status badge: threshold boundaries, stale/missing neutrality, colored icon and intact grayscale digits in light/dark passed")
        let view = VStack(spacing: 10) {
            HStack(spacing: 12) {
                StatusStates(scheme: .light, now: now)
                StatusStates(scheme: .dark, now: now)
                StatusStates(scheme: .dark, now: now, selectedBackdrop: true)
            }
            Text("受控浅/深绘制外观；右列仅模拟选中背景，不代替系统选中态验收").font(.system(size: 11)).foregroundStyle(.secondary)
        }.padding(12).background(Color.white)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff), let data = bitmap.representation(using: .png, properties: [:]) else { throw MirrorError.unavailable }
        let output = CommandLine.arguments.dropFirst().first ?? "macos/build/menubar-states-synthetic.png"
        try data.write(to: URL(fileURLWithPath: output))
        print("Rendered native status badge states in light/dark appearance and a simulated selection backdrop")
    }
}

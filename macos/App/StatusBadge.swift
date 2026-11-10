import AppKit
import CoreText

enum StatusBadge {
    enum RangeState {
        case normal, low, high, unavailable
        var description: String {
            switch self {
            case .normal: return "观察范围内"
            case .low: return "低于观察范围"
            case .high: return "高于观察范围"
            case .unavailable: return "读数待更新"
            }
        }
    }
    static func rangeState(reading: Reading?, now: Date) -> RangeState {
        guard let reading, !reading.isStale(at: now) else { return .unavailable }
        if reading.value < 3.9 { return .low }
        if reading.value > 7.8 { return .high }
        return .normal
    }

    @MainActor static func menuImage(reading: Reading?, now: Date) -> NSImage {
        let stale = reading?.isStale(at: now) ?? true
        let state = rangeState(reading: reading, now: now)
        let low = state == .low
        let high = state == .high
        let warning = low || high
        let iconOpacity: CGFloat = warning ? 0.65 : 0.40
        let value = reading?.display ?? "—"
        let font = NSFont(name: "HelveticaNeue", size: 16 * 18 / 22) ?? NSFont.systemFont(ofSize: 16 * 18 / 22, weight: .regular)
        let origin = CGPoint(x: 8, y: 4 * 18 / 22)
        let measure = CTLineCreateWithAttributedString(NSAttributedString(string: value, attributes: [.font: font]))
        let size = NSSize(width: origin.x + CGFloat(CTLineGetTypographicBounds(measure, nil, nil, nil)) + 2, height: 16.2)
        // Resolve the numeric ink when drawn, not from the application's window theme.
        let image = NSImage(size: size, flipped: false) { _ in
            guard let context = NSGraphicsContext.current?.cgContext else { return false }
            let numericInk = warning ? NSColor.labelColor : NSColor.black
            let iconInk = low ? NSColor.systemRed : high ? NSColor.systemOrange : NSColor.black
            let text = CTLineCreateWithAttributedString(NSAttributedString(string: value, attributes: [.font: font, .foregroundColor: numericInk]))
            context.saveGState()
            context.setAlpha(stale ? 0.48 : 1)
            context.beginTransparencyLayer(auxiliaryInfo: nil)
            context.setFillColor(iconInk.cgColor)
            context.setStrokeColor(iconInk.cgColor)
            context.setLineWidth(1.15)
            context.setLineCap(.round)
            context.setLineJoin(.round)
            let circle = CGRect(x: 0.7, y: 0.7, width: 14.8, height: 14.8)
            context.setAlpha(iconOpacity * 0.15)
            context.fillEllipse(in: circle)
            context.setAlpha(iconOpacity)
            context.strokeEllipse(in: circle)
            let wave = CGMutablePath()
            wave.move(to: CGPoint(x: 1.8, y: 7))
            wave.addLines(between: [CGPoint(x: 4, y: 7), CGPoint(x: 5.4, y: 11.4), CGPoint(x: 7.5, y: 4.5), CGPoint(x: 9.3, y: 9), CGPoint(x: 14.2, y: 9)])
            context.setAlpha(iconOpacity * 0.65)
            context.addPath(wave)
            context.strokePath()
            context.setAlpha(1)
            // The icon yields a transparent rim around intact foreground digits.
            context.setBlendMode(.clear)
            context.setTextDrawingMode(.stroke)
            context.setLineWidth(1.8)
            context.textMatrix = .identity
            context.textPosition = origin
            CTLineDraw(text, context)
            context.setBlendMode(.normal)
            context.setTextDrawingMode(.fill)
            context.textPosition = origin
            CTLineDraw(text, context)
            context.endTransparencyLayer()
            context.restoreGState()
            return true
        }
        image.isTemplate = !warning
        image.cacheMode = .never
        return image
    }
}

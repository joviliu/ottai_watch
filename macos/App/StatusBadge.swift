import AppKit
import CoreText

enum StatusBadge {
    @MainActor static func menuImage(reading: Reading?, now: Date) -> NSImage {
        let fontSize: CGFloat = 16 * 18 / 22
        let textOrigin = CGPoint(x: 5 * 18 / 22, y: 4 * 18 / 22)
        let text = NSAttributedString(string: reading?.display ?? "—", attributes: [
            .font: NSFont(name: "HelveticaNeue", size: fontSize) ?? NSFont.systemFont(ofSize: fontSize, weight: .regular),
            .foregroundColor: NSColor.black
        ])
        let line = CTLineCreateWithAttributedString(text)
        let width = max(16.2, textOrigin.x + CGFloat(CTLineGetTypographicBounds(line, nil, nil, nil)) + 2)
        let size = NSSize(width: width, height: 16.2)
        guard let context = CGContext(data: nil, width: Int(ceil(size.width * 3)), height: Int(ceil(size.height * 3)),
                                      bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return NSImage(size: size)
        }
        context.scaleBy(x: 3, y: 3)
        context.setAlpha(reading?.isStale(at: now) ?? true ? 0.48 : 1)
        context.beginTransparencyLayer(auxiliaryInfo: nil)
        context.setFillColor(NSColor.black.cgColor)
        let drop = CGMutablePath()
        drop.move(to: CGPoint(x: 10, y: 22))
        drop.addCurve(to: CGPoint(x: 2, y: 7.7), control1: CGPoint(x: 8.08, y: 17.16), control2: CGPoint(x: 2, y: 13.2))
        drop.addCurve(to: CGPoint(x: 18, y: 7.7), control1: CGPoint(x: 2, y: -2.2), control2: CGPoint(x: 18, y: -2.2))
        drop.addCurve(to: CGPoint(x: 10, y: 22), control1: CGPoint(x: 18, y: 13.2), control2: CGPoint(x: 11.92, y: 17.16))
        drop.closeSubpath()
        let dropScale: CGFloat = 16.2 / 22
        let dropWidthScale: CGFloat = 0.9 * 1.05
        var dropTransform = CGAffineTransform(a: dropScale * dropWidthScale, b: 0, c: 0, d: dropScale,
                                              tx: 10 * dropScale * (1 - dropWidthScale), ty: 0)
        context.addPath(drop.copy(using: &dropTransform) ?? drop)
        context.fillPath()
        // XOR cuts digits out inside the solid drop and keeps them opaque outside it.
        context.setBlendMode(.xor)
        context.textMatrix = .identity
        context.textPosition = textOrigin
        CTLineDraw(line, context)
        context.endTransparencyLayer()
        guard let bitmap = context.makeImage() else { return NSImage(size: size) }
        let image = NSImage(cgImage: bitmap, size: size)
        // A single template image preserves overlap and adapts to the actual menu-bar background.
        image.isTemplate = true
        return image
    }
}

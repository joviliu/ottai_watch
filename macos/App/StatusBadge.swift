import AppKit
import CoreText

enum StatusBadge {
    @MainActor static func menuImage(reading: Reading?, now: Date) -> NSImage {
        let text = NSAttributedString(string: reading?.display ?? "—", attributes: [
            .font: NSFont(name: "HelveticaNeue-Thin", size: 16) ?? NSFont.systemFont(ofSize: 16, weight: .thin),
            .foregroundColor: NSColor.black
        ])
        let line = CTLineCreateWithAttributedString(text)
        let width = max(16, CGFloat(CTLineGetTypographicBounds(line, nil, nil, nil)) + 3) + 4
        let scale: CGFloat = 18 / 22
        let size = NSSize(width: width * scale, height: 18)
        guard let context = CGContext(data: nil, width: Int(ceil(size.width * 3)), height: 54,
                                      bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return NSImage(size: size)
        }
        context.scaleBy(x: 3 * scale, y: 3 * scale)
        context.setAlpha(reading?.isStale(at: now) ?? true ? 0.48 : 1)
        context.beginTransparencyLayer(auxiliaryInfo: nil)
        context.setFillColor(NSColor.black.cgColor)
        let drop = CGMutablePath()
        drop.move(to: CGPoint(x: 10, y: 22))
        drop.addCurve(to: CGPoint(x: 2, y: 7.7), control1: CGPoint(x: 8.08, y: 17.16), control2: CGPoint(x: 2, y: 13.2))
        drop.addCurve(to: CGPoint(x: 18, y: 7.7), control1: CGPoint(x: 2, y: -2.2), control2: CGPoint(x: 18, y: -2.2))
        drop.addCurve(to: CGPoint(x: 10, y: 22), control1: CGPoint(x: 18, y: 13.2), control2: CGPoint(x: 11.92, y: 17.16))
        drop.closeSubpath()
        context.addPath(drop)
        context.fillPath()
        // XOR cuts digits out inside the solid drop and keeps them opaque outside it.
        context.setBlendMode(.xor)
        context.textMatrix = .identity
        context.textPosition = CGPoint(x: 5, y: 4)
        CTLineDraw(line, context)
        context.endTransparencyLayer()
        guard let bitmap = context.makeImage() else { return NSImage(size: size) }
        let image = NSImage(cgImage: bitmap, size: size)
        // A single template image preserves overlap and adapts to the actual menu-bar background.
        image.isTemplate = true
        return image
    }
}

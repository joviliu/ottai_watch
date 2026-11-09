import SwiftUI

enum MirrorPalette {
    static let blue = Color(red: 0.18, green: 0.43, blue: 0.88)
    static let violet = Color(red: 0.48, green: 0.37, blue: 0.74)
    static let ink = Color(red: 0.16, green: 0.21, blue: 0.31)
    static let muted = Color(red: 0.43, green: 0.48, blue: 0.59)
    static let background = LinearGradient(
        colors: [Color(red: 0.91, green: 0.96, blue: 1), Color(red: 0.95, green: 0.93, blue: 1), Color(red: 1, green: 0.95, blue: 0.91)],
        startPoint: .topLeading, endPoint: .bottomTrailing)
}

extension View {
    func mirrorCard(padding: CGFloat = 16) -> some View {
        self.padding(padding)
            .background(Color.white.opacity(0.96), in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Color.white.opacity(0.9), lineWidth: 1))
            .shadow(color: MirrorPalette.blue.opacity(0.045), radius: 10, x: 0, y: 3)
    }
}

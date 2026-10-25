// Foreground (subject) isolation using the macOS Vision framework.
// Produces an RGBA PNG with the background removed. Vision's instance-mask
// model handles fine detail like curly hair far better than colour keying,
// which matters here because the source photos are shot against a cream wall
// that is close in tone to skin and the t-shirt.
//
// Requires macOS 14+.  Run:  swift scripts/lift_subject.swift <in> <out>

import Foundation
import Vision
import CoreImage
import AppKit

func die(_ msg: String) -> Never {
    FileHandle.standardError.write(("lift_subject: " + msg + "\n").data(using: .utf8)!)
    exit(1)
}

guard CommandLine.arguments.count == 3 else { die("usage: lift_subject <in> <out>") }
let inURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outURL = URL(fileURLWithPath: CommandLine.arguments[2])

guard let source = CGImageSourceCreateWithURL(inURL as CFURL, nil) else {
    die("cannot open \(inURL.path)")
}
let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
let exifOrientation = (props?[kCGImagePropertyOrientation] as? UInt32) ?? 1

guard var image = CIImage(contentsOf: inURL) else { die("cannot decode \(inURL.path)") }
image = image.oriented(forExifOrientation: Int32(exifOrientation))
// Normalise so the extent starts at the origin.
if image.extent.origin != .zero {
    image = image.transformed(by: CGAffineTransform(translationX: -image.extent.origin.x,
                                                    y: -image.extent.origin.y))
}
let extent = image.extent

let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(ciImage: image, options: [:])
do {
    try handler.perform([request])
} catch {
    die("Vision request failed: \(error)")
}
guard let observation = request.results?.first else { die("no foreground subject detected") }

let maskBuffer: CVPixelBuffer
do {
    maskBuffer = try observation.generateScaledMaskForImage(forInstances: observation.allInstances,
                                                            from: handler)
} catch {
    die("mask generation failed: \(error)")
}

var mask = CIImage(cvPixelBuffer: maskBuffer)
// Scale the mask to the working image in case Vision returned it at model size.
let sx = extent.width / mask.extent.width
let sy = extent.height / mask.extent.height
mask = mask.transformed(by: CGAffineTransform(scaleX: sx, y: sy))

let clear = CIImage(color: CIColor.clear).cropped(to: extent)
guard let blend = CIFilter(name: "CIBlendWithMask", parameters: [
    kCIInputImageKey: image,
    kCIInputBackgroundImageKey: clear,
    kCIInputMaskImageKey: mask,
])?.outputImage else { die("blend failed") }

let ctx = CIContext(options: [.workingColorSpace: CGColorSpace(name: CGColorSpace.sRGB)!])
guard let cg = ctx.createCGImage(blend, from: extent) else { die("render failed") }

let rep = NSBitmapImageRep(cgImage: cg)
guard let png = rep.representation(using: .png, properties: [:]) else { die("PNG encoding failed") }
try png.write(to: outURL)
FileHandle.standardError.write("wrote \(outURL.lastPathComponent) \(cg.width)x\(cg.height)\n".data(using: .utf8)!)

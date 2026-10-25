// Detect eye centres in a photo with the macOS Vision framework and print them
// as JSON (pixel coordinates, top-left origin). Used to register adit1 and
// adit2 so the swap keeps the eyes locked in place.
//
//   swift scripts/face_points.swift adit1.jpeg

import Foundation
import Vision
import CoreImage
import AppKit

func die(_ m: String) -> Never {
    FileHandle.standardError.write(("face_points: " + m + "\n").data(using: .utf8)!)
    exit(1)
}

guard CommandLine.arguments.count == 2 else { die("usage: face_points <image>") }
let url = URL(fileURLWithPath: CommandLine.arguments[1])

guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else { die("cannot read image") }
let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]
let orientationRaw = (props?[kCGImagePropertyOrientation] as? UInt32) ?? 1
let cgOrientation = CGImagePropertyOrientation(rawValue: orientationRaw) ?? .up

// Dimensions after EXIF orientation is applied.
let swap = [5, 6, 7, 8].contains(Int(orientationRaw))
let W = CGFloat(swap ? cg.height : cg.width)
let H = CGFloat(swap ? cg.width : cg.height)

let request = VNDetectFaceLandmarksRequest()
let handler = VNImageRequestHandler(cgImage: cg, orientation: cgOrientation, options: [:])
do { try handler.perform([request]) } catch { die("Vision failed: \(error)") }

guard let faces = request.results, !faces.isEmpty else { die("no face detected") }
// largest face
let face = faces.max(by: { $0.boundingBox.width * $0.boundingBox.height
                          < $1.boundingBox.width * $1.boundingBox.height })!
guard let lm = face.landmarks else { die("no landmarks") }

func centre(_ region: VNFaceLandmarkRegion2D?) -> (CGFloat, CGFloat)? {
    guard let region = region, region.pointCount > 0 else { return nil }
    let pts = region.pointsInImage(imageSize: CGSize(width: W, height: H))
    var sx: CGFloat = 0, sy: CGFloat = 0
    for p in pts { sx += p.x; sy += p.y }
    let n = CGFloat(pts.count)
    // pointsInImage uses a bottom-left origin -> flip to top-left
    return (sx / n, H - sy / n)
}

guard let e1 = centre(lm.leftEye) ?? centre(lm.leftPupil),
      let e2 = centre(lm.rightEye) ?? centre(lm.rightPupil) else { die("no eye landmarks") }

// order left-to-right in image space
let (a, b) = e1.0 <= e2.0 ? (e1, e2) : (e2, e1)
let json = "{\"w\":\(Int(W)),\"h\":\(Int(H)),"
         + "\"eyeL\":[\(a.0),\(a.1)],\"eyeR\":[\(b.0),\(b.1)]}"
print(json)

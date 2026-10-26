// Print eye-contour and pupil landmarks (pixel coords, top-left origin) as JSON.
// Used by compose_lookup.py (jawline seam + skin sampling for the looking-up pose).
//
//   swift scripts/eye_regions.swift assets/adit1-cut.png

import Foundation
import Vision
import CoreImage
import AppKit

func die(_ m: String) -> Never {
    FileHandle.standardError.write(("eye_regions: " + m + "\n").data(using: .utf8)!)
    exit(1)
}

guard CommandLine.arguments.count == 2 else { die("usage: eye_regions <image>") }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else { die("cannot read image") }
let W = CGFloat(cg.width), H = CGFloat(cg.height)

let request = VNDetectFaceLandmarksRequest()
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do { try handler.perform([request]) } catch { die("Vision failed: \(error)") }
guard let face = request.results?.max(by: { $0.boundingBox.width < $1.boundingBox.width }),
      let lm = face.landmarks else { die("no face") }

func pts(_ r: VNFaceLandmarkRegion2D?) -> String {
    guard let r = r else { return "[]" }
    let p = r.pointsInImage(imageSize: CGSize(width: W, height: H))
    return "[" + p.map { "[\($0.x),\(H - $0.y)]" }.joined(separator: ",") + "]"
}

print("{\"w\":\(Int(W)),\"h\":\(Int(H)),"
    + "\"leftEye\":\(pts(lm.leftEye)),\"rightEye\":\(pts(lm.rightEye)),"
    + "\"leftPupil\":\(pts(lm.leftPupil)),\"rightPupil\":\(pts(lm.rightPupil)),"
    + "\"faceContour\":\(pts(lm.faceContour))}")

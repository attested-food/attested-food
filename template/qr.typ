// QR alone on a white page, rendered to PNG for the prover-friendly variant (raster image
// instead of ~1200 vector path ops). typst compile --format png --input url=<url> template/qr.typ
#import "@preview/tiaoma:0.3.0": qrcode
#set page(width: auto, height: auto, margin: 0pt, fill: white)
#qrcode(sys.inputs.url, options: (scale: 1.0))

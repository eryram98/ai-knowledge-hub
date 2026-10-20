"""Shared test fixture: build minimal text-layer PDFs without extra dependencies."""

try:
    import pypdf  # noqa: F401
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def build_pdf(page_texts):
    """Build a minimal valid PDF whose pages carry the given text (empty string = blank page)."""
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>", 3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    kids = []
    next_id = 4
    for text in page_texts:
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        kids.append(page_id)
        ops = b""
        if text:
            safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops = "BT /F1 12 Tf 72 720 Td ({0}) Tj ET".format(safe).encode("latin-1")
        objects[content_id] = b"<< /Length " + str(len(ops)).encode() + b" >>\nstream\n" + ops + b"\nendstream"
        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 3 0 R >> >> /Contents {0} 0 R >>".format(content_id).encode()
        )
    objects[2] = "<< /Type /Pages /Kids [{0}] /Count {1} >>".format(
        " ".join("{0} 0 R".format(k) for k in kids), len(kids)
    ).encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += "{0} 0 obj\n".format(obj_id).encode() + objects[obj_id] + b"\nendobj\n"
    xref_at = len(out)
    size = max(objects) + 1
    out += "xref\n0 {0}\n0000000000 65535 f \n".format(size).encode()
    for obj_id in range(1, size):
        out += "{0:010d} 00000 n \n".format(offsets[obj_id]).encode()
    out += "trailer\n<< /Size {0} /Root 1 0 R >>\nstartxref\n{1}\n%%EOF\n".format(size, xref_at).encode()
    return bytes(out)

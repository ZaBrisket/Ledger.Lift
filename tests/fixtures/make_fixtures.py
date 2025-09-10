from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def make_sample(path="sample.pdf"):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, height - 72, "Ledger Lift Sample PDF")
    c.setFont("Helvetica", 12)
    c.drawString(72, height - 108, "This is a tiny synthetic PDF for tests.")
    c.showPage()
    c.save()

if __name__ == "__main__":
    make_sample()
